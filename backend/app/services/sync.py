"""Server-side offline synchronization protocol (plan §2.5 and ADR 0002).

The service owns four responsibilities:

* validate the explicit entity/field whitelists in a push envelope;
* apply one operation and append its change-log row in the same transaction;
* remember operation results for seven days so retries are idempotent;
* serve full-snapshot pulls and bootstrap snapshots with a validated cursor.

Routers stay HTTP-only; this module is the only place that knows how an
``entity_type`` maps to a domain table.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, delete, func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.config import Settings, get_settings
from app.core.enums import can_create_groups
from app.models.activity import Activity
from app.models.base import utc_now
from app.models.expense import Expense
from app.models.group import Group
from app.models.participant import Participant
from app.models.receipt import Receipt
from app.models.receipt_item import ReceiptItem
from app.models.receipt_item_portion import ReceiptItemPortion
from app.models.receipt_opt_out import ReceiptOptOut
from app.models.sync_change import SyncChange
from app.models.sync_operation import SyncOperation
from app.models.user import User
from app.models.user_group import UserGroup
from app.schemas.activities import ActivityRead
from app.schemas.categories import CategoryRead
from app.schemas.common import iso_z
from app.schemas.expenses import ExpenseCreate, ExpenseUpdate
from app.schemas.groups import (
    GroupCreate,
    GroupRead,
    GroupUpdate,
    ParticipantCreate,
    ParticipantRead,
    ParticipantUpdate,
)
from app.schemas.sync import (
    SyncBootstrapResponse,
    SyncChangeRead,
    SyncOperationIn,
    SyncPullRequest,
    SyncPullResponse,
    SyncPushResponse,
    SyncPushResult,
    SyncReceiptSnapshot,
)
from app.services import categories as categories_service
from app.services import expenses as expenses_service
from app.services import groups as groups_service
from app.services.errors import ConflictError, NotFoundError, ServiceError

# ---------------------------------------------------------------------------
# Public whitelists
# ---------------------------------------------------------------------------

# Only these entity types may travel through the outbox. Receipt entities are
# added in Stage 7 without changing the envelope or the push/pull contract.
ENTITY_FIELDS: dict[str, dict[str, frozenset[str]]] = {
    "group": {
        "create": frozenset({"name", "information", "currency", "currency_code", "participants"}),
        "update": frozenset({"name", "information", "currency", "currency_code"}),
    },
    "participant": {
        "create": frozenset({"name"}),
        "update": frozenset({"name"}),
        "delete": frozenset(),
    },
    "expense": {
        "create": frozenset(
            {
                "expense_date",
                "title",
                "category_id",
                "amount",
                "original_amount",
                "original_currency",
                "conversion_rate",
                "paid_by_id",
                "is_reimbursement",
                "split_mode",
                "notes",
                "recurrence_rule",
                "paid_for",
                "documents",
                "participant_id",
            }
        ),
        "update": frozenset(
            {
                "expense_date",
                "title",
                "category_id",
                "amount",
                "original_amount",
                "original_currency",
                "conversion_rate",
                "paid_by_id",
                "is_reimbursement",
                "split_mode",
                "notes",
                "recurrence_rule",
                "paid_for",
                "documents",
                "participant_id",
            }
        ),
        "delete": frozenset(),
    },
    "user_group": {
        "create": frozenset({"is_starred", "is_archived"}),
        "update": frozenset({"is_starred", "is_archived"}),
        "delete": frozenset(),
    },
}

NESTED_FIELDS: dict[str, frozenset[str]] = {
    "participants": frozenset({"id", "name"}),
    "paid_for": frozenset({"participant_id", "shares", "amount", "percentage"}),
    "documents": frozenset({"id", "url", "width", "height"}),
}


# ---------------------------------------------------------------------------
# Errors and internal outcomes
# ---------------------------------------------------------------------------


class SyncError(Exception):
    """A per-operation validation or authorization failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class SyncConflict(Exception):
    """The client's base version no longer matches the server row."""

    def __init__(self, server_entity: dict[str, Any], version: int | None) -> None:
        super().__init__("version conflict")
        self.server_entity = server_entity
        self.version = version


class CursorExpiredError(ConflictError):
    """The requested cursor predates the retained change log."""


@dataclass(frozen=True)
class _Change:
    group_id: str
    entity_type: str
    entity_id: str
    op_type: str
    snapshot: dict[str, Any]


@dataclass
class _Outcome:
    changes: list[_Change] = field(default_factory=list)
    duplicate: bool = False


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _group_snapshot(
    session: Session,
    group: Group,
    *,
    user_id: str | None = None,
) -> dict[str, Any]:
    read = groups_service.group_to_read(session, group, user_id=user_id)
    data = read.model_dump(mode="json")
    for key in (
        "user_group",
        "is_starred",
        "is_archived",
        "isStarred",
        "isArchived",
    ):
        data.pop(key, None)
    return data


