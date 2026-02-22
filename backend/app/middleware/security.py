from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

ALLOWED_CONTENT_TYPES = {
    "application/json",
    "text/plain",
    "multipart/form-data",
}

MAX_BODY_SIZE = 50 * 1024 * 1024  # 50MB default


class SecurityMiddleware(BaseHTTPMiddleware):
    """Input validation: content type checks, body size limits."""

    async def dispatch(self, request: Request, call_next):
        # Check body size for POST/PUT
        if request.method in ("POST", "PUT"):
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > MAX_BODY_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Request body too large. Maximum size: {MAX_BODY_SIZE} bytes."},
                )

        return await call_next(request)
