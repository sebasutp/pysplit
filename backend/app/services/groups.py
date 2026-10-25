"""Group, participant and membership business logic."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.enums import ActivityType
from app.core.ids import new_id
from app.models.activity import Activity
from app.models.expense import Expense
from app.models.expense_paid_for import ExpensePaidFor
from app.models.group import Group
from app.models.participant import Participant
from app.models.user_group import UserGroup
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
    ParticipantInput,
    ParticipantRead,
    ParticipantUpdate,
    UserGroupRead,
)
from app.services.errors import ConflictError, InvalidInputError, NotFoundError


def utc_now() -> datetime:
    return datetime.now(UTC)


def _finish(session: Session, commit: bool) -> None:
    """Commit normally, or flush when a caller owns the transaction.

    The synchronization service applies each operation together with its
    change-log row and idempotency record in one transaction, so it passes
    ``commit=False``.
    """
    if commit:
        session.commit()
    else:
        session.flush()


def _participant_read(participant: Participant) -> ParticipantRead:
    return ParticipantRead(
        id=participant.id,
        name=participant.name,
        group_id=participant.group_id,
        updated_at=participant.updated_at,
        version=participant.version,
        deleted_at=participant.deleted_at,
    )


def _membership_read(membership: UserGroup) -> UserGroupRead:
    return UserGroupRead(
        user_id=membership.user_id,
        group_id=membership.group_id,
        is_starred=membership.is_starred,
        is_archived=membership.is_archived,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
        version=membership.version,
    )


def get_active_group(session: Session, group_id: str) -> Group:
    group = session.get(Group, group_id)
    if group is None or group.deleted_at is not None:
        raise NotFoundError("group not found")
    return group


def get_participants(session: Session, group_id: str) -> list[Participant]:
    """Return live participants; synchronization tombstones stay hidden."""
    return list(
        session.exec(
            select(Participant).where(
                Participant.group_id == group_id,
                Participant.deleted_at.is_(None),
            )
        ).all()
    )


def list_participants(session: Session, group_id: str) -> list[ParticipantRead]:
    get_active_group(session, group_id)
    return [_participant_read(participant) for participant in get_participants(session, group_id)]


def find_membership(session: Session, user_id: str, group_id: str) -> UserGroup | None:
    return session.get(UserGroup, (user_id, group_id))


def group_to_read(
    session: Session,
    group: Group,
    *,
    user_id: str | None = None,
    membership: UserGroup | None = None,
    participants_count: int | None = None,
) -> GroupRead:
    participants = get_participants(session, group.id)
    if membership is None and user_id is not None:
        membership = find_membership(session, user_id, group.id)
    return GroupRead(
        id=group.id,
        name=group.name,
        information=group.information,
        currency=group.currency,
        currency_code=group.currency_code,
        created_at=group.created_at,
        updated_at=group.updated_at,
        version=group.version,
        deleted_at=group.deleted_at,
        participants=[_participant_read(participant) for participant in participants],
        participants_count=participants_count
        if participants_count is not None
        else len(participants),
        user_group=_membership_read(membership) if membership else None,
        is_starred=membership.is_starred if membership else False,
        is_archived=membership.is_archived if membership else False,
        isStarred=membership.is_starred if membership else False,
        isArchived=membership.is_archived if membership else False,
    )


def _ensure_membership(
    session: Session,
    user_id: str,
    group_id: str,
    *,
    is_starred: bool | None = None,
    is_archived: bool | None = None,
) -> UserGroup:
    membership = find_membership(session, user_id, group_id)
    now = utc_now()
    if membership is None:
        membership = UserGroup(
            user_id=user_id,
            group_id=group_id,
            is_starred=bool(is_starred),
            is_archived=bool(is_archived),
            created_at=now,
        )
        session.add(membership)
        return membership

    changed = False
    if is_starred is not None and membership.is_starred != is_starred:
        membership.is_starred = is_starred
        changed = True
    if is_archived is not None and membership.is_archived != is_archived:
        membership.is_archived = is_archived
        changed = True
    if changed:
        membership.updated_at = now
        membership.version += 1
        session.add(membership)
    return membership


def _validate_participant_ids(
    session: Session,
    group_id: str,
    participants: list[ParticipantInput],
) -> None:
    existing_ids = {participant.id for participant in get_participants(session, group_id)}
    seen_names: set[str] = set()
    seen_ids: set[str] = set()
    for participant in participants:
        if participant.name in seen_names:
            raise InvalidInputError("duplicateParticipantName", field="participants")
        seen_names.add(participant.name)
        if participant.id is not None:
            if participant.id in seen_ids:
                raise InvalidInputError("duplicate participant id", field="participants")
            seen_ids.add(participant.id)
            if participant.id not in existing_ids and session.get(Participant, participant.id):
                raise InvalidInputError(
                    f"Participant id {participant.id} is already in use.",
                    field="participants",
                )


def create_group(
    session: Session,
    payload: GroupCreate,
    *,
    user_id: str | None = None,
    commit: bool = True,
) -> GroupRead:
    now = utc_now()
    if payload.id:
        existing = session.get(Group, payload.id)
        if existing is not None and existing.deleted_at is None:
            if user_id is not None:
                _ensure_membership(session, user_id, existing.id)
                _finish(session, commit)
            return group_to_read(session, existing, user_id=user_id)
        if existing is not None:
            raise ConflictError("group id is tombstoned")

    group = Group(
        id=payload.id or new_id("grp"),
        name=payload.name,
        information=payload.information,
        currency=payload.currency,
        currency_code=payload.currency_code,
        created_at=now,
        updated_at=now,
        version=1,
    )
    session.add(group)
    session.flush()

    seen_ids: set[str] = set()
    for item in payload.participants:
        participant_id = item.id or new_id("par")
        if participant_id in seen_ids:
            raise InvalidInputError("duplicate participant id", field="participants")
        if session.get(Participant, participant_id) is not None:
            raise ConflictError(f"participant id already exists: {participant_id}")
        seen_ids.add(participant_id)
        session.add(
            Participant(
                id=participant_id,
                name=item.name,
                group_id=group.id,
                updated_at=now,
                version=1,
            )
        )

    if user_id is not None:
        _ensure_membership(session, user_id, group.id)

    _finish(session, commit)
    if commit:
        session.refresh(group)
    return group_to_read(session, group, user_id=user_id)


def list_groups(
    session: Session,
    *,
    ids: list[str] | None = None,
    status: str | None = None,
    user_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> GroupList:
    if ids is not None:
        if not ids:
            return GroupList(items=[], total=0, limit=limit, offset=offset)
        conditions = [Group.id.in_(ids), Group.deleted_at.is_(None)]
        total = int(session.exec(select(func.count()).select_from(Group).where(*conditions)).one())
        groups = list(
            session.exec(
                select(Group)
                .where(*conditions)
                .order_by(Group.name.asc(), Group.created_at.desc(), Group.id.asc())
                .offset(offset)
                .limit(limit)
            ).all()
        )
        memberships: dict[str, UserGroup] = {}
        if user_id is not None and groups:
            membership_rows = session.exec(
                select(UserGroup).where(
                    UserGroup.user_id == user_id,
                    UserGroup.group_id.in_([group.id for group in groups]),
                )
            ).all()
            memberships = {row.group_id: row for row in membership_rows}
        items = [
            group_to_read(session, group, membership=memberships.get(group.id)) for group in groups
        ]
        return GroupList(items=items, total=total, limit=limit, offset=offset)

    if user_id is None:
        return GroupList(items=[], total=0, limit=limit, offset=offset)

    conditions = [UserGroup.user_id == user_id, Group.deleted_at.is_(None)]
    if status == "starred":
        conditions.append(UserGroup.is_starred.is_(True))
    elif status == "archived":
        conditions.append(UserGroup.is_archived.is_(True))

    total = int(
        session.exec(
            select(func.count())
            .select_from(UserGroup)
            .join(Group, Group.id == UserGroup.group_id)
            .where(*conditions)
        ).one()
    )
    rows = session.exec(
        select(Group, UserGroup)
        .join(UserGroup, UserGroup.group_id == Group.id)
        .where(*conditions)
        .order_by(UserGroup.created_at.desc(), Group.name.asc(), Group.id.asc())
        .offset(offset)
        .limit(limit)
    ).all()

    items = [group_to_read(session, group, membership=membership) for group, membership in rows]
    return GroupList(items=items, total=total, limit=limit, offset=offset)


def get_group(
    session: Session,
    group_id: str,
    *,
    user_id: str | None = None,
) -> GroupRead | None:
    group = session.get(Group, group_id)
    if group is None or group.deleted_at is not None:
        return None
    return group_to_read(session, group, user_id=user_id)


def get_group_details(
    session: Session,
    group_id: str,
    *,
    user_id: str | None = None,
) -> GroupDetails:
    from app.services.expenses import materialize_due_recurring_expenses

    materialize_due_recurring_expenses(session, group_id=group_id)
    group = get_active_group(session, group_id)
    participants = get_participants(session, group_id)

    with_expenses: list[str] = []
    seen: set[str] = set()
    expense_rows = session.exec(
        select(Expense)
        .where(Expense.group_id == group_id, Expense.deleted_at.is_(None))
        .order_by(Expense.expense_date.desc(), Expense.created_at.desc(), Expense.id.asc())
    ).all()
    for expense in expense_rows:
        candidates = [expense.paid_by_id]
        paid_for = session.exec(
            select(ExpensePaidFor).where(ExpensePaidFor.expense_id == expense.id)
        ).all()
        candidates.extend(row.participant_id for row in paid_for)
        for participant_id in candidates:
            if participant_id not in seen:
                seen.add(participant_id)
                with_expenses.append(participant_id)

    by_id = {participant.id: participant for participant in participants}
    details = [
        _participant_read(by_id[participant_id])
        for participant_id in with_expenses
        if participant_id in by_id
    ]
    return GroupDetails(
        group=group_to_read(session, group, user_id=user_id),
        participants_with_expenses=with_expenses,
        participants_with_expense_details=details,
        participantsWithExpenses=with_expenses,
    )


def update_group(
    session: Session,
    group_id: str,
    payload: GroupUpdate,
    *,
    commit: bool = True,
) -> GroupRead:
    group = get_active_group(session, group_id)
    now = utc_now()
    fields = payload.model_dump(exclude_unset=True)

    for field in ("name", "information", "currency", "currency_code"):
        if field in fields:
            setattr(group, field, fields[field])

    if payload.participants is not None:
        _validate_participant_ids(session, group_id, payload.participants)
        existing = {
            participant.id: participant for participant in get_participants(session, group_id)
        }
        desired_ids = {item.id for item in payload.participants if item.id is not None}
        for participant_id, participant in existing.items():
            if participant_id not in desired_ids:
                session.delete(participant)
        for item in payload.participants:
            if item.id is None:
                session.add(
                    Participant(
                        id=new_id("par"),
                        name=item.name,
                        group_id=group_id,
                        updated_at=now,
                        version=1,
                    )
                )
            elif item.id not in existing:
                session.add(
                    Participant(
                        id=item.id,
                        name=item.name,
                        group_id=group_id,
                        updated_at=now,
                        version=1,
                    )
                )
            else:
                participant = existing[item.id]
                if participant.name != item.name:
                    participant.name = item.name
                    participant.updated_at = now
                    participant.version += 1
                    session.add(participant)

    group.updated_at = now
    group.version += 1
    session.add(group)
    session.add(
        Activity(
            id=new_id("act"),
            group_id=group_id,
            time=now,
            activity_type=ActivityType.UPDATE_GROUP.value,
            participant_id=payload.participant_id,
        )
    )
    _finish(session, commit)
    if commit:
        session.refresh(group)
    return group_to_read(session, group)


def add_participant(
    session: Session,
    group_id: str,
    payload: ParticipantCreate,
    *,
    commit: bool = True,
) -> ParticipantRead:
    group = get_active_group(session, group_id)
    participants = get_participants(session, group_id)
    if any(participant.name == payload.name for participant in participants):
        raise InvalidInputError("duplicateParticipantName", field="name")
    participant_id = payload.id or new_id("par")
    if session.get(Participant, participant_id) is not None:
        raise ConflictError(f"participant id already exists: {participant_id}")
    now = utc_now()
    participant = Participant(
        id=participant_id,
        name=payload.name,
        group_id=group.id,
        updated_at=now,
        version=1,
    )
    session.add(participant)
    group.updated_at = now
    group.version += 1
    session.add(group)
    _finish(session, commit)
    if commit:
        session.refresh(participant)
    return _participant_read(participant)


def update_participant(
    session: Session,
    group_id: str,
    participant_id: str,
    payload: ParticipantUpdate,
    *,
    commit: bool = True,
) -> ParticipantRead:
    group = get_active_group(session, group_id)
    participant = session.get(Participant, participant_id)
    if participant is None or participant.group_id != group_id:
        raise NotFoundError("participant not found")
    duplicate = session.exec(
        select(Participant).where(
            Participant.group_id == group_id,
            Participant.name == payload.name,
            Participant.id != participant_id,
        )
    ).first()
    if duplicate is not None:
        raise InvalidInputError("duplicateParticipantName", field="name")
    now = utc_now()
    participant.name = payload.name
    participant.updated_at = now
    participant.version += 1
    group.updated_at = now
    group.version += 1
    session.add(participant)
    session.add(group)
    _finish(session, commit)
    if commit:
        session.refresh(participant)
    return _participant_read(participant)


def delete_participant(
    session: Session,
    group_id: str,
    participant_id: str,
    *,
    commit: bool = True,
) -> None:
    group = get_active_group(session, group_id)
    participant = session.get(Participant, participant_id)
    if participant is None or participant.group_id != group_id:
        raise NotFoundError("participant not found")
    now = utc_now()
    session.delete(participant)
    group.updated_at = now
    group.version += 1
    session.add(group)
    _finish(session, commit)


def _sync_group_ids(payload: GroupSyncRequest) -> list[str]:
    return payload.group_ids or payload.local_group_ids


def sync_groups(
    session: Session,
    payload: GroupSyncRequest,
    *,
    user_id: str | None,
) -> GroupSyncResponse:
    local_ids = _sync_group_ids(payload)
    if user_id is None:
        groups = (
            session.exec(
                select(Group)
                .where(Group.id.in_(local_ids), Group.deleted_at.is_(None))
                .order_by(Group.name.asc(), Group.created_at.desc(), Group.id.asc())
            ).all()
            if local_ids
            else []
        )
        items = [
            group_to_read(
                session,
                group,
                membership=UserGroup(
                    user_id="",
                    group_id=group.id,
                    is_starred=group.id in payload.starred_group_ids,
                    is_archived=group.id in payload.archived_group_ids,
                    created_at=group.created_at,
                ),
            )
            for group in groups
        ]
        for item in items:
            item.user_group = None
            item.is_starred = item.id in payload.starred_group_ids
            item.is_archived = item.id in payload.archived_group_ids
            item.isStarred = item.is_starred
            item.isArchived = item.is_archived
        return GroupSyncResponse(
            is_authenticated=False,
            groups=items,
            user_groups=[],
            isAuthenticated=False,
        )

    if local_ids:
        existing_groups = session.exec(
            select(Group).where(Group.id.in_(local_ids), Group.deleted_at.is_(None))
        ).all()
        for group in existing_groups:
            existing = find_membership(session, user_id, group.id)
            _ensure_membership(
                session,
                user_id,
                group.id,
                is_starred=(
                    True
                    if group.id in payload.starred_group_ids
                    else (None if existing is not None else False)
                ),
                is_archived=(
                    True
                    if group.id in payload.archived_group_ids
                    else (None if existing is not None else False)
                ),
            )
        session.commit()

    rows = session.exec(
        select(Group, UserGroup)
        .join(UserGroup, UserGroup.group_id == Group.id)
        .where(UserGroup.user_id == user_id, Group.deleted_at.is_(None))
        .order_by(UserGroup.created_at.desc(), Group.id.asc())
    ).all()

    items: list[GroupRead] = []
    user_groups: list[UserGroupRead] = []
    for group, membership in rows:
        items.append(group_to_read(session, group, membership=membership))
        user_groups.append(_membership_read(membership))
    return GroupSyncResponse(
        is_authenticated=True,
        groups=items,
        user_groups=user_groups,
        isAuthenticated=True,
    )


def record_access(session: Session, group_id: str, *, user_id: str | None) -> None:
    if user_id is None:
        return
    group = session.get(Group, group_id)
    if group is None or group.deleted_at is not None:
        return
    _ensure_membership(session, user_id, group_id)
    session.commit()


def set_membership(
    session: Session,
    group_id: str,
    user_id: str,
    payload: MembershipUpdate,
) -> UserGroupRead:
    get_active_group(session, group_id)
    membership = _ensure_membership(
        session,
        user_id,
        group_id,
        is_starred=payload.is_starred,
        is_archived=payload.is_archived,
    )
    session.commit()
    session.refresh(membership)
    return _membership_read(membership)


def remove_membership(session: Session, group_id: str, user_id: str | None) -> None:
    if user_id is None:
        return
    membership = find_membership(session, user_id, group_id)
    if membership is not None:
        session.delete(membership)
        session.commit()


def group_payload_for_sync(group: GroupRead) -> dict[str, Any]:
    """Small helper used by tests and future repository adapters."""
    return group.model_dump(mode="json")
