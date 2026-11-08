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
from app.services import sync as sync_service

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
    group = groups_service.create_group(session, payload, user_id=user.id, commit=False)
    sync_service.record_group_change(
        session,
        group_id=group.id,
        op_type="create",
        user_id=user.id,
    )
    for p in group.participants:
        sync_service.record_participant_change(
            session,
            group_id=group.id,
            participant_id=p.id,
            op_type="create",
            snapshot=p.model_dump(mode="json"),
            user_id=user.id,
        )
    session.commit()
    return group


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
    prior_participants = (
        groups_service.list_participants(session, group_id)
        if payload.participants is not None
        else None
    )
    group = groups_service.update_group(session, group_id, payload, commit=False)
    sync_service.record_group_change(
        session,
        group_id=group_id,
        op_type="update",
    )
    if prior_participants is not None:
        prior_map = {p.id: p for p in prior_participants}
        current_map = {p.id: p for p in group.participants}
        for p in group.participants:
            if p.id not in prior_map:
                sync_service.record_participant_change(
                    session,
                    group_id=group_id,
                    participant_id=p.id,
                    op_type="create",
                    snapshot=p.model_dump(mode="json"),
                )
            else:
                prior = prior_map[p.id]
                if prior.name != p.name:
                    sync_service.record_participant_change(
                        session,
                        group_id=group_id,
                        participant_id=p.id,
                        op_type="update",
                        snapshot=p.model_dump(mode="json"),
                    )
        for prior_id, prior in prior_map.items():
            if prior_id not in current_map:
                sync_service.record_participant_change(
                    session,
                    group_id=group_id,
                    participant_id=prior_id,
                    op_type="delete",
                    snapshot=prior.model_dump(mode="json"),
                )
    session.commit()
    return group


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
    participant = groups_service.add_participant(session, group_id, payload, commit=False)
    sync_service.record_participant_change(
        session,
        group_id=group_id,
        participant_id=participant.id,
        op_type="create",
        snapshot=participant.model_dump(mode="json"),
    )
    session.commit()
    return participant


@router.patch("/{group_id}/participants/{participant_id}", response_model=ParticipantRead)
def update_participant(
    group_id: str,
    participant_id: str,
    payload: ParticipantUpdate,
    session: SessionDep,
) -> ParticipantRead:
    participant = groups_service.update_participant(
        session, group_id, participant_id, payload, commit=False
    )
    sync_service.record_participant_change(
        session,
        group_id=group_id,
        participant_id=participant.id,
        op_type="update",
        snapshot=participant.model_dump(mode="json"),
    )
    session.commit()
    return participant


@router.delete(
    "/{group_id}/participants/{participant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_participant(
    group_id: str,
    participant_id: str,
    session: SessionDep,
) -> Response:
    sync_service.record_participant_change(
        session,
        group_id=group_id,
        participant_id=participant_id,
        op_type="delete",
    )
    groups_service.delete_participant(session, group_id, participant_id, commit=False)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{group_id}/membership", response_model=UserGroupRead)
def update_membership(
    group_id: str,
    payload: MembershipUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> UserGroupRead:
    membership = groups_service.set_membership(session, group_id, user.id, payload, commit=False)
    sync_service.record_user_group_change(
        session,
        group_id=group_id,
        user_id=user.id,
        op_type="update",
        snapshot=membership.model_dump(mode="json"),
    )
    session.commit()
    return membership


@router.delete("/{group_id}/membership", status_code=status.HTTP_204_NO_CONTENT)
def remove_membership(
    group_id: str,
    user: OptionalUser,
    session: SessionDep,
) -> Response:
    if user:
        sync_service.record_user_group_change(
            session,
            group_id=group_id,
            user_id=user.id,
            op_type="delete",
        )
        groups_service.remove_membership(session, group_id, user.id, commit=False)
        session.commit()
    else:
        groups_service.remove_membership(session, group_id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
