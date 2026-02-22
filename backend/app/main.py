import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import enrich, export, health, settings, synthetic
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
    """Pre-compute FOLIO label embeddings at startup (runs in background)."""
    try:
        from app.services.folio.folio_service import FolioService
        from app.services.embedding.service import EmbeddingService

        folio_service = FolioService.get_instance()
        embedding_service = EmbeddingService.get_instance()
        # Run the heavy encoding in a thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, embedding_service.index_folio_labels, folio_service)
        logger.info("FOLIO embedding index ready (%d vectors)", embedding_service.index_size)
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: index embeddings in background, start cleanup task
    asyncio.create_task(_index_folio_embeddings())
    cleanup_task = asyncio.create_task(_periodic_job_cleanup())
    yield
    # Shutdown
    cleanup_task.cancel()


app = FastAPI(title=app_settings.app_name, version="0.1.0", lifespan=lifespan)

# Middleware (order matters: outermost first)
app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)
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
app.include_router(settings.router)
