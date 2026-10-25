"""Receipt line-item allocation.

Pure mirror of ``spliit/src/lib/receipt-split.ts``. Money is integer minor
units and quantities are integer thousandths. The module deliberately has no
I/O or database dependencies: the API recomputes provisional totals from stored
items with these functions, and Stage 9C reuses the same fixtures in
JavaScript.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.utils.shares import distribute_amount, weighted_apportion

PARTICIPANT = "PARTICIPANT"
SHARED = "SHARED"


@dataclass(frozen=True)
class ReceiptPortion:
    target: str
    participant_id: str | None
    quantity_milli: int


@dataclass(frozen=True)
class ReceiptSplitItem:
    amount: int
    quantity_milli: int
    portions: list[ReceiptPortion] = field(default_factory=list)


@dataclass(frozen=True)
class ConsumedPortion:
    target: str
    participant_id: str | None
    quantity_milli: int


@dataclass(frozen=True)
class ParticipantReceiptShare:
    participant_id: str
    direct: int
    shared: int
    unassigned: int
    total: int


@dataclass(frozen=True)
class ReceiptSplitResult:
    participants: list[ParticipantReceiptShare]
    items_total: int
    shared_pool: int
    unassigned_pool: int
    all_opted_out: bool


def _value(source: Any, *keys: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        for key in keys:
            if key in source:
                return source[key]
        return default
    for key in keys:
        if hasattr(source, key):
            return getattr(source, key)
    return default


def _portion(source: Any) -> ReceiptPortion:
    if isinstance(source, ReceiptPortion):
        return source
    return ReceiptPortion(
        target=str(_value(source, "target", default=PARTICIPANT)),
        participant_id=_value(source, "participant_id", "participantId"),
        quantity_milli=int(_value(source, "quantity_milli", "quantityMilli", default=0)),
    )


def _split_item(source: Any) -> ReceiptSplitItem:
    if isinstance(source, ReceiptSplitItem):
        return source
    return ReceiptSplitItem(
        amount=int(_value(source, "amount", default=0)),
        quantity_milli=int(_value(source, "quantity_milli", "quantityMilli", default=1000)),
        portions=[_portion(portion) for portion in (_value(source, "portions", default=[]) or [])],
    )


def to_receipt_split_items(items: Iterable[Any]) -> list[ReceiptSplitItem]:
    """Map stored items to split inputs.

    Stored portions take precedence; ``is_shared`` is only a fallback for a
    shared item that has no portions stored yet.
    """
    result: list[ReceiptSplitItem] = []
    for raw in items:
        item = _split_item(raw)
        portions = item.portions
        if not portions and bool(_value(raw, "is_shared", "isShared", default=False)):
            portions = [
                ReceiptPortion(
                    target=SHARED,
                    participant_id=None,
                    quantity_milli=item.quantity_milli,
                )
            ]
        result.append(
            ReceiptSplitItem(
                amount=item.amount,
                quantity_milli=item.quantity_milli,
                portions=portions,
            )
        )
    return result


def _trunc_quantity(value: Any) -> float:
    """Return ``Math.trunc(value) || 0`` for the item-quantity fallback."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if math.isnan(number):
        return 0
    if math.isinf(number):
        return number
    return float(int(number))  # int() truncates toward zero, like Math.trunc.


