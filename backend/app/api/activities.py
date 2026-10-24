"""Activity HTTP endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import SessionDep
from app.api.errors import raise_service_error
from app.schemas.activities import ActivityList
from app.services import activities as activities_service
from app.services.errors import ServiceError

router = APIRouter(prefix="/groups", tags=["activities"])


@router.get("/{group_id}/activities", response_model=ActivityList)
def list_activities(
    group_id: str,
    session: SessionDep,
    cursor: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 5,
) -> ActivityList:
    try:
        return activities_service.list_activities(
            session,
            group_id,
            cursor=cursor,
            limit=limit,
        )
    except ServiceError as exc:
        raise_service_error(exc)
