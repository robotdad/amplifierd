"""API key authentication middleware for amplifierd."""

from __future__ import annotations

import hmac
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

_LOCALHOST_HOSTS = {"127.0.0.1", "localhost", "::1"}

_PUBLIC_PATHS = {"/health", "/info", "/docs", "/redoc", "/openapi.json"}


def is_localhost(host: str | None) -> bool:
    """Check if the request originates from localhost."""
    return host in _LOCALHOST_HOSTS or host is None


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Require API key for non-localhost requests.

    Bypass order:
    1. Localhost requests -> always pass
    2. Public paths (/health, /info, /docs, /redoc, /openapi.json) -> always pass
    3. Valid Authorization: Bearer <api_key> -> pass
    4. Otherwise -> 401
    """

    def __init__(self, app, api_key: str) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        # Localhost always bypasses
        client_host = request.client.host if request.client else None
        if is_localhost(client_host):
            return await call_next(request)

        # Public paths bypass
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        # Check Bearer token
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if hmac.compare_digest(token, self.api_key):
                return await call_next(request)

        logger.warning(
            "Rejected request from %s to %s: missing or invalid API key",
            client_host,
            request.url.path,
        )
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing API key"},
        )
