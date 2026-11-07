"""Serve the compiled SPA from the API process.

A deployment can serve both the API and the frontend from one process: build
the SPA, set ``FRONTEND_DIST_DIR`` to the output directory, and this module
serves it. Local development keeps using the Vite dev server, so the module is
inactive unless that setting is present.

``/api`` is always dynamic and must never be cached, hashed Vite assets may be
cached forever, other images and fonts for 30 days, and the SPA shell
(including deep links) is revalidated on every request.
"""

from __future__ import annotations

from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
}

_NO_STORE_FILES = frozenset({"sw.js", "pwa-build.json"})
_CACHEABLE_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".avif",
        ".ico",
        ".svg",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
    }
)


def is_api_path(path: str, api_prefix: str) -> bool:
    """Return whether a request path belongs to the API namespace."""
    prefix = "/" + api_prefix.strip("/")
    if prefix == "/":
        return True
    return path == prefix or path.startswith(f"{prefix}/")


def cache_control_for(path: str) -> str:
    """Pick the same cache policy the nginx tier used."""
    normalized = path.strip("/")
    filename = normalized.rsplit("/", 1)[-1]

    if filename in _NO_STORE_FILES:
        return "no-cache, no-store, must-revalidate"
    if filename == "manifest.webmanifest":
        return "no-cache"
    if normalized.startswith("assets/"):
        return "public, max-age=31536000, immutable"
    if Path(normalized).suffix.lower() in _CACHEABLE_EXTENSIONS:
        return "public, max-age=2592000"
    return "no-cache"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply the browser security headers to every response.

    API responses are also marked ``no-store`` because they contain
    authenticated data. The static file handler sets its own cache policy;
    ``setdefault`` leaves those headers untouched.
    """

    def __init__(self, app, *, api_prefix: str) -> None:
        super().__init__(app)
        self.api_prefix = api_prefix

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        if is_api_path(request.url.path, self.api_prefix):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


class SPAStaticFiles(StaticFiles):
    """Static files with an index.html fallback for client-side routes."""

    def __init__(self, *, directory: str | Path, api_prefix: str, **kwargs) -> None:
        super().__init__(directory=directory, html=True, **kwargs)
        self.api_prefix = api_prefix

    async def get_response(self, path: str, scope: Scope) -> Response:
        request_path = scope.get("path", "")
        # Unknown API routes must remain JSON 404s, never the SPA shell. This
        # matters because the mount at "/" also sees anything not registered
        # by a router.
        if is_api_path(request_path, self.api_prefix):
            raise HTTPException(status_code=404)

        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            # A missing file (anything with a suffix) is a real 404. Only
            # extensionless deep links fall back to the client-side router.
            if exc.status_code != 404 or Path(path).suffix:
                raise
            response = await super().get_response("index.html", scope)

        response.headers.setdefault("Cache-Control", cache_control_for(path))
        return response
