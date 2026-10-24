"""CSV and JSON export rendering.

The CSV column order, labels, split-mode labels, participant sign convention,
formula-injection escaping and fixed decimal formatting mirror the reference
export routes.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

from app.utils.currency import format_amount_as_decimal, format_amount_for_csv
from app.utils.dates import datetime_to_date
from app.utils.shares import get_expense_shares

SPLIT_MODE_LABELS = {
    "EVENLY": "Evenly",
    "BY_SHARES": "Unevenly \u2013 By shares",
    "BY_PERCENTAGE": "Unevenly \u2013 By percentage",
    "BY_AMOUNT": "Unevenly \u2013 By amount",
}

CSV_FIELDS = [
    "Date",
    "Description",
    "Category",
    "Currency",
    "Cost",
    "Original cost",
    "Original currency",
    "Conversion rate",
    "Is Reimbursement",
    "Split mode",
]


def escape_csv_formula(value: str) -> str:
    """Neutralise spreadsheet formulas (CWE-1236)."""
    return f"'{value}" if value[:1] in {"=", "+", "-", "@", "\t", "\r"} else value


def _json_safe(value: Any) -> Any:
    if value is None:
        return ""
    return value


def build_csv(
    group: Mapping[str, Any],
    expenses: Sequence[Mapping[str, Any]],
    participants: Sequence[Mapping[str, Any]],
) -> str:
    participant_names = [str(participant["name"]) for participant in participants]
    header = CSV_FIELDS + [escape_csv_formula(name) for name in participant_names]
    currency_code = group.get("currency_code")
    currency_label = currency_code or group.get("currency", "")

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)

    for expense in expenses:
        shares = get_expense_shares(expense)
        row: list[Any] = [
            datetime_to_date(expense["expense_date"]).isoformat(),
            escape_csv_formula(str(expense.get("title", ""))),
            escape_csv_formula(str((expense.get("category") or {}).get("name") or "")),
            currency_label,
            format_amount_as_decimal(int(expense["amount"]), currency_code),
            (
                format_amount_as_decimal(
                    int(expense["original_amount"]),
                    expense.get("original_currency"),
                )
                if expense.get("original_amount")
                else ""
            ),
            _json_safe(expense.get("original_currency")),
            _json_safe(expense.get("conversion_rate")),
            "Yes" if expense.get("is_reimbursement") else "No",
            SPLIT_MODE_LABELS.get(str(expense.get("split_mode")), str(expense.get("split_mode"))),
        ]
        for participant in participants:
            participant_id = str(participant["id"])
            share = shares.get(participant_id, 0)
            amount = format_amount_for_csv(share, currency_code)
            if str(expense.get("paid_by_id")) != participant_id:
                amount = f"-{amount}" if amount != "0" else "0"
            row.append(amount)
        writer.writerow(row)

    return buffer.getvalue().rstrip("\n")


def csv_body(group: Mapping[str, Any], expenses: Sequence[Mapping[str, Any]]) -> str:
    """Return the export body including the UTF-8 BOM."""
    participants = group.get("participants", [])
    return "\ufeff" + build_csv(group, expenses, participants)


def json_body(group: Mapping[str, Any]) -> str:
    """Serialise the JSON export payload (sorted by the service)."""
    return json.dumps(group, ensure_ascii=False, separators=(",", ":"))


def csv_filename(group_name: str, today: str) -> str:
    return f"Spliit Export - {group_name} - {today}.csv"


def json_filename(today: str) -> str:
    return f"Spliit Export - {today}.json"


def content_disposition(filename: str) -> str:
    ascii_filename = "".join(
        character if 32 <= ord(character) < 127 and character not in {'"', "\\"} else "_"
        for character in filename
    )
    return f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{quote(filename)}"
