"""Authentication middleware for NPA.

Supports Bearer tokens (JWT or API key) and optional client certificate auth.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from npa.config.config import AuthConfig


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces authentication on API endpoints."""

    EXEMPT_PATHS = {"/health", "/v1/docs", "/v1/redoc", "/openapi.json"}

    def __init__(self, app: Any, config: AuthConfig) -> None:
        super().__init__(app)
        self.config = config

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        if not self.config.enabled:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")

        if self.config.token_type == "bearer":
            if not auth_header.startswith("Bearer "):
                return JSONResponse(
                    status_code=401,
                    content={"code": "unauthorized", "message": "Missing Bearer token"},
                )
            token = auth_header[7:]

            # Check API keys first (constant-time comparison)
            if self.config.api_keys:
                if any(hmac.compare_digest(token, key) for key in self.config.api_keys):
                    return await call_next(request)

            # Try JWT verification
            if self.config.jwt_secret:
                try:
                    import jwt
                    jwt.decode(
                        token,
                        self.config.jwt_secret,
                        algorithms=[self.config.jwt_algorithm],
                    )
                    return await call_next(request)
                except Exception:
                    return JSONResponse(
                        status_code=401,
                        content={"code": "unauthorized", "message": "Invalid token"},
                    )

            return JSONResponse(
                status_code=401,
                content={"code": "unauthorized", "message": "Authentication failed"},
            )

        return await call_next(request)