def _participant_snapshot(participant: Participant) -> dict[str, Any]:
    return ParticipantRead(
        id=participant.id,
        name=participant.name,
        group_id=participant.group_id,
        updated_at=participant.updated_at,
        version=participant.version,
        deleted_at=participant.deleted_at,
    ).model_dump(mode="json")


def _expense_snapshot(session: Session, expense: Expense) -> dict[str, Any]:
    return expenses_service.expense_to_read(session, expense).model_dump(mode="json")


def _membership_snapshot(membership: UserGroup) -> dict[str, Any]:
    return {
        "user_id": membership.user_id,
        "group_id": membership.group_id,
        "is_starred": membership.is_starred,
        "is_archived": membership.is_archived,
        "created_at": iso_z(membership.created_at),
        "updated_at": iso_z(membership.updated_at),
        "version": membership.version,
        "deleted_at": iso_z(membership.deleted_at) if membership.deleted_at else None,
    }


def _receipt_snapshot(session: Session, receipt: Receipt) -> SyncReceiptSnapshot:
    items = list(
        session.exec(
            select(ReceiptItem)
            .where(ReceiptItem.receipt_id == receipt.id)
            .order_by(ReceiptItem.position.asc(), ReceiptItem.id.asc())
        ).all()
    )
    item_ids = [item.id for item in items]
    portions: list[ReceiptItemPortion] = []
    if item_ids:
        portions = list(
            session.exec(
                select(ReceiptItemPortion)
                .where(ReceiptItemPortion.item_id.in_(item_ids))
                .order_by(ReceiptItemPortion.created_at.asc(), ReceiptItemPortion.id.asc())
            ).all()
        )
    opt_outs = list(
        session.exec(select(ReceiptOptOut).where(ReceiptOptOut.receipt_id == receipt.id)).all()
    )
    return SyncReceiptSnapshot(
        receipt={
            "id": receipt.id,
            "group_id": receipt.group_id,
            "image_url": receipt.image_url,
            "image_width": receipt.image_width,
            "image_height": receipt.image_height,
            "status": receipt.status,
            "merchant": receipt.merchant,
            "receipt_date": iso_z(receipt.receipt_date) if receipt.receipt_date else None,
            "currency_code": receipt.currency_code,
            "total": receipt.total,
            "expense_id": receipt.expense_id,
            "created_at": iso_z(receipt.created_at),
            "updated_at": iso_z(receipt.updated_at),
            "version": receipt.version,
            "deleted_at": iso_z(receipt.deleted_at) if receipt.deleted_at else None,
        },
        items=[
            {
                "id": item.id,
                "receipt_id": item.receipt_id,
                "name": item.name,
                "quantity_milli": item.quantity_milli,
                "unit_price": item.unit_price,
                "amount": item.amount,
                "is_shared": item.is_shared,
                "is_adjustment": item.is_adjustment,
                "position": item.position,
                "created_at": iso_z(item.created_at),
                "updated_at": iso_z(item.updated_at),
                "version": item.version,
                "deleted_at": iso_z(item.deleted_at) if item.deleted_at else None,
            }
            for item in items
        ],
        portions=[
            {
                "id": portion.id,
                "item_id": portion.item_id,
                "target": portion.target,
                "participant_id": portion.participant_id,
                "quantity_milli": portion.quantity_milli,
                "created_at": iso_z(portion.created_at),
                "updated_at": iso_z(portion.updated_at),
                "version": portion.version,
                "deleted_at": iso_z(portion.deleted_at) if portion.deleted_at else None,
            }
            for portion in portions
        ],
        opt_outs=[
            {
                "id": opt_out.id,
                "receipt_id": opt_out.receipt_id,
                "participant_id": opt_out.participant_id,
                "created_at": iso_z(opt_out.created_at),
                "updated_at": iso_z(opt_out.updated_at),
                "version": opt_out.version,
                "deleted_at": iso_z(opt_out.deleted_at) if opt_out.deleted_at else None,
            }
            for opt_out in opt_outs
        ],
    )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _check_fields(
    entity_type: str,
    op_type: str,
    payload: dict[str, Any],
) -> frozenset[str]:
    allowed = ENTITY_FIELDS.get(entity_type, {}).get(op_type)
    if allowed is None:
        raise SyncError(
            "unknown_entity" if entity_type not in ENTITY_FIELDS else "unsupported_operation",
            f"Unsupported operation {op_type!r} for entity {entity_type!r}.",
        )
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise SyncError("unknown_field", f"Unknown fields for {entity_type}: {', '.join(unknown)}")
    for key, nested_allowed in NESTED_FIELDS.items():
        value = payload.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            raise SyncError("validation_error", f"{key} must be an array")
        for entry in value:
            if not isinstance(entry, dict):
                raise SyncError("validation_error", f"{key} entries must be objects")
            unknown_nested = sorted(set(entry) - nested_allowed)
            if unknown_nested:
                raise SyncError(
                    "unknown_field",
                    f"Unknown fields in {key}: {', '.join(unknown_nested)}",
                )
    return allowed


