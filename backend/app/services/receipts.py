"""Receipt extraction, item allocation and apply-to-expense logic."""

from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import delete, func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.config import Settings
from app.core.enums import ReceiptPortionTarget, ReceiptStatus, SplitMode
from app.core.ids import new_id
from app.models.base import utc_now
from app.models.category import Category
from app.models.expense import Expense
from app.models.participant import Participant
from app.models.receipt import Receipt
from app.models.receipt_item import ReceiptItem
from app.models.receipt_item_portion import ReceiptItemPortion
from app.models.receipt_opt_out import ReceiptOptOut
from app.schemas.expenses import MAX_AMOUNT, ExpensePaidForInput, ExpenseUpdate
from app.schemas.receipts import (
    ReceiptExtractionResult,
    ReceiptItemCreate,
    ReceiptItemRead,
    ReceiptItemUpdate,
    ReceiptPortionInput,
    ReceiptPortionRead,
    ReceiptRead,
    ReceiptSplitParticipant,
    ReceiptSplitRead,
    ReceiptState,
    ReceiptTotalExtraction,
)
from app.services import ai as ai_service
from app.services import categories as categories_service
from app.services import expenses as expenses_service
from app.services import groups as groups_service
from app.services import uploads as uploads_service
from app.services.common import require_group
from app.services.errors import ConflictError, ForbiddenError, InvalidInputError, NotFoundError
from app.storage import BlobStorage, get_storage
from app.utils.currency import decimal_digits
from app.utils.receipt_extraction import (
    normalize_receipt,
    parse_receipt_items_response,
)
from app.utils.receipt_split import (
    ReceiptSplitResult,
    compute_receipt_split,
    to_receipt_split_items,
)

# ---------------------------------------------------------------------------
# Serializable views
# ---------------------------------------------------------------------------


_PUBLIC_PROVIDER_LABELS = {"openai-compatible", "google", "disabled"}


def _public_provider(provider: str | None) -> str | None:
    """Collapse legacy stored provider values that may contain a base URL."""
    if provider is None:
        return None
    if provider in _PUBLIC_PROVIDER_LABELS:
        return provider
    lowered = provider.lower()
    if "google" in lowered or "generativelanguage" in lowered:
        return "google"
    return "openai-compatible"


def _receipt_read(receipt: Receipt) -> ReceiptRead:
    return ReceiptRead(
        id=receipt.id,
        group_id=receipt.group_id,
        image_url=receipt.image_url,
        image_width=receipt.image_width,
        image_height=receipt.image_height,
        status=receipt.status,
        attempts=receipt.attempts,
        merchant=receipt.merchant,
        receipt_date=receipt.receipt_date.date() if receipt.receipt_date else None,
        currency_code=receipt.currency_code,
        total=receipt.total,
        expense_id=receipt.expense_id,
        provider=_public_provider(receipt.provider),
        model=receipt.model,
        created_at=receipt.created_at,
        updated_at=receipt.updated_at,
        version=receipt.version,
        deleted_at=receipt.deleted_at,
    )


def _portion_read(portion: ReceiptItemPortion) -> ReceiptPortionRead:
    return ReceiptPortionRead(
        id=portion.id,
        item_id=portion.item_id,
        target=portion.target,
        participant_id=portion.participant_id,
        quantity_milli=portion.quantity_milli,
        version=portion.version,
    )


