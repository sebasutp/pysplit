"""Synchronization HTTP endpoints (bootstrap, pull and push)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import OptionalUser, SessionDep, SettingsDep
from app.api.errors import raise_service_error
from app.schemas.sync import (
    SyncBootstrapResponse,
    SyncPullRequest,
    SyncPullResponse,
    SyncPushRequest,
    SyncPushResponse,
)
from app.services import sync as sync_service
from app.services.errors import ServiceError

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/bootstrap", response_model=SyncBootstrapResponse)
def bootstrap(
    group_id: str,
    user: OptionalUser,
    session: SessionDep,
    settings: SettingsDep,
) -> SyncBootstrapResponse:
    try:
        return sync_service.bootstrap_group(
            session,
            group_id,
            user_id=user.id if user else None,
            settings=settings,
        )
    except ServiceError as exc:
        raise_service_error(exc)


@router.post("/pull", response_model=SyncPullResponse)
def pull(
    payload: SyncPullRequest,
    user: OptionalUser,
    session: SessionDep,
    settings: SettingsDep,
) -> SyncPullResponse:
    try:
        return sync_service.pull_changes(
            session,
            payload,
            user_id=user.id if user else None,
            settings=settings,
        )
    except ServiceError as exc:
        raise_service_error(exc)


@router.post("/push", response_model=SyncPushResponse)
def push(
    payload: SyncPushRequest,
    user: OptionalUser,
    session: SessionDep,
    settings: SettingsDep,
) -> SyncPushResponse:
    return sync_service.push_operations(
        session,
        payload.operations,
        user_id=user.id if user else None,
        settings=settings,
    )
