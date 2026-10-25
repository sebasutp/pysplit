"""Synchronization HTTP endpoints (bootstrap, pull and push)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import OptionalUser, SessionDep, SettingsDep
from app.core.limits import enforce_sync_rate_limit
from app.schemas.sync import (
    SyncBootstrapResponse,
    SyncPullRequest,
    SyncPullResponse,
    SyncPushRequest,
    SyncPushResponse,
)
from app.services import sync as sync_service

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/bootstrap", response_model=SyncBootstrapResponse)
def bootstrap(
    group_id: str,
    request: Request,
    user: OptionalUser,
    session: SessionDep,
    settings: SettingsDep,
) -> SyncBootstrapResponse:
    enforce_sync_rate_limit(request, settings)
    return sync_service.bootstrap_group(
        session,
        group_id,
        user_id=user.id if user else None,
        settings=settings,
    )


@router.post("/pull", response_model=SyncPullResponse)
def pull(
    payload: SyncPullRequest,
    request: Request,
    user: OptionalUser,
    session: SessionDep,
    settings: SettingsDep,
) -> SyncPullResponse:
    enforce_sync_rate_limit(request, settings)
    return sync_service.pull_changes(
        session,
        payload,
        user_id=user.id if user else None,
        settings=settings,
    )


@router.post("/push", response_model=SyncPushResponse)
def push(
    payload: SyncPushRequest,
    request: Request,
    user: OptionalUser,
    session: SessionDep,
    settings: SettingsDep,
) -> SyncPushResponse:
    enforce_sync_rate_limit(request, settings)
    return sync_service.push_operations(
        session,
        payload.operations,
        user_id=user.id if user else None,
        settings=settings,
    )
