from __future__ import annotations

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc), "type": "validation_error"},
        )

    @app.exception_handler(Exception)
    async def general_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception: %s", exc)
        # Don't expose stack traces in production
        from app.config import settings

        detail = str(exc) if settings.debug else "Internal server error"
        return JSONResponse(
            status_code=500,
            content={"detail": detail, "type": "internal_error"},
        )
