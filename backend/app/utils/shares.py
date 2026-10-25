"""Expense share apportionment.

Pure mirror of ``spliit/src/lib/shares.ts``. Money is integer minor units and
shares always add up to exactly the expense amount, including negative amounts
(income) and legacy rows whose stored share totals do not satisfy the form
invariants.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

EVENLY = "EVENLY"


def hash_string(value: str) -> int:
    """FNV-1a over JavaScript UTF-16 code units, returned unsigned."""
    result = 0x811C9DC5
    encoded = value.encode("utf-16-le")
    for index in range(0, len(encoded), 2):
        code_unit = int.from_bytes(encoded[index : index + 2], "little")
        result ^= code_unit
        result = (result * 0x01000193) & 0xFFFFFFFF
    return result


def apportion(amount: int, shares: Sequence[int], total_shares: int, offset: int) -> list[int]:
    """Split ``amount`` over ``shares`` using largest-remainder apportionment.

    Every participant first receives the floor of their exact share; leftover
    units go to the largest remainders. Ties rotate from ``offset`` so an even
    split does not always favour the same participants.
    """
    count = len(shares)
    if count == 0:
        return []
    if total_shares == 0:
        return [0] * count

    amounts: list[int] = []
    remainders: list[tuple[int, int]] = []
    distributed = 0

    for index, share in enumerate(shares):
        exact = amount * share
        base = exact // total_shares  # Python's // floors, matching Math.floor.
        amounts.append(base)
        distributed += base
        remainders.append((index, exact - base * total_shares))

    remaining = amount - distributed
    if remaining == 0:
        return amounts

    def rotation(index: int) -> int:
        return (index - offset + count) % count

    remainders.sort(key=lambda item: (-item[1], rotation(item[0])))
    # The mathematical budget is non-negative and smaller than the participant
    # count for valid inputs. Guard rather than IndexError on corrupt rows.
    for index, _remainder in remainders[: max(0, min(remaining, count))]:
        amounts[index] += 1
    return amounts


def distribute_amount(amount: int, count: int) -> list[int]:
    """Split ``amount`` into ``count`` even shares that add up exactly."""
    return apportion(amount, [1] * count, count, 0)


def weighted_apportion(amount: int, weights: Sequence[int]) -> list[int]:
    """Split ``amount`` proportionally to integer weights."""
    if not weights:
        return []
    return apportion(amount, weights, sum(weights), 0)


@dataclass(frozen=True)
class ShareRow:
    participant_id: str
    shares: int


def _paid_for_rows(expense: Mapping[str, Any]) -> list[ShareRow]:
    raw = expense.get("paid_for")
    if raw is None:
        raw = expense.get("paidFor") or []
    rows: list[ShareRow] = []
    for item in raw:  # type: ignore[union-attr]
        if not isinstance(item, Mapping):
            continue
        participant_id = item.get("participant_id")
        if participant_id is None and isinstance(item.get("participant"), Mapping):
            participant_id = item["participant"].get("id")
        if participant_id is None:
            continue
        shares = item.get("shares", 1)
        rows.append(ShareRow(str(participant_id), int(shares)))
    return rows


def _split_mode(expense: Mapping[str, Any]) -> str:
    return str(expense.get("split_mode", expense.get("splitMode", EVENLY)))


def get_expense_shares(expense: Mapping[str, Any]) -> dict[str, int]:
    """Return each paid-for participant's whole-minor-unit share."""
    paid_for = sorted(_paid_for_rows(expense), key=lambda row: row.participant_id)
    split_mode = _split_mode(expense)

    weights = (
        [1] * len(paid_for)
        if split_mode not in {"BY_SHARES", "BY_PERCENTAGE", "BY_AMOUNT"}
        else [row.shares for row in paid_for]
    )
    total_shares = sum(weights)

    expense_id = expense.get("id")
    offset = 0
    if expense_id and paid_for:
        offset = hash_string(str(expense_id)) % len(paid_for)

    amount = int(expense.get("amount", 0))
    amounts = apportion(amount, weights, total_shares, offset)
    return {row.participant_id: amount for row, amount in zip(paid_for, amounts, strict=True)}


def get_participant_share(participant_id: str | None, expense: Mapping[str, Any]) -> int:
    """Return one participant's share, or ``0`` when they were not paid for."""
    if participant_id is None:
        return 0
    return get_expense_shares(expense).get(participant_id, 0)
