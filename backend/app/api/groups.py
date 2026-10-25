"""Group, participant and membership HTTP endpoints."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import (
    CurrentUser,
    GroupCreatorUser,
    OptionalUser,
    SessionDep,
)
from app.schemas.groups import (
    GroupCreate,
    GroupDetails,
    GroupList,
    GroupRead,
    GroupSyncRequest,
    GroupSyncResponse,
    GroupUpdate,
    MembershipUpdate,
    ParticipantCreate,
    ParticipantRead,
    ParticipantUpdate,
    UserGroupRead,
)
from app.services import groups as groups_service

router = APIRouter(prefix="/groups", tags=["groups"])

LimitQuery = Annotated[int, Query(ge=1, le=200)]
OffsetQuery = Annotated[int, Query(ge=0)]
StatusQuery = Literal["recent", "starred", "archived", "all"]


def _group_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="group not found")


def _parse_ids(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


@router.post("/sync", response_model=GroupSyncResponse)
def sync_groups(
    payload: GroupSyncRequest,
    user: OptionalUser,
    session: SessionDep,
) -> GroupSyncResponse:
    return groups_service.sync_groups(
        session,
        payload,
        user_id=user.id if user else None,
    )


@router.get("", response_model=GroupList)
def list_groups(
    user: OptionalUser,
    session: SessionDep,
    ids: Annotated[str | None, Query()] = None,
    status_filter: Annotated[StatusQuery | None, Query(alias="status")] = None,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
) -> GroupList:
    return groups_service.list_groups(
        session,
        ids=_parse_ids(ids),
        status=status_filter,
        user_id=user.id if user else None,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: GroupCreate,
    user: GroupCreatorUser,
    session: SessionDep,
) -> GroupRead:
    return groups_service.create_group(session, payload, user_id=user.id)


@router.get("/{group_id}", response_model=GroupRead)
def get_group(
    group_id: str,
    user: OptionalUser,
    session: SessionDep,
) -> GroupRead:
    group = groups_service.get_group(
        session,
        group_id,
        user_id=user.id if user else None,
    )
    if group is None:
        raise _group_not_found()
    return group


@router.get("/{group_id}/details", response_model=GroupDetails)
def get_group_details(
    group_id: str,
    user: OptionalUser,
    session: SessionDep,
) -> GroupDetails:
    return groups_service.get_group_details(
        session,
        group_id,
        user_id=user.id if user else None,
    )


@router.patch("/{group_id}", response_model=GroupRead)
def update_group(
    group_id: str,
    payload: GroupUpdate,
    session: SessionDep,
) -> GroupRead:
    return groups_service.update_group(session, group_id, payload)


@router.post("/{group_id}/access", status_code=status.HTTP_204_NO_CONTENT)
def record_access(
    group_id: str,
    user: OptionalUser,
    session: SessionDep,
) -> Response:
    groups_service.record_access(session, group_id, user_id=user.id if user else None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{group_id}/participants", response_model=list[ParticipantRead])
def list_participants(
    group_id: str,
    session: SessionDep,
) -> list[ParticipantRead]:
    return groups_service.list_participants(session, group_id)


@router.post(
    "/{group_id}/participants",
    response_model=ParticipantRead,
    status_code=status.HTTP_201_CREATED,
)
def add_participant(
    group_id: str,
    payload: ParticipantCreate,
    session: SessionDep,
) -> ParticipantRead:
    return groups_service.add_participant(session, group_id, payload)


@router.patch("/{group_id}/participants/{participant_id}", response_model=ParticipantRead)
def update_participant(
    group_id: str,
    participant_id: str,
    payload: ParticipantUpdate,
    session: SessionDep,
) -> ParticipantRead:
    return groups_service.update_participant(session, group_id, participant_id, payload)


@router.delete(
    "/{group_id}/participants/{participant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_participant(
    group_id: str,
    participant_id: str,
    session: SessionDep,
) -> Response:
    groups_service.delete_participant(session, group_id, participant_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{group_id}/membership", response_model=UserGroupRead)
def update_membership(
    group_id: str,
    payload: MembershipUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> UserGroupRead:
    return groups_service.set_membership(session, group_id, user.id, payload)


@router.delete("/{group_id}/membership", status_code=status.HTTP_204_NO_CONTENT)
def remove_membership(
    group_id: str,
    user: OptionalUser,
    session: SessionDep,
) -> Response:
    groups_service.remove_membership(session, group_id, user.id if user else None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
