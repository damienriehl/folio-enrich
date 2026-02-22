from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import enrich, export, health, synthetic
from app.config import settings
from app.middleware.error_handler import register_error_handlers
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security import SecurityMiddleware

app = FastAPI(title=settings.app_name, version="0.1.0")

# Middleware (order matters: outermost first)
app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)
app.add_middleware(SecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
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