def _consume_quantity(value: Any) -> float:
    """Return ``Math.floor(value)`` while tolerating non-numeric input."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if math.isnan(number):
        return 0
    if math.isinf(number):
        return number
    return float(math.floor(number))


def _whole(value: float) -> int | None:
    """Convert a finite quantity back to an integer for the result model."""
    if not math.isfinite(value):
        return None
    return int(value)


def consume_item_portions(
    item: Any,
    known_participant_ids: Iterable[str] | set[str],
) -> tuple[list[ConsumedPortion], int | None]:
    """Consume an item's portions against its own quantity.

    Portion quantities are floored, non-positive quantities are dropped, and
    every portion is clamped to the running budget. Participant portions whose
    participant is missing or not in the group are ignored. A zero, negative or
    NaN item quantity still counts as one whole unit.
    """
    split_item = _split_item(item)
    known = set(known_participant_ids)
    total = max(_trunc_quantity(split_item.quantity_milli), 1.0)
    remaining = total
    portions: list[ConsumedPortion] = []

    for portion in split_item.portions:
        quantity = _consume_quantity(portion.quantity_milli)
        if not quantity > 0:
            continue
        if portion.target == PARTICIPANT:
            participant_id = portion.participant_id
            if not participant_id or participant_id not in known:
                continue
            allowed = min(quantity, remaining)
            if allowed <= 0:
                continue
            remaining -= allowed
            portions.append(
                ConsumedPortion(
                    target=PARTICIPANT,
                    participant_id=participant_id,
                    quantity_milli=_whole(allowed) or 0,
                )
            )
        else:
            allowed = min(quantity, remaining)
            if allowed <= 0:
                continue
            remaining -= allowed
            portions.append(
                ConsumedPortion(
                    target=SHARED,
                    participant_id=None,
                    quantity_milli=_whole(allowed) or 0,
                )
            )

    return portions, _whole(remaining)


def compute_receipt_split(
    participant_ids: Sequence[str],
    opted_out_participant_ids: Sequence[str],
    items: Iterable[Any],
) -> ReceiptSplitResult:
    """Split a receipt's line items across participants.

    Each item's line total is apportioned over the quantities its portions claim
    (largest remainder, so cents are never lost). Whatever quantity is left over
    becomes an unassigned pool shared by participants who did not opt out.
    Shared portions (whole-bill charges) are spread over every participant,
    opt-outs included.
    """
    # Preserve order while de-duplicating, matching Array.from(new Set(...)).
    participants = list(dict.fromkeys(str(participant_id) for participant_id in participant_ids))
    participant_set = set(participants)
    opted_out = {
        str(participant_id)
        for participant_id in opted_out_participant_ids
        if str(participant_id) in participant_set
    }

    item_list = [_split_item(item) for item in items]

    direct: dict[str, int] = {}
    shared_pool = 0
    unassigned_pool = 0

    for item in item_list:
        portions, unassigned = consume_item_portions(item, participant_set)
        unassigned_value = unassigned or 0

        destinations: list[tuple[str, str | None]] = []
        weights: list[int] = []
        shared_weight = 0

        for portion in portions:
            if portion.target == PARTICIPANT and portion.participant_id is not None:
                weights.append(portion.quantity_milli)
                destinations.append(("direct", portion.participant_id))
            else:
                shared_weight += portion.quantity_milli

        if shared_weight > 0:
            weights.append(shared_weight)
            destinations.append(("shared", None))
        if unassigned_value > 0:
            weights.append(unassigned_value)
            destinations.append(("unassigned", None))

        amounts = weighted_apportion(item.amount, weights)
        for (kind, participant_id), amount in zip(destinations, amounts, strict=True):
            if kind == "direct" and participant_id is not None:
                direct[participant_id] = direct.get(participant_id, 0) + amount
            elif kind == "shared":
                shared_pool += amount
            else:
                unassigned_pool += amount

    shared_shares = distribute_amount(shared_pool, len(participants))
    sharers = [participant for participant in participants if participant not in opted_out]
    unassigned_shares = distribute_amount(unassigned_pool, len(sharers))
    sharer_index = {participant: index for index, participant in enumerate(sharers)}

    participant_shares = []
    for index, participant_id in enumerate(participants):
        direct_amount = direct.get(participant_id, 0)
        shared_amount = shared_shares[index] if index < len(shared_shares) else 0
        unassigned_amount = 0
        if participant_id not in opted_out:
            position = sharer_index.get(participant_id)
            if position is not None and position < len(unassigned_shares):
                unassigned_amount = unassigned_shares[position]
        participant_shares.append(
            ParticipantReceiptShare(
                participant_id=participant_id,
                direct=direct_amount,
                shared=shared_amount,
                unassigned=unassigned_amount,
                total=direct_amount + shared_amount + unassigned_amount,
            )
        )

    return ReceiptSplitResult(
        participants=participant_shares,
        items_total=sum(item.amount for item in item_list),
        shared_pool=shared_pool,
        unassigned_pool=unassigned_pool,
        all_opted_out=len(sharers) == 0 and unassigned_pool != 0,
    )