def _item_read(item: ReceiptItem, portions: list[ReceiptItemPortion]) -> ReceiptItemRead:
    return ReceiptItemRead(
        id=item.id,
        receipt_id=item.receipt_id,
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


def _split_read(split: ReceiptSplitResult, items: list[ReceiptItem]) -> ReceiptSplitRead:
    adjustments = sum(item.amount for item in items if item.is_adjustment)
    return ReceiptSplitRead(
        participants=[
            ReceiptSplitParticipant(
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
# Loading and split computation
# ---------------------------------------------------------------------------


def _require_receipt(
    session: Session,
    group_id: str,
    receipt_id: str,
    *,
    include_deleted: bool = False,
) -> Receipt:
    require_group(session, group_id)
    receipt = session.get(Receipt, receipt_id)
    if (
        receipt is None
        or receipt.group_id != group_id
        or (receipt.deleted_at is not None and not include_deleted)
    ):
        raise NotFoundError("Receipt not found")
    return receipt


def get_receipt_by_image(session: Session, group_id: str, image_url: str) -> Receipt | None:
    return session.exec(
        select(Receipt).where(
            Receipt.group_id == group_id,
            Receipt.image_url == image_url,
            Receipt.deleted_at.is_(None),
        )
    ).first()


def get_receipt_for_expense(
    session: Session,
    group_id: str,
    expense_id: str,
) -> Receipt | None:
    return session.exec(
        select(Receipt).where(
            Receipt.group_id == group_id,
            Receipt.expense_id == expense_id,
            Receipt.deleted_at.is_(None),
        )
    ).first()


def _items_with_portions(
    session: Session,
    receipt_id: str,
) -> list[tuple[ReceiptItem, list[ReceiptItemPortion]]]:
    items = list(
        session.exec(
            select(ReceiptItem)
            .where(
                ReceiptItem.receipt_id == receipt_id,
                ReceiptItem.deleted_at.is_(None),
            )
            .order_by(ReceiptItem.position.asc(), ReceiptItem.id.asc())
        ).all()
    )
    if not items:
        return []
    item_ids = [item.id for item in items]
    portions = list(
        session.exec(
            select(ReceiptItemPortion)
            .where(
                ReceiptItemPortion.item_id.in_(item_ids),
                ReceiptItemPortion.deleted_at.is_(None),
            )
            .order_by(ReceiptItemPortion.created_at.asc(), ReceiptItemPortion.id.asc())
        ).all()
    )
    by_item: dict[str, list[ReceiptItemPortion]] = {item.id: [] for item in items}
    for portion in portions:
        by_item.setdefault(portion.item_id, []).append(portion)
    return [(item, by_item.get(item.id, [])) for item in items]


def _opt_out_ids(session: Session, receipt_id: str) -> list[str]:
    rows = session.exec(
        select(ReceiptOptOut)
        .where(
            ReceiptOptOut.receipt_id == receipt_id,
            ReceiptOptOut.deleted_at.is_(None),
        )
        .order_by(ReceiptOptOut.participant_id.asc())
    ).all()
    return [row.participant_id for row in rows]


def compute_receipt_split_for(
    session: Session,
    receipt: Receipt,
    group_id: str,
) -> tuple[ReceiptSplitResult, list[tuple[ReceiptItem, list[ReceiptItemPortion]]]]:
    """Recompute provisional totals from stored items and live participants."""
    participants = groups_service.get_participants(session, group_id)
    pairs = _items_with_portions(session, receipt.id)
    split = compute_receipt_split(
        [participant.id for participant in participants],
        _opt_out_ids(session, receipt.id),
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


def receipt_state(session: Session, group_id: str, receipt: Receipt) -> ReceiptState:
    split, pairs = compute_receipt_split_for(session, receipt, group_id)
    return ReceiptState(
        receipt=_receipt_read(receipt),
        items=[_item_read(item, portions) for item, portions in pairs],
        opt_outs=_opt_out_ids(session, receipt.id),
        split=_split_read(split, [item for item, _portions in pairs]),
    )


def get_receipt_state(
    session: Session,
    group_id: str,
    *,
    receipt_id: str | None = None,
    expense_id: str | None = None,
) -> ReceiptState:
    if receipt_id is None and expense_id is None:
        raise InvalidInputError("Either receipt_id or expense_id is required")
    if receipt_id is not None:
        receipt = _require_receipt(session, group_id, receipt_id)
    else:
        receipt = get_receipt_for_expense(session, group_id, expense_id or "")
        if receipt is None:
            raise NotFoundError("Receipt not found")
    return receipt_state(session, group_id, receipt)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def create_pending_receipt(
    session: Session,
    *,
    group_id: str,
    image_url: str,
    image_width: int | None = None,
    image_height: int | None = None,
    now: datetime | None = None,
) -> Receipt:
    """Create a PENDING receipt, returning the winner of a concurrent race."""
    require_group(session, group_id)
    moment = now or utc_now()
    receipt = Receipt(
        id=new_id("rcpt"),
        group_id=group_id,
        image_url=image_url,
        image_width=image_width,
        image_height=image_height,
        status=ReceiptStatus.PENDING.value,
        created_at=moment,
        updated_at=moment,
        version=1,
    )
    session.add(receipt)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = get_receipt_by_image(session, group_id, image_url)
        if existing is None:
            raise ConflictError("Receipt already exists") from None
        return existing
    session.refresh(receipt)
    return receipt


def claim_receipt_for_extraction(
    session: Session,
    receipt_id: str,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> bool:
    """Atomically claim a paid extraction, up to ``receipt_max_attempts``.

    Returns ``False`` when another worker already owns the receipt. Once the
    configured attempt budget is exhausted a :class:`ConflictError` is raised
    so the caller gets a clear 409 instead of silently paying for another call.
    """
    moment = now or utc_now()
    stale_before = moment - timedelta(seconds=settings.receipt_extraction_stale_seconds)
    result = session.execute(
        update(Receipt)
        .where(
            Receipt.id == receipt_id,
            Receipt.deleted_at.is_(None),
            Receipt.attempts < settings.receipt_max_attempts,
            or_(
                Receipt.status.in_([ReceiptStatus.PENDING.value, ReceiptStatus.FAILED.value]),
                (Receipt.status == ReceiptStatus.EXTRACTING.value)
                & (Receipt.updated_at < stale_before),
            ),
        )
        .values(
            status=ReceiptStatus.EXTRACTING.value,
            attempts=Receipt.attempts + 1,
            updated_at=moment,
            version=Receipt.version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    session.commit()
    if (result.rowcount or 0) == 1:
        return True

    receipt = session.get(Receipt, receipt_id)
    if (
        receipt is not None
        and receipt.deleted_at is None
        and receipt.attempts >= settings.receipt_max_attempts
        and (
            receipt.status in (ReceiptStatus.PENDING.value, ReceiptStatus.FAILED.value)
            or (
                receipt.status == ReceiptStatus.EXTRACTING.value
                and receipt.updated_at < stale_before
            )
        )
    ):
        raise ConflictError("Receipt extraction attempts are exhausted. Upload the receipt again.")
    return False


def _parse_receipt_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return datetime.combine(parsed, time(12, 0), tzinfo=UTC)


def complete_receipt(
    session: Session,
    receipt_id: str,
    *,
    raw_extraction: str | None,
    provider: str | None,
    model: str | None,
    normalized: dict[str, Any],
    now: datetime | None = None,
) -> Receipt:
    """Store a successful extraction and replace the receipt's items."""
    moment = now or utc_now()
    receipt = session.get(Receipt, receipt_id)
    if receipt is None:
        raise NotFoundError("Receipt not found")

    item_ids = [
        item_id
        for item_id in session.exec(
            select(ReceiptItem.id).where(ReceiptItem.receipt_id == receipt_id)
        ).all()
        if item_id is not None
    ]
    if item_ids:
        session.execute(delete(ReceiptItemPortion).where(ReceiptItemPortion.item_id.in_(item_ids)))
    session.execute(delete(ReceiptItem).where(ReceiptItem.receipt_id == receipt_id))

    total = normalized.get("total")
    if total is None:
        total = normalized.get("items_total")

    receipt.status = ReceiptStatus.EXTRACTED.value
    receipt.raw_extraction = raw_extraction
    receipt.provider = provider
    receipt.model = model
    receipt.merchant = normalized.get("merchant")
    receipt.receipt_date = _parse_receipt_date(normalized.get("date"))
    receipt.currency_code = normalized.get("currency_code")
    receipt.total = total
    receipt.updated_at = moment
    receipt.version += 1
    session.add(receipt)

    for item in normalized.get("items", []):
        session.add(
            ReceiptItem(
                id=new_id("ritem"),
                receipt_id=receipt_id,
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
    session.refresh(receipt)
    return receipt


def fail_receipt(
    session: Session,
    receipt_id: str,
    *,
    raw_extraction: str | None,
    provider: str | None,
    model: str | None,
    now: datetime | None = None,
) -> None:
    receipt = session.get(Receipt, receipt_id)
    if receipt is None:
        return
    receipt.status = ReceiptStatus.FAILED.value
    receipt.raw_extraction = raw_extraction
    receipt.provider = provider
    receipt.model = model
    receipt.updated_at = now or utc_now()
    receipt.version += 1
    session.add(receipt)
    session.commit()


def link_receipt_to_expense(
    session: Session,
    group_id: str,
    receipt_id: str,
    expense_id: str | None,
    *,
    now: datetime | None = None,
) -> Receipt:
    receipt = _require_receipt(session, group_id, receipt_id)
    if expense_id is not None:
        expense = session.get(Expense, expense_id)
        if expense is None or expense.group_id != group_id or expense.deleted_at is not None:
            raise NotFoundError("Expense not found")
    if receipt.expense_id == expense_id:
        return receipt

    receipt.expense_id = expense_id
    receipt.updated_at = now or utc_now()
    receipt.version += 1
    session.add(receipt)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ConflictError("Expense already has a linked receipt") from None
    session.refresh(receipt)
    return receipt


# ---------------------------------------------------------------------------
# Item mutations
# ---------------------------------------------------------------------------


def _require_item(session: Session, receipt: Receipt, item_id: str) -> ReceiptItem:
    item = session.get(ReceiptItem, item_id)
    if item is None or item.receipt_id != receipt.id or item.deleted_at is not None:
        raise NotFoundError("Item not found")
    return item


def _check_item_values(
    settings: Settings | None,
    *,
    name: str | None = None,
    quantity_milli: int | None = None,
    amount: int | None = None,
) -> None:
    """Apply configured limits in addition to the schema's hard caps."""
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
    """Apply the configured item caps to model output before storing it.

    Charges are folded into the same item list by ``normalize_receipt``; the
    adjustment row is allowed to have a negative amount because it reconciles
    the printed total.
    """
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
    """Bound both model-produced arrays, even if the provider ignored the schema."""
    return {
        **parsed,
        "items": list(parsed.get("items", []))[:limit],
        "charges": list(parsed.get("charges", []))[:limit],
    }


def add_item(
    session: Session,
    group_id: str,
    receipt_id: str,
    payload: ReceiptItemCreate,
    *,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> ReceiptState:
    receipt = _require_receipt(session, group_id, receipt_id)
    item_id = payload.id or new_id("ritem")
    if payload.id is not None:
        existing_item = session.get(ReceiptItem, item_id)
        if existing_item is not None:
            if existing_item.receipt_id == receipt.id and existing_item.deleted_at is None:
                # Idempotent replay of a create whose response was lost.
                return receipt_state(session, group_id, receipt)
            raise InvalidInputError("Receipt item id already exists", field="id")
    _check_item_values(
        settings,
        name=payload.name,
        quantity_milli=payload.quantity_milli,
        amount=payload.amount,
    )
    if settings is not None:
        existing_count = session.exec(
            select(func.count(ReceiptItem.id)).where(
                ReceiptItem.receipt_id == receipt.id,
                ReceiptItem.deleted_at.is_(None),
            )
        ).one()
        if int(existing_count) >= settings.max_receipt_items:
            raise InvalidInputError("Receipt has too many items", field="items")
    moment = now or utc_now()
    maximum = session.exec(
        select(func.max(ReceiptItem.position)).where(ReceiptItem.receipt_id == receipt.id)
    ).one()
    position = (int(maximum) if maximum is not None else -1) + 1
    session.add(
        ReceiptItem(
            id=item_id,
            receipt_id=receipt.id,
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
    receipt.updated_at = moment
    receipt.version += 1
    session.add(receipt)
    session.commit()
    session.refresh(receipt)
    return receipt_state(session, group_id, receipt)


def update_item(
    session: Session,
    group_id: str,
    receipt_id: str,
    item_id: str,
    payload: ReceiptItemUpdate,
    *,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> ReceiptState:
    receipt = _require_receipt(session, group_id, receipt_id)
    item = _require_item(session, receipt, item_id)
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
    receipt.updated_at = moment
    receipt.version += 1
    session.add(item)
    session.add(receipt)
    session.commit()
    session.refresh(receipt)
    return receipt_state(session, group_id, receipt)


def delete_item(
    session: Session,
    group_id: str,
    receipt_id: str,
    item_id: str,
    *,
    now: datetime | None = None,
) -> ReceiptState:
    receipt = _require_receipt(session, group_id, receipt_id)
    item = session.get(ReceiptItem, item_id)
    if item is not None and item.receipt_id != receipt.id:
        raise NotFoundError("Item not found")
    if item is None or item.deleted_at is not None:
        # Retries after a lost response must be idempotent: the first delete
        # already removed the row, so return the current receipt state.
        return receipt_state(session, group_id, receipt)
    session.execute(delete(ReceiptItemPortion).where(ReceiptItemPortion.item_id == item.id))
    session.delete(item)
    moment = now or utc_now()
    receipt.updated_at = moment
    receipt.version += 1
    session.add(receipt)
    session.commit()
    session.refresh(receipt)
    return receipt_state(session, group_id, receipt)


def set_item_portions(
    session: Session,
    group_id: str,
    receipt_id: str,
    item_id: str,
    portions: list[ReceiptPortionInput],
    *,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> ReceiptState:
    receipt = _require_receipt(session, group_id, receipt_id)
    item = _require_item(session, receipt, item_id)
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

    session.execute(delete(ReceiptItemPortion).where(ReceiptItemPortion.item_id == item.id))
    moment = now or utc_now()
    for portion in portions:
        session.add(
            ReceiptItemPortion(
                id=new_id("rport"),
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
    receipt.updated_at = moment
    receipt.version += 1
    session.add(item)
    session.add(receipt)
    session.commit()
    session.refresh(receipt)
    return receipt_state(session, group_id, receipt)


def set_opt_out(
    session: Session,
    group_id: str,
    receipt_id: str,
    participant_id: str,
    opted_out: bool,
    *,
    now: datetime | None = None,
) -> ReceiptState:
    receipt = _require_receipt(session, group_id, receipt_id)
    participant = session.get(Participant, participant_id)
    if (
        participant is None
        or participant.group_id != group_id
        or participant.deleted_at is not None
    ):
        raise InvalidInputError("Participant is not in the group", field="participant_id")

    moment = now or utc_now()
    existing = session.exec(
        select(ReceiptOptOut).where(
            ReceiptOptOut.receipt_id == receipt.id,
            ReceiptOptOut.participant_id == participant_id,
        )
    ).first()
    if opted_out:
        if existing is None:
            session.add(
                ReceiptOptOut(
                    id=new_id("ropt"),
                    receipt_id=receipt.id,
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

    receipt.updated_at = moment
    receipt.version += 1
    session.add(receipt)
    session.commit()
    session.refresh(receipt)
    return receipt_state(session, group_id, receipt)


# ---------------------------------------------------------------------------
# Apply to an expense
# ---------------------------------------------------------------------------


def apply_receipt_to_expense(
    session: Session,
    group_id: str,
    receipt_id: str,
    expense_id: str,
    *,
    participant_id: str | None = None,
    now: datetime | None = None,
) -> tuple[Receipt, Any, ReceiptSplitResult]:
    receipt = _require_receipt(session, group_id, receipt_id)
    expense = session.get(Expense, expense_id)
    if expense is None or expense.group_id != group_id or expense.deleted_at is not None:
        raise NotFoundError("Expense not found")

    split, _pairs = compute_receipt_split_for(session, receipt, group_id)

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
    moment = now or utc_now()
    expenses_service.update_expense(
        session,
        group_id,
        expense_id,
        payload,
        now=moment,
        commit=False,
    )

    receipt.expense_id = expense_id
    receipt.updated_at = moment
    receipt.version += 1
    session.add(receipt)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ConflictError("Expense already has a linked receipt") from None
    session.refresh(receipt)

    expense_read = expenses_service.get_expense(session, group_id, expense_id)
    return receipt, expense_read, split


# ---------------------------------------------------------------------------
# AI extraction
# ---------------------------------------------------------------------------


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


def extract_total(
    session: Session,
    settings: Settings,
    *,
    group_id: str,
    image_url: str,
    ai_client: Any = None,
    storage: BlobStorage | None = None,
) -> ReceiptTotalExtraction:
    if not settings.receipt_extract_enabled:
        raise ForbiddenError("Receipt extraction is not enabled.")
    require_group(session, group_id)
    storage = storage or get_storage(settings)
    image = uploads_service.resolve_image_for_ai(
        session,
        storage,
        settings,
        group_id=group_id,
        image_url=image_url,
    )
    _categories, options = _category_options(session)
    prompt = ai_service.build_receipt_extract_prompt(options)

    try:
        content = _call_ai(
            settings,
            ai_client=ai_client,
            model=settings.receipt_extract_model,
            messages=[
                {"role": "user", "content": [{"type": "text", "text": prompt}]},
                {"role": "user", "content": [{"type": "image_url", "image_url": {"url": image}}]},
            ],
            response_format=ai_service.RECEIPT_EXTRACT_JSON_SCHEMA,
        )
    except ai_service.AiError:
        return ReceiptTotalExtraction()

    parsed = _parse_total_response(content)
    if parsed is None:
        return ReceiptTotalExtraction()
    return ReceiptTotalExtraction(
        amount=parsed["amount"],
        category_id=parsed["category_id"],
        date=parsed["date"],
        title=parsed["title"],
    )


def _extraction_result(
    session: Session,
    group_id: str,
    receipt: Receipt,
    *,
    status: str,
    category_id: str | None = None,
) -> ReceiptExtractionResult:
    state = receipt_state(session, group_id, receipt)
    if category_id is None and receipt.raw_extraction:
        parsed = parse_receipt_items_response(receipt.raw_extraction)
        if parsed is not None:
            category_id = parsed.get("category_id")
    return ReceiptExtractionResult(
        status=status,
        receipt_id=receipt.id,
        total=receipt.total,
        items_total=state.split.items_total,
        merchant=receipt.merchant,
        date=receipt.receipt_date.date().isoformat() if receipt.receipt_date else None,
        currency_code=receipt.currency_code,
        category_id=category_id,
        receipt=state.receipt,
        items=state.items,
        opt_outs=state.opt_outs,
        split=state.split,
    )


def extract_items(
    session: Session,
    settings: Settings,
    *,
    group_id: str,
    image_url: str,
    image_width: int | None = None,
    image_height: int | None = None,
    ai_client: Any = None,
    storage: BlobStorage | None = None,
) -> ReceiptExtractionResult:
    if not settings.enable_receipt_items:
        raise ForbiddenError("Receipt items extraction is not enabled.")
    group = require_group(session, group_id)
    storage = storage or get_storage(settings)
    image = uploads_service.resolve_image_for_ai(
        session,
        storage,
        settings,
        group_id=group_id,
        image_url=image_url,
    )

    existing = get_receipt_by_image(session, group_id, image_url)
    if existing is not None and existing.status == ReceiptStatus.EXTRACTED.value:
        return _extraction_result(
            session,
            group_id,
            existing,
            status=ReceiptStatus.EXTRACTED.value,
        )

    receipt = existing or create_pending_receipt(
        session,
        group_id=group_id,
        image_url=image_url,
        image_width=image_width,
        image_height=image_height,
    )

    if not claim_receipt_for_extraction(session, receipt.id, settings=settings):
        raise ConflictError("Receipt extraction is already in progress.")
    session.refresh(receipt)

    _categories, options = _category_options(session)
    prompt = ai_service.build_receipt_items_prompt(options)
    model = settings.receipt_items_model
    provider = settings.ai_provider_label

    try:
        content = _call_ai(
            settings,
            ai_client=ai_client,
            model=model,
            messages=[
                {"role": "user", "content": [{"type": "text", "text": prompt}]},
                {"role": "user", "content": [{"type": "image_url", "image_url": {"url": image}}]},
            ],
            response_format=ai_service.RECEIPT_ITEMS_RESPONSE_FORMAT,
        )
    except ai_service.AiError:
        fail_receipt(
            session,
            receipt.id,
            raw_extraction=None,
            provider=provider,
            model=model,
        )
        session.refresh(receipt)
        return _extraction_result(
            session,
            group_id,
            receipt,
            status=ReceiptStatus.FAILED.value,
        )

    parsed = parse_receipt_items_response(content, limit=settings.max_receipt_items)
    if parsed is not None:
        parsed = _cap_extraction_lists(parsed, settings.max_receipt_items)
    if parsed is None:
        fail_receipt(
            session,
            receipt.id,
            raw_extraction=content,
            provider=provider,
            model=model,
        )
        session.refresh(receipt)
        return _extraction_result(
            session,
            group_id,
            receipt,
            status=ReceiptStatus.FAILED.value,
        )

    normalized = normalize_receipt(parsed, decimal_digits(group.currency_code))
    try:
        _validate_normalized_items(settings, normalized)
    except InvalidInputError:
        fail_receipt(
            session,
            receipt.id,
            raw_extraction=content,
            provider=provider,
            model=model,
        )
        session.refresh(receipt)
        return _extraction_result(
            session,
            group_id,
            receipt,
            status=ReceiptStatus.FAILED.value,
        )
    receipt = complete_receipt(
        session,
        receipt.id,
        raw_extraction=content,
        provider=provider,
        model=model,
        normalized=normalized,
    )
    return _extraction_result(
        session,
        group_id,
        receipt,
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
        raise ForbiddenError("Category extraction is not enabled.")
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
    except ai_service.AiError:
        return 0

    parsed = _parse_category_response(content)
    if parsed is None:
        return 0
    for category in categories:
        if category.id == parsed:
            return int(category.id or 0)
    return 0
