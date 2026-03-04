import asyncio
import logging
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import concepts, enrich, export, feedback, health, ollama, settings, synthetic
from app.config import settings as app_settings
from app.middleware.error_handler import register_error_handlers
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security import SecurityMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


async def _index_folio_embeddings() -> None:
    """Pre-compute FOLIO label embeddings at startup (blocks startup until ready)."""
    try:
        from app.services.folio.owl_cache import ensure_owl_fresh
        from app.services.folio.folio_service import FolioService
        from app.services.embedding.service import EmbeddingService, build_embedding_index

        # Ensure OWL cache is fresh before FOLIO init reads it
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, ensure_owl_fresh)

        folio_service = FolioService.get_instance()
        embedding_service = EmbeddingService.get_instance()
        # Run the heavy encoding in a thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, embedding_service.index_folio_labels, folio_service)
        logger.info("FOLIO embedding index ready (%d vectors)", embedding_service.index_size)
        # Also build the FAISS-backed index for semantic search
        await loop.run_in_executor(None, build_embedding_index, folio_service)
    except Exception:
        logger.warning("Failed to pre-compute FOLIO embeddings — semantic features disabled", exc_info=True)


async def _periodic_job_cleanup() -> None:
    """Periodically clean up expired jobs."""
    from app.storage.job_store import JobStore

    store = JobStore()
    while True:
        try:
            deleted = await store.cleanup_expired()
            if deleted:
                logger.info("Cleaned up %d expired jobs", deleted)
        except Exception:
            logger.warning("Job cleanup failed", exc_info=True)
        await asyncio.sleep(3600)  # Every hour


async def _manage_ollama() -> None:
    """Detect and optionally start Ollama at startup."""
    if not (app_settings.ollama_auto_manage and app_settings.llm_provider == "ollama"):
        return

    try:
        from app.services.ollama.manager import OllamaManager
        manager = OllamaManager.get_instance()
        info = await manager.detect()

        if info.status.value == "running":
            logger.info("Ollama already running (v%s) with %d model(s)", info.version, len(info.models))
        elif info.status.value == "installed":
            logger.info("Ollama installed — starting server...")
            started = await manager.start()
            if started:
                logger.info("Ollama server started")
            else:
                logger.warning("Failed to start Ollama server — run setup via Settings")
        else:
            logger.warning("Ollama not installed — run setup via Settings or POST /ollama/setup")
    except Exception:
        logger.warning("Ollama auto-management failed", exc_info=True)


async def _stop_ollama() -> None:
    """Stop managed Ollama process on shutdown."""
    if not (app_settings.ollama_auto_manage and app_settings.llm_provider == "ollama"):
        return
    try:
        from app.services.ollama.manager import OllamaManager
        manager = OllamaManager.get_instance()
        await manager.stop()
    except Exception:
        logger.warning("Failed to stop Ollama", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: detect/start Ollama if configured
    await _manage_ollama()

    # Startup: eager-load FOLIO ontology and embedding index before accepting requests
    logger.info("Loading FOLIO ontology and building embedding index...")
    await _index_folio_embeddings()
    cleanup_task = asyncio.create_task(_periodic_job_cleanup())
    yield
    # Shutdown
    cleanup_task.cancel()
    await _stop_ollama()


app = FastAPI(title=app_settings.app_name, version="0.4.5", lifespan=lifespan)

# Middleware (order matters: outermost first)
app.add_middleware(
    RateLimitMiddleware,
    max_requests=app_settings.rate_limit_requests,
    window_seconds=app_settings.rate_limit_window,
)
app.add_middleware(SecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Error handlers
register_error_handlers(app)

# Routes
app.include_router(health.router)
app.include_router(enrich.router)
app.include_router(export.router)
app.include_router(synthetic.router)
app.include_router(concepts.router)
app.include_router(feedback.router)
app.include_router(settings.router)
app.include_router(ollama.router)

# Serve frontend
_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend_dir.is_dir():
    @app.get("/", include_in_schema=False)
    async def _serve_index():
        return FileResponse(_frontend_dir / "index.html")

    app.mount("/static", StaticFiles(directory=_frontend_dir), name="frontend")
