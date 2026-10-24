"""Reference-compatible balance calculation for import verification.

This is intentionally an independent, small mirror of
``spliit/src/lib/balances.ts`` and ``shares.ts``. Stage 3 will build the full
Python domain core; Stage 2 needs just enough to prove that imported rows
produce the same balances as the reference application.

The algorithm keeps every share a whole minor unit and uses FNV-1a seeded
largest-remainder apportionment, matching the reference exactly.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

FNV_OFFSET_BASIS = 0x811C9DC5
FNV_PRIME = 0x01000193
UINT32_MASK = 0xFFFFFFFF


def fnv1a_hash(value: str) -> int:
    """FNV-1a 32-bit hash over UTF-16 code units, matching JavaScript.

    ``charCodeAt`` iterates UTF-16 code units, so astral characters contribute
    two units (a surrogate pair), exactly as they do in the reference.
    """
    result = FNV_OFFSET_BASIS
    encoded = value.encode("utf-16-le", errors="surrogatepass")
    for index in range(0, len(encoded), 2):
        code_unit = int.from_bytes(encoded[index : index + 2], "little")
        result ^= code_unit
        result = (result * FNV_PRIME) & UINT32_MASK
    return result


def js_string_key(value: str) -> bytes:
    """Sort key matching JavaScript's UTF-16 code-unit string ordering."""
    return value.encode("utf-16-be", errors="surrogatepass")


def apportion(
    amount: int,
    shares: list[int],
    total_shares: int,
    offset: int,
) -> list[int]:
    """Largest-remainder apportionment with reference tie-breaking."""
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
        base = exact // total_shares  # floor, including negative amounts
        amounts.append(base)
        distributed += base
        remainders.append((index, exact - base * total_shares))

    remaining = amount - distributed
    if remaining == 0:
        return amounts

    def rotated(index: int) -> int:
        return (index - offset + count) % count

    remainders.sort(key=lambda item: (-item[1], rotated(item[0])))
    for position in range(remaining):
        amounts[remainders[position][0]] += 1
    return amounts


def get_expense_shares(
    expense_id: str | None,
    amount: int,
    split_mode: str,
    paid_for: list[dict[str, Any]],
) -> dict[str, int]:
    """Return the share of ``amount`` for each paid-for participant."""
    ordered = sorted(paid_for, key=lambda row: js_string_key(str(row["participant_id"])))
    if split_mode in ("BY_SHARES", "BY_PERCENTAGE", "BY_AMOUNT"):
        shares = [int(row["shares"]) for row in ordered]
    else:
        # EVENLY and any unknown mode default to equal shares, as in the app.
        shares = [1 for _ in ordered]
    total_shares = sum(shares)
    offset = fnv1a_hash(expense_id) % len(ordered) if expense_id and ordered else 0
    amounts = apportion(amount, shares, total_shares, offset)
    return {str(row["participant_id"]): amounts[index] for index, row in enumerate(ordered)}


def balances_for_group(expenses: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Compute ``paid`` / ``paidFor`` / ``total`` per participant."""
    balances: dict[str, dict[str, int]] = {}

    for expense in expenses:
        paid_by = str(expense["paid_by_id"])
        if paid_by not in balances:
            balances[paid_by] = {"paid": 0, "paidFor": 0, "total": 0}
        balances[paid_by]["paid"] += int(expense["amount"])

        shares = get_expense_shares(
            expense.get("id"),
            int(expense["amount"]),
            str(expense.get("split_mode") or "EVENLY"),
            expense.get("paid_for", []),
        )
        for participant_id, divided_amount in shares.items():
            if participant_id not in balances:
                balances[participant_id] = {"paid": 0, "paidFor": 0, "total": 0}
            balances[participant_id]["paidFor"] += divided_amount

    for values in balances.values():
        values["total"] = values["paid"] - values["paidFor"]
    return balances


def _group_ids(connection: sqlite3.Connection, table: str, column: str) -> list[str]:
    rows = connection.execute(
        f'SELECT DISTINCT "{column}" FROM "{table}" ORDER BY "{column}"'
    ).fetchall()
    return [str(row[0]) for row in rows]


def _assemble(
    group_ids: list[str],
    expense_rows: list[sqlite3.Row],
    paid_for_rows: list[sqlite3.Row],
) -> dict[str, dict[str, dict[str, int]]]:
    paid_by_expense: dict[str, list[dict[str, Any]]] = {}
    for row in paid_for_rows:
        paid_by_expense.setdefault(str(row["expense_id"]), []).append(
            {
                "participant_id": str(row["participant_id"]),
                "shares": int(row["shares"]),
            }
        )

    expenses_by_group: dict[str, list[dict[str, Any]]] = {group_id: [] for group_id in group_ids}
    for row in expense_rows:
        group_id = str(row["group_id"])
        expenses_by_group.setdefault(group_id, []).append(
            {
                "id": str(row["id"]),
                "amount": int(row["amount"]),
                "split_mode": str(row["split_mode"]),
                "paid_by_id": str(row["paid_by_id"]),
                "paid_for": paid_by_expense.get(str(row["id"]), []),
            }
        )

    return {
        group_id: balances_for_group(expenses)
        for group_id, expenses in sorted(expenses_by_group.items())
    }


def source_balances(connection: sqlite3.Connection) -> dict[str, dict[str, dict[str, int]]]:
    """Compute the reference balances directly from a legacy database."""
    group_ids = [str(row[0]) for row in connection.execute('SELECT id FROM "Group"')]
    expenses = connection.execute(
        'SELECT id, "groupId" AS group_id, amount, "splitMode" AS split_mode, '
        '"paidById" AS paid_by_id FROM "Expense"'
    ).fetchall()
    paid_for = connection.execute(
        'SELECT "expenseId" AS expense_id, "participantId" AS participant_id, '
        'shares FROM "ExpensePaidFor"'
    ).fetchall()
    return _assemble(group_ids, expenses, paid_for)


def target_balances(connection: sqlite3.Connection) -> dict[str, dict[str, dict[str, int]]]:
    """Compute the same balances from the imported (new) database."""
    group_ids = [str(row[0]) for row in connection.execute("SELECT id FROM groups")]
    expenses = connection.execute(
        "SELECT id, group_id, amount, split_mode, paid_by_id FROM expenses"
    ).fetchall()
    paid_for = connection.execute(
        "SELECT expense_id, participant_id, shares FROM expense_paid_for"
    ).fetchall()
    return _assemble(group_ids, expenses, paid_for)


def json_safe_balances(
    balances: dict[str, dict[str, dict[str, int]]],
) -> dict[str, dict[str, dict[str, int]]]:
    """Keep ``orjson``/``json`` output deterministic and plain."""
    return {
        group_id: {
            participant_id: {
                "paid": int(values["paid"]),
                "paidFor": int(values["paidFor"]),
                "total": int(values["total"]),
            }
            for participant_id, values in sorted(participants.items())
        }
        for group_id, participants in sorted(balances.items())
    }


# Kept for scripts that need to normalise legacy values to JSON later.
def decimal_to_string(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
