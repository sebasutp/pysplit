"""Defensive receipt-extraction parsing and normalization.

Pure mirror of ``spliit/src/lib/receipt-extraction.ts``. The AI model is bound
to a JSON schema, but a self-hosted or older endpoint may ignore it, so the
response is parsed rather than trusted. Malformed output returns ``None`` and
the caller records a ``FAILED`` receipt instead of crashing.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from typing import Any

MAX_RECEIPT_ITEMS = 200

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _optional_string(container: Mapping[str, Any], key: str) -> str | None:
    value = container.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional_number(container: Mapping[str, Any], key: str) -> float | int | None:
    value = container.get(key)
    if value is None:
        return None
    if not _is_number(value):
        raise ValueError(f"{key} must be a finite number")
    return value


def _required_number(container: Mapping[str, Any], key: str) -> float | int:
    if key not in container or not _is_number(container[key]):
        raise ValueError(f"{key} must be a finite number")
    return container[key]


def _required_string(container: Mapping[str, Any], key: str) -> str:
    if key not in container or not isinstance(container[key], str):
        raise ValueError(f"{key} must be a string")
    return container[key]


def _parse_items(value: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("items must be an array")
    items: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError("items entries must be objects")
        items.append(
            {
                "name": _required_string(raw, "name"),
                "quantity": _required_number(raw, "quantity"),
                "unit_price": _optional_number(raw, "unitPrice"),
                "amount": _required_number(raw, "amount"),
            }
        )
    if limit is not None:
        items = items[:limit]
    return items


def _parse_charges(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("charges must be an array")
    charges: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError("charges entries must be objects")
        charges.append(
            {
                "name": _required_string(raw, "name"),
                "amount": _required_number(raw, "amount"),
            }
        )
    return charges


def _category_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("categoryId must be a string or number")
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return str(int(value)) if value.is_integer() else str(value)
    raise ValueError("categoryId must be a string or number")


def parse_receipt_items_response(
    content: str | None,
    *,
    limit: int = MAX_RECEIPT_ITEMS,
) -> dict[str, Any] | None:
    """Parse the raw model message, returning ``None`` for bad output.

    Only the first ``limit`` items are kept; charges are kept as-is because
    they are few and whole-bill by nature.
    """
    if content is None or not content.strip():
        return None

    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, Mapping):
        return None

    try:
        items = parsed.get("items", [])
        charges = parsed.get("charges", [])
        return {
            "merchant": _optional_string(parsed, "merchant"),
            "date": _optional_string(parsed, "date"),
            "currency_code": _optional_string(parsed, "currencyCode"),
            "total": _optional_number(parsed, "total"),
            "category_id": _category_value(parsed.get("categoryId")),
            "items": _parse_items(items, limit=max(1, limit)),
            "charges": _parse_charges(charges),
        }
    except ValueError:
        return None


def _js_round(value: float) -> int:
    """JavaScript ``Math.round`` semantics (half rounds toward +infinity)."""
    return math.floor(value + 0.5)


def _to_minor(value: float | int, decimal_digits: int) -> int:
    return _js_round(float(value) * (10**decimal_digits))


def normalize_receipt(extraction: Mapping[str, Any], decimal_digits: int) -> dict[str, Any]:
    """Convert an extraction to the stored shape (integer minor units)."""
    items: list[dict[str, Any]] = []
    position = 0

    for item in extraction.get("items", []):
        quantity = float(item["quantity"])
        quantity_milli = (
            max(1, _js_round(quantity * 1000)) if quantity > 0 and math.isfinite(quantity) else 1000
        )
        name = str(item["name"]).strip() or "Item"
        unit_price = item.get("unit_price")
        items.append(
            {
                "name": name,
                "quantity_milli": quantity_milli,
                "unit_price": None if unit_price is None else _to_minor(unit_price, decimal_digits),
                "amount": _to_minor(item["amount"], decimal_digits),
                "is_shared": False,
                "is_adjustment": False,
                "position": position,
            }
        )
        position += 1

    for charge in extraction.get("charges", []):
        name = str(charge["name"]).strip() or "Charge"
        items.append(
            {
                "name": name,
                "quantity_milli": 1000,
                "unit_price": None,
                "amount": _to_minor(charge["amount"], decimal_digits),
                "is_shared": True,
                "is_adjustment": False,
                "position": position,
            }
        )
        position += 1

    total = extraction.get("total")
    total_minor = None if total is None else _to_minor(total, decimal_digits)
    item_sum = sum(item["amount"] for item in items)

    if total_minor is not None and total_minor != item_sum:
        items.append(
            {
                "name": "Adjustment",
                "quantity_milli": 1000,
                "unit_price": None,
                "amount": total_minor - item_sum,
                "is_shared": True,
                "is_adjustment": True,
                "position": position,
            }
        )

    raw_date = extraction.get("date")
    date = raw_date if isinstance(raw_date, str) and _DATE_PATTERN.fullmatch(raw_date) else None
    merchant = extraction.get("merchant")
    merchant = merchant.strip() if isinstance(merchant, str) and merchant.strip() else None
    currency_code = extraction.get("currency_code")
    currency_code = (
        currency_code.strip().upper()
        if isinstance(currency_code, str) and currency_code.strip()
        else None
    )

    return {
        "merchant": merchant,
        "date": date,
        "currency_code": currency_code,
        "total": total_minor,
        "category_id": extraction.get("category_id"),
        "items": items,
        "items_total": total_minor if total_minor is not None else item_sum,
    }
