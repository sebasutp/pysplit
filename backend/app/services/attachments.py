"""Unified attachment upload, retrieval, receipt extraction and split logic."""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import math
from datetime import UTC, date, datetime, time, timedelta
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import delete, func, or_, update
from sqlmodel import Session, select

from app.core.config import Settings
from app.core.enums import ReceiptPortionTarget, ReceiptStatus, SplitMode
from app.core.ids import new_id
from app.models.attachment import Attachment
from app.models.attachment_item import AttachmentItem
from app.models.attachment_item_portion import AttachmentItemPortion
from app.models.attachment_opt_out import AttachmentOptOut
from app.models.base import utc_now
from app.models.category import Category
from app.models.expense import Expense
from app.models.participant import Participant
from app.schemas.attachments import (
    AttachmentApplyRequest,
    AttachmentExtractionResult,
    AttachmentExtractItemsRequest,
    AttachmentItemCreate,
    AttachmentItemRead,
    AttachmentItemUpdate,
    AttachmentPortionInput,
    AttachmentPortionRead,
    AttachmentRead,
    AttachmentSplitParticipant,
    AttachmentSplitRead,
    AttachmentState,
    AttachmentTotalExtraction,
)
from app.schemas.expenses import MAX_AMOUNT, ExpensePaidForInput, ExpenseUpdate
from app.services import ai as ai_service
from app.services import categories as categories_service
from app.services import groups as groups_service
from app.services.common import require_group
from app.services.errors import (
    ConflictError,
    ForbiddenError,
    InvalidInputError,
    NotFoundError,
    PayloadTooLargeError,
)
from app.storage import BlobStorage, StorageError, get_storage
from app.utils.currency import decimal_digits
from app.utils.receipt_extraction import normalize_receipt, parse_receipt_items_response
from app.utils.receipt_split import (
    ReceiptSplitResult,
    compute_receipt_split,
    to_receipt_split_items,
)

CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}
EXTENSION_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}
IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
SUPPORTED_CONTENT_TYPES = frozenset(CONTENT_TYPE_EXTENSIONS)
_PUBLIC_PROVIDER_LABELS = {"openai-compatible", "google", "disabled"}

logger = logging.getLogger(__name__)


def _public_provider(provider: str | None) -> str | None:
    if provider is None:
        return None
    if provider in _PUBLIC_PROVIDER_LABELS:
        return provider
    lowered = provider.lower()
    if "google" in lowered or "generativelanguage" in lowered:
        return "google"
    return "openai-compatible"