def _validation_detail(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "invalid payload"
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", ()))
    message = str(first.get("msg", "invalid value"))
    return f"{location}: {message}" if location else message


def _require_base_version(operation: SyncOperationIn) -> int:
    if operation.base_version is None:
        raise SyncError("base_version_required", "base_version is required for this operation")
    return operation.base_version


def _require_group(session: Session, group_id: str) -> Group:
    group = session.get(Group, group_id)
    if group is None or group.deleted_at is not None:
        raise SyncError("not_found", "group not found")
    return group


def _assert_same_group(entity_group_id: str, operation: SyncOperationIn) -> None:
    if entity_group_id != operation.group_id:
        raise SyncError("cross_group", "entity does not belong to the supplied group")


def _conflict(session: Session, entity_type: str, row: Any) -> SyncConflict:
    if entity_type == "expense":
        snapshot = _expense_snapshot(session, row)
    elif entity_type == "participant":
        snapshot = _participant_snapshot(row)
    elif entity_type == "group":
        snapshot = _group_snapshot(session, row)
    else:  # pragma: no cover - only used for entities with conflict rules
        snapshot = {}
    return SyncConflict(snapshot, getattr(row, "version", None))


# ---------------------------------------------------------------------------
# Entity apply functions
# ---------------------------------------------------------------------------


def _apply_group(
    session: Session,
    operation: SyncOperationIn,
    *,
    user_id: str | None,
    now: datetime,
) -> _Outcome:
    if operation.group_id != operation.entity_id:
        raise SyncError("cross_group", "group operations must target their own group")
    existing = session.get(Group, operation.entity_id)

    if operation.op_type == "create":
        if user_id is None:
            raise SyncError("forbidden", "sign in to create a group")
        user = session.get(User, user_id)
        if user is None or not can_create_groups(user.tier):
            raise SyncError("forbidden", "your tier cannot create groups")
        if existing is not None:
            if existing.deleted_at is not None:
                raise _conflict(session, "group", existing)
            return _Outcome(duplicate=True)
        try:
            payload = GroupCreate.model_validate({**operation.payload, "id": operation.entity_id})
        except ValidationError as exc:
            raise SyncError("validation_error", _validation_detail(exc)) from exc
        group_read = groups_service.create_group(session, payload, user_id=user_id, commit=False)
        snapshot = {
            key: value
            for key, value in group_read.model_dump(mode="json").items()
            if key
            not in {
                "user_group",
                "is_starred",
                "is_archived",
                "isStarred",
                "isArchived",
            }
        }
        changes = [
            _Change(group_read.id, "group", group_read.id, "create", snapshot),
        ]
        for participant in group_read.participants:
            changes.append(
                _Change(
                    group_read.id,
                    "participant",
                    participant.id,
                    "create",
                    participant.model_dump(mode="json"),
                )
            )
        return _Outcome(changes=changes)

    if existing is None:
        raise SyncError("not_found", "group not found")
    if existing.deleted_at is not None:
        raise _conflict(session, "group", existing)

    _require_base_version(operation)
    try:
        payload = GroupUpdate.model_validate(operation.payload)
    except ValidationError as exc:
        raise SyncError("validation_error", _validation_detail(exc)) from exc
    # Group metadata follows last-writer-wins; a stale base_version is safe.
    group_read = groups_service.update_group(session, operation.group_id, payload, commit=False)
    snapshot = {
        key: value
        for key, value in group_read.model_dump(mode="json").items()
        if key
        not in {
            "user_group",
            "is_starred",
            "is_archived",
            "isStarred",
            "isArchived",
        }
    }
    return _Outcome(changes=[_Change(group_read.id, "group", group_read.id, "update", snapshot)])


def _apply_participant(
    session: Session,
    operation: SyncOperationIn,
    *,
    user_id: str | None,
    now: datetime,
) -> _Outcome:
    group = _require_group(session, operation.group_id)
    existing = session.get(Participant, operation.entity_id)
    if existing is not None and existing.group_id != group.id:
        raise SyncError("cross_group", "participant belongs to another group")

    if operation.op_type == "create":
        if existing is not None:
            if existing.deleted_at is not None:
                raise _conflict(session, "participant", existing)
            return _Outcome(duplicate=True)
        try:
            payload = ParticipantCreate.model_validate(
                {"id": operation.entity_id, **operation.payload}
            )
        except ValidationError as exc:
            raise SyncError("validation_error", _validation_detail(exc)) from exc
        participant = groups_service.add_participant(session, group.id, payload, commit=False)
        return _Outcome(
            changes=[
                _Change(
                    group.id,
                    "participant",
                    participant.id,
                    "create",
                    participant.model_dump(mode="json"),
                )
            ]
        )

    if existing is None:
        raise SyncError("not_found", "participant not found")

    if operation.op_type == "update":
        if existing.deleted_at is not None:
            raise _conflict(session, "participant", existing)
        _require_base_version(operation)
        try:
            payload = ParticipantUpdate.model_validate(operation.payload)
        except ValidationError as exc:
            raise SyncError("validation_error", _validation_detail(exc)) from exc
        # Participant names follow last-writer-wins.
        participant = groups_service.update_participant(
            session, group.id, operation.entity_id, payload, commit=False
        )
        return _Outcome(
            changes=[
                _Change(
                    group.id,
                    "participant",
                    participant.id,
                    "update",
                    participant.model_dump(mode="json"),
                )
            ]
        )

    # delete
    _require_base_version(operation)
    if existing.deleted_at is not None:
        return _Outcome(duplicate=True)
    existing.deleted_at = now
    existing.updated_at = now
    existing.version += 1
    group.updated_at = now
    group.version += 1
    session.add(existing)
    session.add(group)
    session.flush()
    return _Outcome(
        changes=[
            _Change(
                group.id,
                "participant",
                existing.id,
                "delete",
                _participant_snapshot(existing),
            )
        ]
    )


def _apply_expense(
    session: Session,
    operation: SyncOperationIn,
    *,
    user_id: str | None,
    now: datetime,
) -> _Outcome:
    group = _require_group(session, operation.group_id)
    existing = session.get(Expense, operation.entity_id)
    if existing is not None:
        _assert_same_group(existing.group_id, operation)

    if operation.op_type == "create":
        if existing is not None:
            if existing.deleted_at is not None:
                raise _conflict(session, "expense", existing)
            return _Outcome(duplicate=True)
        try:
            payload = ExpenseCreate.model_validate({**operation.payload, "id": operation.entity_id})
        except ValidationError as exc:
            raise SyncError("validation_error", _validation_detail(exc)) from exc
        expense_read = expenses_service.create_expense(
            session,
            group.id,
            payload,
            now=now,
            commit=False,
        )
        return _Outcome(
            changes=[
                _Change(
                    group.id,
                    "expense",
                    expense_read.id,
                    "create",
                    expense_read.model_dump(mode="json"),
                )
            ]
        )

    if existing is None:
        raise SyncError("not_found", "expense not found")
    base_version = _require_base_version(operation)

    if operation.op_type == "update":
        if existing.deleted_at is not None:
            raise _conflict(session, "expense", existing)
        if existing.version != base_version:
            raise _conflict(session, "expense", existing)
        try:
            payload = ExpenseUpdate.model_validate(operation.payload)
        except ValidationError as exc:
            raise SyncError("validation_error", _validation_detail(exc)) from exc
        expense_read = expenses_service.update_expense(
            session,
            group.id,
            operation.entity_id,
            payload,
            now=now,
            commit=False,
        )
        return _Outcome(
            changes=[
                _Change(
                    group.id,
                    "expense",
                    expense_read.id,
                    "update",
                    expense_read.model_dump(mode="json"),
                )
            ]
        )

    # delete: tombstones win, and a stale delete never removes a newer edit.
    if existing.deleted_at is not None:
        if existing.version != base_version:
            raise _conflict(session, "expense", existing)
        return _Outcome(duplicate=True)
    if existing.version != base_version:
        raise _conflict(session, "expense", existing)
    expenses_service.delete_expense(
        session,
        group.id,
        operation.entity_id,
        now=now,
        commit=False,
    )
    session.flush()
    snapshot = _expense_snapshot(session, existing)
    return _Outcome(changes=[_Change(group.id, "expense", existing.id, "delete", snapshot)])


def _apply_user_group(
    session: Session,
    operation: SyncOperationIn,
    *,
    user_id: str | None,
    now: datetime,
) -> _Outcome:
    if user_id is None:
        raise SyncError("forbidden", "sign in to synchronize group membership")
    if operation.entity_id != operation.group_id:
        raise SyncError("cross_group", "membership operations must target their group")
    group = _require_group(session, operation.group_id)
    membership = session.get(UserGroup, (user_id, group.id))

    if operation.op_type == "delete":
        _require_base_version(operation)
        if membership is None:
            return _Outcome(duplicate=True)
        snapshot = {
            "user_id": user_id,
            "group_id": group.id,
            "is_starred": membership.is_starred,
            "is_archived": membership.is_archived,
            "created_at": iso_z(membership.created_at),
            "updated_at": iso_z(now),
            "version": membership.version + 1,
            "deleted_at": iso_z(now),
        }
        session.delete(membership)
        session.flush()
        return _Outcome(changes=[_Change(group.id, "user_group", group.id, "delete", snapshot)])

    if operation.op_type == "update":
        _require_base_version(operation)
    try:
        payload = _MembershipPayload.model_validate(operation.payload)
    except ValidationError as exc:
        raise SyncError("validation_error", _validation_detail(exc)) from exc

    # A group is either starred or archived, never both. Archive wins when a
    # stale client sends both positive flags; setting either one clears the
    # other. This keeps a guest archive from leaving another device's star set.
    is_starred = payload.is_starred
    is_archived = payload.is_archived
    if is_archived is True:
        is_starred = False
    elif is_starred is True:
        is_archived = False

    changed = False
    if membership is None:
        membership = UserGroup(
            user_id=user_id,
            group_id=group.id,
            is_starred=bool(is_starred),
            is_archived=bool(is_archived),
            created_at=now,
            updated_at=now,
            version=1,
        )
        changed = True
    else:
        if is_starred is not None and membership.is_starred != is_starred:
            membership.is_starred = is_starred
            changed = True
        if is_archived is not None and membership.is_archived != is_archived:
            membership.is_archived = is_archived
            changed = True
        if changed:
            membership.updated_at = now
            membership.version += 1
    if changed:
        session.add(membership)
        session.flush()
        return _Outcome(
            changes=[
                _Change(
                    group.id,
                    "user_group",
                    group.id,
                    operation.op_type,
                    _membership_snapshot(membership),
                )
            ]
        )
    return _Outcome(duplicate=True)


class _MembershipPayload(BaseModel):
    is_starred: bool | None = None
    is_archived: bool | None = None


_APPLIERS: dict[
    str,
    Callable[..., _Outcome],
] = {
    "group": _apply_group,
    "participant": _apply_participant,
    "expense": _apply_expense,
    "user_group": _apply_user_group,
}


def _apply_operation(
    session: Session,
    operation: SyncOperationIn,
    *,
    user_id: str | None,
    now: datetime,
) -> _Outcome:
    if operation.entity_type not in ENTITY_FIELDS:
        raise SyncError("unknown_entity", f"Unknown entity type: {operation.entity_type}")
    _check_fields(operation.entity_type, operation.op_type, operation.payload)
    if operation.entity_type == "user_group" and user_id is None:
        raise SyncError("forbidden", "sign in to synchronize group membership")
    if (
        operation.op_type in {"update", "delete"}
        and operation.base_version is None
        and operation.entity_type != "group"
    ):
        # Group updates are last-writer-wins, but the envelope still requires a
        # base version so the client is explicit about what it last saw.
        raise SyncError("base_version_required", "base_version is required for this operation")
    applier = _APPLIERS[operation.entity_type]
    return applier(session, operation, user_id=user_id, now=now)


# ---------------------------------------------------------------------------
# Change log, idempotency and compaction
# ---------------------------------------------------------------------------


def _append_change(
    session: Session,
    *,
    change: _Change,
    user_id: str | None,
    now: datetime,
) -> int:
    row = SyncChange(
        group_id=change.group_id,
        entity_type=change.entity_type,
        entity_id=change.entity_id,
        op_type=change.op_type,
        payload_json=json.dumps(change.snapshot, sort_keys=True, separators=(",", ":")),
        user_id=user_id,
        changed_at=now,
    )
    session.add(row)
    session.flush()
    assert row.seq is not None
    return int(row.seq)


def _entity_latest_seq(session: Session, entity_type: str, entity_id: str) -> int | None:
    row = session.exec(
        select(SyncChange)
        .where(SyncChange.entity_type == entity_type, SyncChange.entity_id == entity_id)
        .order_by(SyncChange.seq.desc())
    ).first()
    return int(row.seq) if row is not None and row.seq is not None else None


def _duplicate_snapshot(
    session: Session, operation: SyncOperationIn, user_id: str | None = None
) -> dict[str, Any] | None:
    if operation.entity_type == "group":
        row = session.get(Group, operation.entity_id)
        return _group_snapshot(session, row) if row is not None else None
    if operation.entity_type == "participant":
        row = session.get(Participant, operation.entity_id)
        return _participant_snapshot(row) if row is not None else None
    if operation.entity_type == "expense":
        row = session.get(Expense, operation.entity_id)
        return _expense_snapshot(session, row) if row is not None else None
    if operation.entity_type == "user_group" and user_id is not None:
        row = session.get(UserGroup, (user_id, operation.entity_id))
        return _membership_snapshot(row) if row is not None else None
    return None


def _current_cursor(session: Session) -> int:
    value = session.exec(select(func.max(SyncChange.seq))).one()
    return int(value) if value is not None else 0


def _compaction_floor(session: Session) -> int:
    marker = session.exec(
        select(SyncChange)
        .where(
            SyncChange.entity_type == "sync_meta",
            SyncChange.entity_id == "change_log",
        )
        .order_by(SyncChange.seq.desc())
    ).first()
    if marker is None or marker.payload_json is None:
        return 0
    try:
        payload = json.loads(marker.payload_json)
        return int(payload.get("compacted_through", 0))
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0


def compact_sync_state(
    session: Session,
    *,
    now: datetime | None = None,
    settings: Settings | None = None,
    commit: bool = True,
) -> int:
    """Delete expired idempotency rows and change-log rows.

    A ``sync_meta`` marker records the highest compacted sequence number so a
    client whose cursor predates the retained window is told to bootstrap
    instead of silently missing changes.
    """
    active = settings or get_settings()
    moment = now or utc_now()
    cutoff = moment - timedelta(days=active.sync_change_retention_days)
    operation_cutoff = moment

    session.execute(delete(SyncOperation).where(SyncOperation.expires_at < operation_cutoff))

    old_max_value = session.exec(
        select(func.max(SyncChange.seq)).where(
            SyncChange.changed_at < cutoff,
            SyncChange.entity_type != "sync_meta",
        )
    ).one()
    if old_max_value is None:
        if commit:
            session.commit()
        else:
            session.flush()
        return 0

    old_max = int(old_max_value)
    previous_floor = _compaction_floor(session)
    floor = max(previous_floor, old_max)
    result = session.execute(
        delete(SyncChange).where(
            SyncChange.changed_at < cutoff,
            SyncChange.entity_type != "sync_meta",
        )
    )
    deleted = int(result.rowcount or 0)
    session.add(
        SyncChange(
            group_id=None,
            entity_type="sync_meta",
            entity_id="change_log",
            op_type="compaction",
            payload_json=json.dumps({"compacted_through": floor}, sort_keys=True),
            user_id=None,
            changed_at=moment,
        )
    )
    if commit:
        session.commit()
    else:
        session.flush()
    return deleted


def _remember_result(
    session: Session,
    operation: SyncOperationIn,
    *,
    user_id: str | None,
    result: dict[str, Any],
    now: datetime,
    settings: Settings,
) -> None:
    expires_at = now + timedelta(days=settings.sync_operation_retention_days)
    existing = session.get(SyncOperation, operation.op_id)
    if existing is None:
        session.add(
            SyncOperation(
                op_id=operation.op_id,
                user_id=user_id,
                applied_at=now,
                expires_at=expires_at,
                result_json=json.dumps(result, sort_keys=True, separators=(",", ":")),
            )
        )
    else:
        existing.result_json = json.dumps(result, sort_keys=True, separators=(",", ":"))
        existing.expires_at = expires_at
        existing.user_id = user_id
    session.commit()


def _process_operation(
    session: Session,
    operation: SyncOperationIn,
    *,
    user_id: str | None,
    settings: Settings,
    now: datetime,
) -> SyncPushResult:
    remembered = session.get(SyncOperation, operation.op_id)
    if remembered is not None:
        if remembered.expires_at > now:
            return SyncPushResult.model_validate(json.loads(remembered.result_json))
        session.delete(remembered)
        session.commit()

    try:
        outcome = _apply_operation(session, operation, user_id=user_id, now=now)
        seq: int | None = None
        for index, change in enumerate(outcome.changes):
            change_seq = _append_change(session, change=change, user_id=user_id, now=now)
            if index == 0:
                seq = change_seq
        if outcome.duplicate and seq is None:
            seq = _entity_latest_seq(session, operation.entity_type, operation.entity_id)
        primary = (
            outcome.changes[0].snapshot
            if outcome.changes
            else _duplicate_snapshot(session, operation, user_id)
        )
        version = (
            int(primary.get("version"))
            if isinstance(primary, dict) and primary.get("version") is not None
            else None
        )
        result = SyncPushResult(
            op_id=operation.op_id,
            status="applied",
            entity=primary,
            version=version,
            seq=seq,
            duplicate=True if outcome.duplicate else None,
        )
        _remember_result(
            session,
            operation,
            user_id=user_id,
            result=result.model_dump(mode="json"),
            now=now,
            settings=settings,
        )
        return result
    except SyncConflict as exc:
        session.rollback()
        result = SyncPushResult(
            op_id=operation.op_id,
            status="conflict",
            server_entity=exc.server_entity,
            version=exc.version,
        )
        _remember_result(
            session,
            operation,
            user_id=user_id,
            result=result.model_dump(mode="json"),
            now=now,
            settings=settings,
        )
        return result
    except SyncError as exc:
        session.rollback()
        result = SyncPushResult(
            op_id=operation.op_id,
            status="error",
            code=exc.code,
            detail=exc.detail,
        )
        _remember_result(
            session,
            operation,
            user_id=user_id,
            result=result.model_dump(mode="json"),
            now=now,
            settings=settings,
        )
        return result
    except ValidationError as exc:
        session.rollback()
        result = SyncPushResult(
            op_id=operation.op_id,
            status="error",
            code="validation_error",
            detail=_validation_detail(exc),
        )
        _remember_result(
            session,
            operation,
            user_id=user_id,
            result=result.model_dump(mode="json"),
            now=now,
            settings=settings,
        )
        return result
    except IntegrityError:
        # A concurrent create may win the primary-key race. Treat the loser as
        # an idempotent duplicate instead of surfacing a 500 or creating a
        # second recurrence link.
        session.rollback()
        remembered = session.get(SyncOperation, operation.op_id)
        if remembered is not None:
            return SyncPushResult.model_validate(json.loads(remembered.result_json))
        snapshot = (
            _duplicate_snapshot(session, operation, user_id)
            if operation.op_type == "create"
            else None
        )
        if snapshot is not None:
            result = SyncPushResult(
                op_id=operation.op_id,
                status="applied",
                entity=snapshot,
                version=(int(snapshot["version"]) if snapshot.get("version") is not None else None),
                seq=_entity_latest_seq(session, operation.entity_type, operation.entity_id),
                duplicate=True,
            )
        else:
            result = SyncPushResult(
                op_id=operation.op_id,
                status="error",
                code="conflict",
                detail="database constraint violation",
            )
        _remember_result(
            session,
            operation,
            user_id=user_id,
            result=result.model_dump(mode="json"),
            now=now,
            settings=settings,
        )
        return result
    except ServiceError as exc:
        session.rollback()
        code = "not_found" if isinstance(exc, NotFoundError) else "validation_error"
        if isinstance(exc, ConflictError):
            code = "conflict"
        result = SyncPushResult(
            op_id=operation.op_id,
            status="error",
            code=code,
            detail=str(exc),
        )
        _remember_result(
            session,
            operation,
            user_id=user_id,
            result=result.model_dump(mode="json"),
            now=now,
            settings=settings,
        )
        return result


def push_operations(
    session: Session,
    operations: list[SyncOperationIn],
    *,
    user_id: str | None,
    settings: Settings | None = None,
) -> SyncPushResponse:
    active = settings or get_settings()
    moment = utc_now()
    compact_sync_state(session, now=moment, settings=active)
    results: list[SyncPushResult] = []
    for operation in operations:
        results.append(
            _process_operation(
                session,
                operation,
                user_id=user_id,
                settings=active,
                now=moment,
            )
        )
    return SyncPushResponse(results=results, cursor=_current_cursor(session))


# ---------------------------------------------------------------------------
# Pull and bootstrap
# ---------------------------------------------------------------------------


def pull_changes(
    session: Session,
    payload: SyncPullRequest,
    *,
    user_id: str | None,
    settings: Settings | None = None,
) -> SyncPullResponse:
    active = settings or get_settings()
    moment = utc_now()
    compact_sync_state(session, now=moment, settings=active)

    max_cursor = _current_cursor(session)
    if payload.cursor > max_cursor:
        raise CursorExpiredError("bootstrap_required")
    if payload.cursor < _compaction_floor(session):
        raise CursorExpiredError("bootstrap_required")
    oldest_value = session.exec(
        select(func.min(SyncChange.seq)).where(SyncChange.entity_type != "sync_meta")
    ).one()
    if oldest_value is not None and payload.cursor < int(oldest_value) - 1:
        # Rows disappeared without a compaction marker (manual cleanup or a
        # retention job interrupted before writing the marker). There is a gap
        # between the cursor and the feed, so a full snapshot is required.
        raise CursorExpiredError("bootstrap_required")

    if not payload.group_ids:
        return SyncPullResponse(changes=[], cursor=payload.cursor, has_more=False)

    conditions = [
        SyncChange.seq > payload.cursor,
        SyncChange.entity_type != "sync_meta",
        SyncChange.group_id.in_(payload.group_ids),
    ]
    # Star/archive rows are per user; a capability-URL guest must never see
    # another account's membership state.
    if user_id is None:
        conditions.append(SyncChange.entity_type != "user_group")
    else:
        conditions.append(
            or_(
                SyncChange.entity_type != "user_group",
                and_(
                    SyncChange.entity_type == "user_group",
                    SyncChange.user_id == user_id,
                ),
            )
        )

    rows = list(
        session.exec(
            select(SyncChange)
            .where(*conditions)
            .order_by(SyncChange.seq.asc())
            .limit(payload.limit + 1)
        ).all()
    )
    has_more = len(rows) > payload.limit
    visible = rows[: payload.limit]
    changes = [
        SyncChangeRead(
            seq=int(row.seq or 0),
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            op_type=row.op_type,
            snapshot=json.loads(row.payload_json) if row.payload_json else None,
        )
        for row in visible
    ]
    cursor = int(visible[-1].seq or 0) if visible else payload.cursor
    return SyncPullResponse(changes=changes, cursor=cursor, has_more=has_more)


def bootstrap_group(
    session: Session,
    group_id: str,
    *,
    user_id: str | None = None,
    settings: Settings | None = None,
) -> SyncBootstrapResponse:
    active = settings or get_settings()
    compact_sync_state(session, now=utc_now(), settings=active)

    group = session.get(Group, group_id)
    if group is None or group.deleted_at is not None:
        raise NotFoundError("group not found")

    expenses_service.materialize_due_recurring_expenses(session, group_id=group_id)
    session.refresh(group)

    participants = groups_service.get_participants(session, group_id)
    expense_rows = list(
        session.exec(
            select(Expense)
            .where(Expense.group_id == group_id, Expense.deleted_at.is_(None))
            .order_by(Expense.expense_date.desc(), Expense.created_at.desc(), Expense.id.asc())
        ).all()
    )
    activity_rows = list(
        session.exec(
            select(Activity)
            .where(Activity.group_id == group_id)
            .order_by(Activity.time.desc(), Activity.id.desc())
        ).all()
    )
    receipts = list(session.exec(select(Receipt).where(Receipt.group_id == group_id)).all())
    categories = categories_service.list_categories(session, limit=200)

    membership = session.get(UserGroup, (user_id, group_id)) if user_id is not None else None
    return SyncBootstrapResponse(
        cursor=_current_cursor(session),
        group=GroupRead.model_validate(_group_snapshot(session, group, user_id=user_id)),
        participants=[
            ParticipantRead.model_validate(_participant_snapshot(participant))
            for participant in participants
        ],
        expenses=expenses_service.expenses_to_read(session, expense_rows),
        activities=[
            ActivityRead(
                id=activity.id,
                group_id=activity.group_id,
                time=activity.time,
                activity_type=activity.activity_type,
                participant_id=activity.participant_id,
                expense_id=activity.expense_id,
                data=activity.data,
            )
            for activity in activity_rows
        ],
        receipts=[_receipt_snapshot(session, receipt) for receipt in receipts],
        categories=[
            CategoryRead(id=int(category.id or 0), grouping=category.grouping, name=category.name)
            for category in categories.items
        ],
        user_group=(
            _membership_snapshot(membership)
            if membership is not None and membership.deleted_at is None
            else None
        ),
    )


# ---------------------------------------------------------------------------
# Group claim/merge
# ---------------------------------------------------------------------------


def claim_groups(
    session: Session,
    *,
    user_id: str,
    group_ids: list[str],
    starred_group_ids: list[str] | tuple[str, ...] = (),
    archived_group_ids: list[str] | tuple[str, ...] = (),
    now: datetime | None = None,
    commit: bool = True,
) -> list[UserGroup]:
    """Merge locally known group IDs into an account without duplicates.

    This is the service equivalent of the reference ``syncGroupsProcedure``.
    Membership changes are written to the change feed so another logged-in
    device can observe the claim.
    """
    moment = now or utc_now()
    starred = set(starred_group_ids)
    archived = set(archived_group_ids)
    # Archive wins when a stale guest cache lists a group in both sets.
    starred -= archived
    memberships: list[UserGroup] = []
    seen: set[str] = set()
    for group_id in group_ids:
        if group_id in seen:
            continue
        seen.add(group_id)
        group = session.get(Group, group_id)
        if group is None or group.deleted_at is not None:
            continue
        membership = session.get(UserGroup, (user_id, group_id))
        if membership is None:
            membership = UserGroup(
                user_id=user_id,
                group_id=group_id,
                is_starred=group_id in starred,
                is_archived=group_id in archived,
                created_at=moment,
                updated_at=moment,
                version=1,
            )
            session.add(membership)
            session.flush()
            op_type = "create"
            changed = True
        else:
            changed = False
            if group_id in starred and not membership.is_starred:
                membership.is_starred = True
                changed = True
            if group_id in archived and not membership.is_archived:
                membership.is_archived = True
                changed = True
            if changed:
                membership.updated_at = moment
                membership.version += 1
                session.add(membership)
                session.flush()
            op_type = "update"
        if changed:
            _append_change(
                session,
                change=_Change(
                    group_id,
                    "user_group",
                    group_id,
                    op_type,
                    _membership_snapshot(membership),
                ),
                user_id=user_id,
                now=moment,
            )
        memberships.append(membership)
    if commit:
        session.commit()
    else:
        session.flush()
    return memberships
