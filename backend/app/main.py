"""ASGI application factory.

This module contains application creation, middleware and router registration
only. Business logic lives in ``services`` and HTTP handlers live in ``api``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    activities,
    admin,
    auth,
    balances,
    categories,
    expenses,
    features,
    groups,
    health,
    receipts,
    stats,
    sync,
)
from app.api.errors import service_error
from app.core.config import Settings, get_settings
from app.core.logging import RequestContextMiddleware, configure_logging
from app.core.observability import init_sentry
from app.services.errors import ServiceError
from app.storage import close_storage


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Release the process-wide blob client on shutdown."""
    try:
        yield
    finally:
        close_storage()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    init_sentry(settings)

    api_prefix = settings.api_prefix.rstrip("/")
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        docs_url=f"{api_prefix}/docs",
        openapi_url=f"{api_prefix}/openapi.json",
        redoc_url=f"{api_prefix}/redoc",
        swagger_ui_oauth2_redirect_url=f"{api_prefix}/docs/oauth2-redirect",
        lifespan=_lifespan,
    )

    @app.exception_handler(ServiceError)
    async def _service_error_handler(_request: Request, exc: ServiceError) -> JSONResponse:
        http_exc = service_error(exc)
        return JSONResponse(status_code=http_exc.status_code, content={"detail": http_exc.detail})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )

    # Added last so Starlette makes it the outermost middleware. It then wraps
    # CORS as well, giving preflight and rejected-origin responses a request id.
    app.add_middleware(RequestContextMiddleware, settings=settings)

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(admin.router, prefix=settings.api_prefix)
    app.include_router(features.router, prefix=settings.api_prefix)
    app.include_router(categories.router, prefix=settings.api_prefix)
    app.include_router(groups.router, prefix=settings.api_prefix)
    app.include_router(balances.global_router, prefix=settings.api_prefix)
    app.include_router(balances.group_router, prefix=settings.api_prefix)
    app.include_router(stats.router, prefix=settings.api_prefix)
    app.include_router(activities.router, prefix=settings.api_prefix)
    app.include_router(expenses.router, prefix=settings.api_prefix)
    app.include_router(receipts.router, prefix=settings.api_prefix)
    app.include_router(receipts.ai_router, prefix=settings.api_prefix)
    app.include_router(sync.router, prefix=settings.api_prefix)

    return app


app = create_app()
