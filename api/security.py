"""
Observer Intelligence Platform — Security Middleware
==================================================
API key authentication, rate limiting, and security headers.

Authentication:
    All /api/ endpoints and WebSocket require a valid API key.
    Keys are defined in OBSERVER_API_KEYS env var (comma-separated).
    Passed via X-API-Key header or ?api_key= query parameter.

    Static files, health check, and HTML pages are unauthenticated
    (HTML pages serve the UI shell — actual data comes via /api/).

Rate Limiting:
    Per-IP rate limits on API endpoints via slowapi.
    WebSocket already has per-IP limits in services/websocket.py.

@created 2026-02-23 — Production hardening
"""

import os
import secrets
import time
from typing import Optional

from fastapi import Request, WebSocket, HTTPException, Security
from fastapi.security import APIKeyHeader, APIKeyQuery
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from utils.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# API KEY CONFIGURATION
# =============================================================================
# Load from env: comma-separated list of valid API keys
# If not set, authentication is DISABLED (development mode)
_raw_keys = os.getenv("OBSERVER_API_KEYS", "").strip()
API_KEYS: set = {k.strip() for k in _raw_keys.split(",") if k.strip()} if _raw_keys else set()
AUTH_ENABLED: bool = len(API_KEYS) > 0

if AUTH_ENABLED:
    logger.info(f"API authentication ENABLED ({len(API_KEYS)} key(s) configured)")
else:
    logger.warning("API authentication DISABLED — set OBSERVER_API_KEYS in .env for production")


# FastAPI security scheme declarations (for OpenAPI docs)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_api_key_query = APIKeyQuery(name="api_key", auto_error=False)


# =============================================================================
# PATHS THAT SKIP AUTHENTICATION
# =============================================================================
# Health check must be unauthenticated for monitoring/load-balancer probes.
# Static files are served by nginx in production (or FastAPI mount in dev).
# HTML pages serve the UI shell — all sensitive data goes through /api/.
_PUBLIC_PATHS = {
    "/api/v1/health",
    "/api/v1/feeds/health",
}

_PUBLIC_PREFIXES = (
    "/static/",
    "/docs",
    "/openapi.json",
)


def _is_public_path(path: str) -> bool:
    """Check if a request path is exempt from API key auth."""
    if path in _PUBLIC_PATHS:
        return True
    for prefix in _PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _is_api_path(path: str) -> bool:
    """Check if a path is an API endpoint (requires auth when enabled)."""
    return path.startswith("/api/")


def _is_html_page(path: str) -> bool:
    """Check if this is an HTML page request (dashboard, client, feeds, etc.)."""
    # These serve the UI shell — auth is optional (controlled by OBSERVER_AUTH_PAGES)
    _page_paths = {"/", "/client", "/feeds", "/scraper", "/dashboard", "/console/obs"}
    return path in _page_paths or path.rstrip("/") in _page_paths


# Whether to require auth on HTML pages too (default: yes if auth is enabled)
AUTH_PAGES: bool = os.getenv("OBSERVER_AUTH_PAGES", "true").lower() == "true"


# =============================================================================
# AUTH MIDDLEWARE
# =============================================================================
class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces API key authentication on protected routes.

    API key can be provided via:
      - X-API-Key header (preferred)
      - ?api_key= query parameter (convenience for browser testing)

    Unauthenticated paths: health checks, static files, OpenAPI docs.
    """

    async def dispatch(self, request: Request, call_next):
        if not AUTH_ENABLED:
            return await call_next(request)

        path = request.url.path

        # Public paths always skip auth
        if _is_public_path(path):
            return await call_next(request)

        # HTML pages — skip auth if OBSERVER_AUTH_PAGES=false
        if _is_html_page(path) and not AUTH_PAGES:
            return await call_next(request)

        # API endpoints and (optionally) HTML pages require a key
        if _is_api_path(path) or _is_html_page(path):
            api_key = (
                request.headers.get("X-API-Key")
                or request.query_params.get("api_key")
            )

            if not api_key or api_key not in API_KEYS:
                if _is_html_page(path):
                    # For HTML pages, return 403 with a simple message
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Access denied. API key required."},
                    )
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                    headers={"WWW-Authenticate": "ApiKey"},
                )

        return await call_next(request)


def verify_ws_api_key(websocket: WebSocket) -> bool:
    """
    Verify API key for WebSocket connections.
    Key can be in query params: ws://host/ws?api_key=XXX
    Or in headers (if the client library supports it).

    Returns True if auth is disabled or key is valid.
    """
    if not AUTH_ENABLED:
        return True

    api_key = (
        websocket.headers.get("X-API-Key")
        or websocket.query_params.get("api_key")
    )
    return api_key is not None and api_key in API_KEYS


def generate_api_key() -> str:
    """Generate a cryptographically secure API key (for admin convenience)."""
    return f"observer_{secrets.token_urlsafe(32)}"
