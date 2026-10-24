"""ASGI application factory.

This module contains application creation, middleware and router registration
only. Business logic lives in ``services`` and HTTP handlers live in ``api``.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    stats,
)
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )

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

    return app


app = create_app()
