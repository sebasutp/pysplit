"""Health endpoints.

The public contract keeps all three reference endpoints:
``/api/health``, ``/api/health/liveness`` and ``/api/health/readiness``.
Readiness is the only one that touches the database.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import SessionDep, SettingsDep
from app.schemas.health import HealthResponse, LivenessResponse, ReadinessResponse
from app.services.health import database_is_ready

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
def health(settings: SettingsDep) -> HealthResponse:
    """Return a cheap liveness-style payload used by clients and probes."""
    return HealthResponse(status="ok", version=settings.app_version)


@router.get("/liveness", response_model=LivenessResponse)
def liveness() -> LivenessResponse:
    """Prove the process is running without touching dependencies."""
    return LivenessResponse(status="alive")


@router.get("/readiness", response_model=ReadinessResponse)
def readiness(session: SessionDep) -> ReadinessResponse:
    """Prove the database is reachable with the configured credentials."""
    if not database_is_ready(session):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        )
    return ReadinessResponse(status="ready", checks={"database": "ok"})
