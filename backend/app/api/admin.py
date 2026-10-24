"""Admin HTTP endpoints.

Every route depends on :data:`app.api.deps.AdminUser`, which returns 401 for
anonymous callers and 403 for authenticated non-admin tiers.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import AdminUser, SessionDep
from app.schemas.admin import (
    AdminGroupList,
    AdminMetrics,
    AdminUserList,
    PreAuthorizeRequest,
    PreAuthorizeResponse,
    TierUpdateRequest,
    TierUpdateResponse,
)
from app.services import admin as admin_service
from app.services.errors import NotFoundError

router = APIRouter(prefix="/admin", tags=["admin"])

LimitQuery = Annotated[int, Query(ge=1, le=100)]
OffsetQuery = Annotated[int, Query(ge=0)]


@router.get("/metrics", response_model=AdminMetrics)
def metrics(_admin: AdminUser, session: SessionDep) -> AdminMetrics:
    return admin_service.get_metrics(session)


@router.get("/users", response_model=AdminUserList)
def list_users(
    _admin: AdminUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    tier: Annotated[str | None, Query(max_length=32)] = None,
    limit: LimitQuery = 10,
    offset: OffsetQuery = 0,
) -> AdminUserList:
    return admin_service.list_users(
        session,
        query=q,
        tier=tier,
        limit=limit,
        offset=offset,
    )


@router.post("/users/preauthorize", response_model=PreAuthorizeResponse)
def preauthorize_user(
    payload: PreAuthorizeRequest,
    _admin: AdminUser,
    session: SessionDep,
) -> PreAuthorizeResponse:
    return admin_service.preauthorize_user(
        session,
        email=payload.email,
        tier=payload.tier,
        name=payload.name,
    )


@router.patch("/users/{user_id}/tier", response_model=TierUpdateResponse)
def update_user_tier(
    user_id: str,
    payload: TierUpdateRequest,
    _admin: AdminUser,
    session: SessionDep,
) -> TierUpdateResponse:
    try:
        return admin_service.update_user_tier(
            session,
            user_id=user_id,
            tier=payload.tier,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    _admin: AdminUser,
    session: SessionDep,
) -> Response:
    try:
        admin_service.delete_user(session, user_id=user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/groups", response_model=AdminGroupList)
def list_groups(
    _admin: AdminUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: LimitQuery = 10,
    offset: OffsetQuery = 0,
) -> AdminGroupList:
    return admin_service.list_groups(
        session,
        query=q,
        limit=limit,
        offset=offset,
    )


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: str,
    _admin: AdminUser,
    session: SessionDep,
) -> Response:
    try:
        admin_service.delete_group(session, group_id=group_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