def sniff_content_type(data: bytes) -> str | None:
    """Return the supported type implied by the file signature."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def _safe_filename(filename: str | None, content_type: str) -> str:
    base = PurePosixPath(str(filename or "")).name.strip()
    if not base or base in {".", ".."}:
        base = f"attachment{CONTENT_TYPE_EXTENSIONS[content_type]}"
    return base[:255]


def _file_url(settings: Settings, group_id: str, attachment_id: str) -> str:
    return f"{settings.api_prefix}/groups/{group_id}/attachments/{attachment_id}/file"


def _attachment_read(attachment: Attachment) -> AttachmentRead:
    return AttachmentRead(
        id=attachment.id,
        group_id=attachment.group_id,
        expense_id=attachment.expense_id,
        url=attachment.url,
        thumbnail_url=attachment.thumbnail_url,
        filename=attachment.filename,
        content_type=attachment.content_type,
        byte_size=attachment.byte_size,
        width=attachment.width,
        height=attachment.height,
        receipt_status=attachment.receipt_status,
        attempts=attachment.attempts,
        merchant=attachment.merchant,
        receipt_date=attachment.receipt_date.date() if attachment.receipt_date else None,
        currency_code=attachment.currency_code,
        total=attachment.total,
        provider=_public_provider(attachment.provider),
        model=attachment.model,
        created_at=attachment.created_at,
        updated_at=attachment.updated_at,
        version=attachment.version,
        deleted_at=attachment.deleted_at,
    )


def _portion_read(portion: AttachmentItemPortion) -> AttachmentPortionRead:
    return AttachmentPortionRead(
        id=portion.id,
        item_id=portion.item_id,
        target=portion.target,
        participant_id=portion.participant_id,
        quantity_milli=portion.quantity_milli,
        version=portion.version,
    )


def _item_read(item: AttachmentItem, portions: list[AttachmentItemPortion]) -> AttachmentItemRead:
    return AttachmentItemRead(
        id=item.id,
        attachment_id=item.attachment_id,
        name=item.name,
        quantity_milli=item.quantity_milli,
        unit_price=item.unit_price,
        amount=item.amount,
        is_shared=item.is_shared,
        is_adjustment=item.is_adjustment,
        position=item.position,
        version=item.version,
        updated_at=item.updated_at,
        deleted_at=item.deleted_at,
        portions=[_portion_read(portion) for portion in portions],
    )


def _split_read(split: ReceiptSplitResult, items: list[AttachmentItem]) -> AttachmentSplitRead:
    adjustments = sum(item.amount for item in items if item.is_adjustment)
    return AttachmentSplitRead(
        participants=[
            AttachmentSplitParticipant(
                participant_id=share.participant_id,
                direct=share.direct,
                shared=share.shared,
                unassigned=share.unassigned,
                total=share.total,
            )
            for share in split.participants
        ],
        items_total=split.items_total,
        shared_pool=split.shared_pool,
        unassigned_pool=split.unassigned_pool,
        all_opted_out=split.all_opted_out,
        participant_totals=[
            {"participant_id": share.participant_id, "amount": share.total}
            for share in split.participants
        ],
        unassigned=split.unassigned_pool,
        shared=split.shared_pool,
        adjustments=adjustments,
        total=split.items_total,
    )


# ---------------------------------------------------------------------------
# Upload, retrieval and linking
# ---------------------------------------------------------------------------


def _active_expense(session: Session, group_id: str, expense_id: str) -> Expense:
    expense = session.get(Expense, expense_id)
    if expense is None or expense.group_id != group_id or expense.deleted_at is not None:
        raise NotFoundError("Expense not found")
    return expense


def save_attachment(
    session: Session,
    storage: BlobStorage,
    settings: Settings,
    *,
    group_id: str,
    data: bytes,
    content_type: str | None,
    filename: str | None,
    expense_id: str | None = None,
    width: int = 1,
    height: int = 1,
    now: datetime | None = None,
) -> AttachmentRead:
    require_group(session, group_id)
    if expense_id is not None:
        _active_expense(session, group_id, expense_id)
    if not data:
        raise InvalidInputError("uploaded file is empty", field="file")
    if len(data) > settings.max_upload_bytes:
        raise PayloadTooLargeError(f"file exceeds the {settings.max_upload_bytes} byte limit")

    sniffed = sniff_content_type(data)
    if sniffed is None or sniffed not in settings.upload_allowed_type_list:
        raise InvalidInputError("unsupported file type", field="file")
    # The signature wins over the browser-provided MIME type.
    normalized_type = sniffed

    attachment_id = new_id("att")
    key = f"attachments/{group_id}/{attachment_id}{CONTENT_TYPE_EXTENSIONS[normalized_type]}"
    storage.save(key, data, content_type=normalized_type)
    url = storage.public_url(key) or _file_url(settings, group_id, attachment_id)
    moment = now or utc_now()
    attachment = Attachment(
        id=attachment_id,
        group_id=group_id,
        expense_id=expense_id,
        storage_key=key,
        url=url,
        filename=_safe_filename(filename, normalized_type),
        content_type=normalized_type,
        byte_size=len(data),
        width=max(1, int(width)),
        height=max(1, int(height)),
        thumbnail_url=url if normalized_type in IMAGE_CONTENT_TYPES else None,
        created_at=moment,
        updated_at=moment,
        version=1,
    )
    try:
        session.add(attachment)
        session.commit()
        session.refresh(attachment)
    except Exception:
        session.rollback()
        with contextlib.suppress(StorageError):
            storage.delete(key)
        raise
    return _attachment_read(attachment)


def get_attachment(
    session: Session,
    group_id: str,
    attachment_id: str,
) -> Attachment:
    require_group(session, group_id)
    attachment = session.get(Attachment, attachment_id)
    if attachment is None or attachment.group_id != group_id or attachment.deleted_at is not None:
        raise NotFoundError("Attachment not found")
    return attachment


def resolve_attachment_file(
    session: Session,
    storage: BlobStorage,
    *,
    group_id: str,
    attachment_id: str,
) -> tuple[Attachment, bytes, str, str]:
    attachment = get_attachment(session, group_id, attachment_id)
    try:
        data = storage.read(attachment.storage_key)
    except StorageError as exc:
        raise NotFoundError("Attachment file not found") from exc
    return attachment, data, attachment.content_type, attachment.filename


def delete_attachment(
    session: Session,
    storage: BlobStorage,
    *,
    group_id: str,
    attachment_id: str,
) -> None:
    attachment = get_attachment(session, group_id, attachment_id)
    key = attachment.storage_key
    session.delete(attachment)
    session.commit()
    with contextlib.suppress(StorageError):
        storage.delete(key)


def link_attachment_to_expense(
    session: Session,
    group_id: str,
    attachment_id: str,
    expense_id: str | None,
    *,
    now: datetime | None = None,
) -> Attachment:
    attachment = get_attachment(session, group_id, attachment_id)
    if expense_id is not None:
        _active_expense(session, group_id, expense_id)
        existing = session.exec(
            select(Attachment).where(
                Attachment.expense_id == expense_id,
                Attachment.id != attachment.id,
                Attachment.receipt_status.is_not(None),
                Attachment.deleted_at.is_(None),
            )
        ).first()
        if existing is not None and attachment.receipt_status is not None:
            raise ConflictError("Expense already has a processed receipt")

    attachment.expense_id = expense_id
    attachment.updated_at = now or utc_now()
    attachment.version += 1
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return attachment


def attachments_for_expenses(
    session: Session,
    expense_ids: list[str],
) -> dict[str, list[Attachment]]:
    if not expense_ids:
        return {}
    rows = list(
        session.exec(
            select(Attachment)
            .where(
                Attachment.expense_id.in_(expense_ids),
                Attachment.deleted_at.is_(None),
            )
            .order_by(Attachment.created_at.asc(), Attachment.id.asc())
        ).all()
    )
    grouped: dict[str, list[Attachment]] = {}
    for row in rows:
        if row.expense_id:
            grouped.setdefault(row.expense_id, []).append(row)
    return grouped


def attachment_reads_for_expenses(
    session: Session,
    expense_ids: list[str],
) -> dict[str, list[AttachmentRead]]:
    grouped = attachments_for_expenses(session, expense_ids)
    return {
        expense_id: [_attachment_read(attachment) for attachment in attachments]
        for expense_id, attachments in grouped.items()
    }


# ---------------------------------------------------------------------------
# Receipt state and split
# ---------------------------------------------------------------------------


def _items_with_portions(
    session: Session,
    attachment_id: str,
) -> list[tuple[AttachmentItem, list[AttachmentItemPortion]]]:
    items = list(
        session.exec(
            select(AttachmentItem)
            .where(
                AttachmentItem.attachment_id == attachment_id,
                AttachmentItem.deleted_at.is_(None),
            )
            .order_by(AttachmentItem.position.asc(), AttachmentItem.id.asc())
        ).all()
    )
    if not items:
        return []
    item_ids = [item.id for item in items]
    portions = list(
        session.exec(
            select(AttachmentItemPortion)
            .where(
                AttachmentItemPortion.item_id.in_(item_ids),
                AttachmentItemPortion.deleted_at.is_(None),
            )
            .order_by(
                AttachmentItemPortion.created_at.asc(),
                AttachmentItemPortion.id.asc(),
            )
        ).all()
    )
    by_item: dict[str, list[AttachmentItemPortion]] = {item.id: [] for item in items}
    for portion in portions:
        by_item.setdefault(portion.item_id, []).append(portion)
    return [(item, by_item.get(item.id, [])) for item in items]


def _opt_out_ids(session: Session, attachment_id: str) -> list[str]:
    rows = session.exec(
        select(AttachmentOptOut)
        .where(
            AttachmentOptOut.attachment_id == attachment_id,
            AttachmentOptOut.deleted_at.is_(None),
        )
        .order_by(AttachmentOptOut.participant_id.asc())
    ).all()
    return [row.participant_id for row in rows]


def compute_attachment_split(
    session: Session,
    attachment: Attachment,
    group_id: str,
) -> tuple[ReceiptSplitResult, list[tuple[AttachmentItem, list[AttachmentItemPortion]]]]:
    participants = groups_service.get_participants(session, group_id)
    pairs = _items_with_portions(session, attachment.id)
    split = compute_receipt_split(
        [participant.id for participant in participants],
        _opt_out_ids(session, attachment.id),
        to_receipt_split_items(
            [
                {
                    "amount": item.amount,
                    "quantity_milli": item.quantity_milli,
                    "is_shared": item.is_shared,
                    "portions": [
                        {
                            "target": portion.target,
                            "participant_id": portion.participant_id,
                            "quantity_milli": portion.quantity_milli,
                        }
                        for portion in portions
                    ],
                }
                for item, portions in pairs
            ]
        ),
    )
    return split, pairs


def attachment_state(session: Session, group_id: str, attachment: Attachment) -> AttachmentState:
    split, pairs = compute_attachment_split(session, attachment, group_id)
    return AttachmentState(
        attachment=_attachment_read(attachment),
        items=[_item_read(item, portions) for item, portions in pairs],
        opt_outs=_opt_out_ids(session, attachment.id),
        split=_split_read(split, [item for item, _portions in pairs]),
    )


def get_attachment_state(
    session: Session,
    group_id: str,
    *,
    attachment_id: str,
) -> AttachmentState:
    attachment = get_attachment(session, group_id, attachment_id)
    return attachment_state(session, group_id, attachment)


# ---------------------------------------------------------------------------
# Extraction lifecycle
# ---------------------------------------------------------------------------


def claim_for_extraction(
    session: Session,
    attachment_id: str,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> bool:
    moment = now or utc_now()
    stale_before = moment - timedelta(seconds=settings.receipt_extraction_stale_seconds)
    result = session.execute(
        update(Attachment)
        .where(
            Attachment.id == attachment_id,
            Attachment.deleted_at.is_(None),
            Attachment.attempts < settings.receipt_max_attempts,
            or_(
                Attachment.receipt_status.is_(None),
                Attachment.receipt_status.in_(
                    [ReceiptStatus.PENDING.value, ReceiptStatus.FAILED.value]
                ),
                (Attachment.receipt_status == ReceiptStatus.EXTRACTING.value)
                & (Attachment.updated_at < stale_before),
            ),
        )
        .values(
            receipt_status=ReceiptStatus.EXTRACTING.value,
            attempts=Attachment.attempts + 1,
            updated_at=moment,
            version=Attachment.version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    session.commit()
    if (result.rowcount or 0) == 1:
        return True

    attachment = session.get(Attachment, attachment_id)
    if (
        attachment is not None
        and attachment.deleted_at is None
        and attachment.attempts >= settings.receipt_max_attempts
        and (
            attachment.receipt_status
            in (None, ReceiptStatus.PENDING.value, ReceiptStatus.FAILED.value)
            or (
                attachment.receipt_status == ReceiptStatus.EXTRACTING.value
                and attachment.updated_at < stale_before
            )
        )
    ):
        raise ConflictError("Receipt extraction attempts are exhausted. Upload the file again.")
    return False


def _parse_receipt_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return datetime.combine(parsed, time(12, 0), tzinfo=UTC)


def complete_extraction(
    session: Session,
    attachment_id: str,
    *,
    raw_extraction: str | None,
    provider: str | None,
    model: str | None,
    normalized: dict[str, Any],
    now: datetime | None = None,
) -> Attachment:
    moment = now or utc_now()
    attachment = session.get(Attachment, attachment_id)
    if attachment is None:
        raise NotFoundError("Attachment not found")

    item_ids = [
        item_id
        for item_id in session.exec(
            select(AttachmentItem.id).where(AttachmentItem.attachment_id == attachment_id)
        ).all()
        if item_id is not None
    ]
    if item_ids:
        session.execute(
            delete(AttachmentItemPortion).where(AttachmentItemPortion.item_id.in_(item_ids))
        )
    session.execute(delete(AttachmentItem).where(AttachmentItem.attachment_id == attachment_id))

    total = normalized.get("total")
    if total is None:
        total = normalized.get("items_total")

    attachment.receipt_status = ReceiptStatus.EXTRACTED.value
    attachment.raw_extraction = raw_extraction
    attachment.provider = provider
    attachment.model = model
    attachment.merchant = normalized.get("merchant")
    attachment.receipt_date = _parse_receipt_date(normalized.get("date"))
    attachment.currency_code = normalized.get("currency_code")
    attachment.total = total
    attachment.updated_at = moment
    attachment.version += 1
    session.add(attachment)

    for item in normalized.get("items", []):
        session.add(
            AttachmentItem(
                id=new_id("aitem"),
                attachment_id=attachment_id,
                name=item["name"],
                quantity_milli=item["quantity_milli"],
                unit_price=item.get("unit_price"),
                amount=item["amount"],
                is_shared=bool(item.get("is_shared")),
                is_adjustment=bool(item.get("is_adjustment")),
                position=int(item["position"]),
                created_at=moment,
                updated_at=moment,
                version=1,
            )
        )

    session.commit()
    session.refresh(attachment)
    return attachment


def fail_extraction(
    session: Session,
    attachment_id: str,
    *,
    raw_extraction: str | None,
    provider: str | None,
    model: str | None,
    now: datetime | None = None,
) -> None:
    attachment = session.get(Attachment, attachment_id)
    if attachment is None:
        return
    attachment.receipt_status = ReceiptStatus.FAILED.value
    attachment.raw_extraction = raw_extraction
    attachment.provider = provider
    attachment.model = model
    attachment.updated_at = now or utc_now()
    attachment.version += 1
    session.add(attachment)
    session.commit()


# ---------------------------------------------------------------------------
# Item mutations
# ---------------------------------------------------------------------------


def _require_item(session: Session, attachment: Attachment, item_id: str) -> AttachmentItem:
    item = session.get(AttachmentItem, item_id)
    if item is None or item.attachment_id != attachment.id or item.deleted_at is not None:
        raise NotFoundError("Item not found")
    return item


def _check_item_values(
    settings: Settings | None,
    *,
    name: str | None = None,
    quantity_milli: int | None = None,
    amount: int | None = None,
) -> None:
    if settings is None:
        return
    if name is not None and len(name) > settings.max_receipt_item_name_length:
        raise InvalidInputError("Item name is too long", field="name")
    if quantity_milli is not None and (
        quantity_milli <= 0 or quantity_milli > settings.max_receipt_item_quantity_milli
    ):
        raise InvalidInputError("Item quantity is out of range", field="quantity_milli")
    if amount is not None and (amount <= 0 or amount > settings.max_receipt_item_amount):
        raise InvalidInputError("Item amount is out of range", field="amount")


def _validate_normalized_items(settings: Settings, normalized: dict[str, Any]) -> None:
    for item in normalized.get("items", []):
        if item.get("is_adjustment"):
            continue
        _check_item_values(
            settings,
            name=item.get("name"),
            quantity_milli=item.get("quantity_milli"),
            amount=item.get("amount"),
        )


def _cap_extraction_lists(parsed: dict[str, Any], limit: int) -> dict[str, Any]:
    return {
        **parsed,
        "items": list(parsed.get("items", []))[:limit],
        "charges": list(parsed.get("charges", []))[:limit],
    }


def add_item(
    session: Session,
    group_id: str,
    attachment_id: str,
    payload: AttachmentItemCreate,
    *,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> AttachmentState:
    attachment = get_attachment(session, group_id, attachment_id)
    item_id = payload.id or new_id("aitem")
    if payload.id is not None:
        existing_item = session.get(AttachmentItem, item_id)
        if existing_item is not None:
            if existing_item.attachment_id == attachment.id and existing_item.deleted_at is None:
                return attachment_state(session, group_id, attachment)
            raise InvalidInputError("Attachment item id already exists", field="id")
    _check_item_values(
        settings,
        name=payload.name,
        quantity_milli=payload.quantity_milli,
        amount=payload.amount,
    )
    if settings is not None:
        existing_count = session.exec(
            select(func.count(AttachmentItem.id)).where(
                AttachmentItem.attachment_id == attachment.id,
                AttachmentItem.deleted_at.is_(None),
            )
        ).one()
        if int(existing_count) >= settings.max_receipt_items:
            raise InvalidInputError("Receipt has too many items", field="items")
    moment = now or utc_now()
    maximum = session.exec(
        select(func.max(AttachmentItem.position)).where(
            AttachmentItem.attachment_id == attachment.id
        )
    ).one()
    position = (int(maximum) if maximum is not None else -1) + 1
    session.add(
        AttachmentItem(
            id=item_id,
            attachment_id=attachment.id,
            name=payload.name,
            quantity_milli=payload.quantity_milli,
            unit_price=None,
            amount=payload.amount,
            is_shared=payload.is_shared,
            is_adjustment=False,
            position=position,
            created_at=moment,
            updated_at=moment,
            version=1,
        )
    )
    attachment.updated_at = moment
    attachment.version += 1
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return attachment_state(session, group_id, attachment)


def update_item(
    session: Session,
    group_id: str,
    attachment_id: str,
    item_id: str,
    payload: AttachmentItemUpdate,
    *,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> AttachmentState:
    attachment = get_attachment(session, group_id, attachment_id)
    item = _require_item(session, attachment, item_id)
    fields = payload.model_dump(exclude_unset=True)
    if any(value is None for value in fields.values()):
        raise InvalidInputError("Receipt item fields cannot be null", field="item")
    _check_item_values(
        settings,
        name=fields.get("name"),
        quantity_milli=fields.get("quantity_milli"),
        amount=fields.get("amount"),
    )
    for key, value in fields.items():
        setattr(item, key, value)
    moment = now or utc_now()
    item.updated_at = moment
    item.version += 1
    attachment.updated_at = moment
    attachment.version += 1
    session.add(item)
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return attachment_state(session, group_id, attachment)


def delete_item(
    session: Session,
    group_id: str,
    attachment_id: str,
    item_id: str,
    *,
    now: datetime | None = None,
) -> AttachmentState:
    attachment = get_attachment(session, group_id, attachment_id)
    item = session.get(AttachmentItem, item_id)
    if item is not None and item.attachment_id != attachment.id:
        raise NotFoundError("Item not found")
    if item is None or item.deleted_at is not None:
        return attachment_state(session, group_id, attachment)
    session.execute(delete(AttachmentItemPortion).where(AttachmentItemPortion.item_id == item.id))
    session.delete(item)
    moment = now or utc_now()
    attachment.updated_at = moment
    attachment.version += 1
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return attachment_state(session, group_id, attachment)


def set_item_portions(
    session: Session,
    group_id: str,
    attachment_id: str,
    item_id: str,
    portions: list[AttachmentPortionInput],
    *,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> AttachmentState:
    attachment = get_attachment(session, group_id, attachment_id)
    item = _require_item(session, attachment, item_id)
    if settings is not None and len(portions) > settings.max_receipt_item_portions:
        raise InvalidInputError("Too many portions", field="portions")
    participant_ids = {
        participant.id for participant in groups_service.get_participants(session, group_id)
    }

    assigned = 0
    for portion in portions:
        assigned += portion.quantity_milli
        if portion.target == ReceiptPortionTarget.PARTICIPANT.value and (
            not portion.participant_id or portion.participant_id not in participant_ids
        ):
            raise InvalidInputError("Invalid participant for portion", field="portions")
    if assigned > item.quantity_milli:
        raise InvalidInputError("Portions exceed the item quantity", field="portions")

    session.execute(delete(AttachmentItemPortion).where(AttachmentItemPortion.item_id == item.id))
    moment = now or utc_now()
    for portion in portions:
        session.add(
            AttachmentItemPortion(
                id=new_id("aportion"),
                item_id=item.id,
                target=portion.target,
                participant_id=(
                    None
                    if portion.target == ReceiptPortionTarget.SHARED.value
                    else portion.participant_id
                ),
                quantity_milli=portion.quantity_milli,
                created_at=moment,
                updated_at=moment,
                version=1,
            )
        )

    item.is_shared = bool(portions) and all(
        portion.target == ReceiptPortionTarget.SHARED.value for portion in portions
    )
    item.updated_at = moment
    item.version += 1
    attachment.updated_at = moment
    attachment.version += 1
    session.add(item)
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return attachment_state(session, group_id, attachment)


def set_opt_out(
    session: Session,
    group_id: str,
    attachment_id: str,
    participant_id: str,
    opted_out: bool,
    *,
    now: datetime | None = None,
) -> AttachmentState:
    attachment = get_attachment(session, group_id, attachment_id)
    participant = session.get(Participant, participant_id)
    if (
        participant is None
        or participant.group_id != group_id
        or participant.deleted_at is not None
    ):
        raise InvalidInputError("Participant is not in the group", field="participant_id")

    moment = now or utc_now()
    existing = session.exec(
        select(AttachmentOptOut).where(
            AttachmentOptOut.attachment_id == attachment.id,
            AttachmentOptOut.participant_id == participant_id,
        )
    ).first()
    if opted_out:
        if existing is None:
            session.add(
                AttachmentOptOut(
                    id=new_id("aopt"),
                    attachment_id=attachment.id,
                    participant_id=participant_id,
                    created_at=moment,
                    updated_at=moment,
                    version=1,
                )
            )
        elif existing.deleted_at is not None:
            existing.deleted_at = None
            existing.updated_at = moment
            existing.version += 1
            session.add(existing)
    elif existing is not None:
        session.delete(existing)

    attachment.updated_at = moment
    attachment.version += 1
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return attachment_state(session, group_id, attachment)


# ---------------------------------------------------------------------------
# Apply to an expense
# ---------------------------------------------------------------------------


def apply_attachment_to_expense(
    session: Session,
    group_id: str,
    attachment_id: str,
    expense_id: str,
    *,
    participant_id: str | None = None,
    now: datetime | None = None,
) -> tuple[Attachment, ReceiptSplitResult]:
    attachment = get_attachment(session, group_id, attachment_id)
    expense = _active_expense(session, group_id, expense_id)
    split, _pairs = compute_attachment_split(session, attachment, group_id)

    if split.all_opted_out:
        raise InvalidInputError("Everyone opted out, but items are still unassigned.")
    if split.items_total == 0:
        raise InvalidInputError("The receipt has no items to apply.")
    if split.items_total < -MAX_AMOUNT or split.items_total > MAX_AMOUNT:
        raise InvalidInputError("The receipt total is outside the allowed expense range.")
    if any(share.total < 0 for share in split.participants):
        raise InvalidInputError(
            "Some participants have a negative share; adjust the items before applying."
        )

    paid_for = [
        ExpensePaidForInput(participant_id=share.participant_id, amount=share.total)
        for share in split.participants
        if share.total > 0
    ]
    payload = ExpenseUpdate(
        amount=split.items_total,
        split_mode=SplitMode.BY_AMOUNT,
        paid_for=paid_for,
        participant_id=participant_id,
    )
    from app.services import expenses as expenses_service

    moment = now or utc_now()
    expenses_service.update_expense(
        session,
        group_id,
        expense.id,
        payload,
        now=moment,
        commit=False,
    )

    attachment.expense_id = expense_id
    attachment.updated_at = moment
    attachment.version += 1
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return attachment, split


# ---------------------------------------------------------------------------
# AI extraction
# ---------------------------------------------------------------------------


def _require_receipt_ai(settings: Settings) -> None:
    if not settings.receipt_ai_enabled:
        raise ForbiddenError("Receipt AI is not enabled.")


def _category_options(session: Session) -> tuple[list[Category], list[str]]:
    categories = categories_service.list_categories(session, limit=500).items
    return categories, [
        ai_service.format_category_for_ai_prompt(category) for category in categories
    ]


def _call_ai(
    settings: Settings,
    *,
    ai_client: Any,
    model: str,
    messages: list[dict[str, Any]],
    response_format: dict[str, Any],
) -> str | None:
    owned = ai_client is None
    client = ai_client or ai_service.get_ai_client(settings)
    try:
        return client.complete(
            model=model,
            messages=messages,
            response_format=response_format,
        )
    finally:
        if owned:
            client.close()


def _parse_total_response(content: str | None) -> dict[str, Any] | None:
    if not content:
        return None
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    amount = parsed.get("amount")
    category_id = parsed.get("categoryId")
    date_value = parsed.get("date")
    title = parsed.get("title")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool):
        return None
    if not math.isfinite(amount):
        return None
    if (
        not isinstance(category_id, str)
        or not isinstance(date_value, str)
        or not isinstance(title, str)
    ):
        return None
    return {
        "amount": float(amount),
        "category_id": category_id,
        "date": date_value,
        "title": title,
    }


def _parse_category_response(content: str | None) -> int | None:
    if not content:
        return None
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    category_id = parsed.get("categoryId")
    if isinstance(category_id, bool):
        return None
    if isinstance(category_id, int):
        return category_id
    if isinstance(category_id, float) and math.isfinite(category_id) and category_id.is_integer():
        return int(category_id)
    return None


def _image_for_ai(storage: BlobStorage, attachment: Attachment) -> str:
    if attachment.content_type not in IMAGE_CONTENT_TYPES:
        raise InvalidInputError(
            "Receipt AI supports images only; PDFs can still be attached.",
            field="file",
        )
    try:
        data = storage.read(attachment.storage_key)
    except StorageError as exc:
        raise NotFoundError("Attachment file not found") from exc
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{attachment.content_type};base64,{encoded}"


def _receipt_messages(prompt: str, image: str) -> list[dict[str, Any]]:
    """One multimodal user turn, which all OpenAI-compatible providers accept."""
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image}},
            ],
        }
    ]


def extract_total(
    session: Session,
    settings: Settings,
    *,
    group_id: str,
    attachment_id: str,
    ai_client: Any = None,
    storage: BlobStorage | None = None,
) -> AttachmentTotalExtraction:
    _require_receipt_ai(settings)
    attachment = get_attachment(session, group_id, attachment_id)
    storage = storage or get_storage(settings)
    image = _image_for_ai(storage, attachment)
    _categories, options = _category_options(session)
    prompt = ai_service.build_receipt_extract_prompt(options)

    try:
        content = _call_ai(
            settings,
            ai_client=ai_client,
            model=settings.receipt_extract_model,
            messages=_receipt_messages(prompt, image),
            response_format=ai_service.RECEIPT_EXTRACT_JSON_SCHEMA,
        )
    except ai_service.AiError as exc:
        logger.warning("Receipt total extraction failed for %s: %s", attachment.id, exc)
        return AttachmentTotalExtraction()

    parsed = _parse_total_response(content)
    if parsed is None:
        return AttachmentTotalExtraction()
    return AttachmentTotalExtraction(
        amount=parsed["amount"],
        category_id=parsed["category_id"],
        date=parsed["date"],
        title=parsed["title"],
    )


def _extraction_result(
    session: Session,
    group_id: str,
    attachment: Attachment,
    *,
    status: str,
    category_id: str | None = None,
    error: str | None = None,
) -> AttachmentExtractionResult:
    state = attachment_state(session, group_id, attachment)
    if category_id is None and attachment.raw_extraction:
        parsed = parse_receipt_items_response(attachment.raw_extraction)
        if parsed is not None:
            category_id = parsed.get("category_id")
    return AttachmentExtractionResult(
        status=status,
        attachment_id=attachment.id,
        error=error,
        total=attachment.total,
        items_total=state.split.items_total,
        merchant=attachment.merchant,
        date=attachment.receipt_date.date().isoformat() if attachment.receipt_date else None,
        currency_code=attachment.currency_code,
        category_id=category_id,
        attachment=state.attachment,
        items=state.items,
        opt_outs=state.opt_outs,
        split=state.split,
    )


def extract_items(
    session: Session,
    settings: Settings,
    *,
    group_id: str,
    attachment_id: str,
    expense_id: str | None = None,
    ai_client: Any = None,
    storage: BlobStorage | None = None,
) -> AttachmentExtractionResult:
    _require_receipt_ai(settings)
    group = require_group(session, group_id)
    attachment = get_attachment(session, group_id, attachment_id)
    storage = storage or get_storage(settings)

    if expense_id is not None and attachment.expense_id != expense_id:
        attachment = link_attachment_to_expense(
            session,
            group_id,
            attachment.id,
            expense_id,
        )
    if attachment.receipt_status == ReceiptStatus.EXTRACTED.value:
        return _extraction_result(
            session,
            group_id,
            attachment,
            status=ReceiptStatus.EXTRACTED.value,
        )

    if attachment.expense_id is not None:
        other = session.exec(
            select(Attachment).where(
                Attachment.expense_id == attachment.expense_id,
                Attachment.id != attachment.id,
                Attachment.receipt_status.is_not(None),
                Attachment.deleted_at.is_(None),
            )
        ).first()
        if other is not None:
            raise ConflictError("Expense already has a processed receipt")

    image = _image_for_ai(storage, attachment)
    if not claim_for_extraction(session, attachment.id, settings=settings):
        raise ConflictError("Receipt extraction is already in progress.")
    session.refresh(attachment)

    _categories, options = _category_options(session)
    prompt = ai_service.build_receipt_items_prompt(options)
    model = settings.receipt_items_model
    provider = settings.ai_provider_label

    try:
        content = _call_ai(
            settings,
            ai_client=ai_client,
            model=model,
            messages=_receipt_messages(prompt, image),
            response_format=ai_service.RECEIPT_ITEMS_RESPONSE_FORMAT,
        )
    except ai_service.AiError as exc:
        logger.warning("Receipt item extraction failed for %s: %s", attachment.id, exc)
        fail_extraction(
            session,
            attachment.id,
            raw_extraction=None,
            provider=provider,
            model=model,
        )
        session.refresh(attachment)
        return _extraction_result(
            session,
            group_id,
            attachment,
            status=ReceiptStatus.FAILED.value,
            error=str(exc)[:300],
        )

    parsed = parse_receipt_items_response(content, limit=settings.max_receipt_items)
    if parsed is not None:
        parsed = _cap_extraction_lists(parsed, settings.max_receipt_items)
    if parsed is None:
        logger.warning(
            "Receipt item extraction for %s returned unparseable content: %r",
            attachment.id,
            (content or "")[:500],
        )
        fail_extraction(
            session,
            attachment.id,
            raw_extraction=content,
            provider=provider,
            model=model,
        )
        session.refresh(attachment)
        return _extraction_result(
            session,
            group_id,
            attachment,
            status=ReceiptStatus.FAILED.value,
            error="The AI response was not a valid receipt JSON object.",
        )

    normalized = normalize_receipt(parsed, decimal_digits(group.currency_code))
    try:
        _validate_normalized_items(settings, normalized)
    except InvalidInputError:
        fail_extraction(
            session,
            attachment.id,
            raw_extraction=content,
            provider=provider,
            model=model,
        )
        session.refresh(attachment)
        return _extraction_result(
            session,
            group_id,
            attachment,
            status=ReceiptStatus.FAILED.value,
            error="The AI returned a receipt item outside the allowed limits.",
        )
    attachment = complete_extraction(
        session,
        attachment.id,
        raw_extraction=content,
        provider=provider,
        model=model,
        normalized=normalized,
    )
    return _extraction_result(
        session,
        group_id,
        attachment,
        status=ReceiptStatus.EXTRACTED.value,
        category_id=parsed.get("category_id"),
    )


def infer_category(
    session: Session,
    settings: Settings,
    *,
    title: str,
    ai_client: Any = None,
) -> int:
    if not settings.enable_category_extract:
        raise ForbiddenError("Category AI is not enabled.")
    categories, options = _category_options(session)
    fallback = (
        ai_service.format_category_for_ai_prompt(categories[0]) if categories else '"General"'
    )
    try:
        content = _call_ai(
            settings,
            ai_client=ai_client,
            model=settings.category_extract_model,
            messages=[
                {
                    "role": "system",
                    "content": ai_service.build_category_extract_system_prompt(options, fallback),
                },
                {"role": "user", "content": title[:40]},
            ],
            response_format=ai_service.CATEGORY_EXTRACT_JSON_SCHEMA,
        )
    except ai_service.AiError as exc:
        logger.warning("Category inference failed: %s", exc)
        return 0

    parsed = _parse_category_response(content)
    if parsed is None:
        return 0
    for category in categories:
        if category.id == parsed:
            return int(category.id or 0)
    return 0


def apply_request_expense_id(payload: AttachmentApplyRequest) -> str:
    return payload.expense_id


def extract_request_expense_id(payload: AttachmentExtractItemsRequest) -> str | None:
    return payload.expense_id


def ensure_attachment_supported(settings: Settings, attachment: Attachment) -> None:
    if attachment.content_type not in SUPPORTED_CONTENT_TYPES:
        raise InvalidInputError("unsupported file type", field="file")
    if attachment.content_type not in settings.upload_allowed_type_list:
        raise InvalidInputError("unsupported file type", field="file")


def attachment_file_name(attachment: Attachment) -> str:
    return (
        attachment.filename
        or f"{attachment.id}{CONTENT_TYPE_EXTENSIONS.get(attachment.content_type, '')}"
    )


def attachment_url_path(attachment: Attachment) -> str:
    parsed = urlsplit(attachment.url)
    return parsed.path
