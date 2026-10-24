"""Currency metadata and minor-unit formatting.

The reference stores amounts as integer minor units and uses a fixed currency
catalogue for decimal digits. The values below mirror the supported ISO codes in
``spliit/src/lib/currency-data.json``; custom symbols use two decimals.
"""

from __future__ import annotations

from decimal import Decimal

ZERO_DECIMAL_CURRENCIES = frozenset({"JPY", "HUF", "ISK", "IDR", "KRW", "VND", "COP"})

SUPPORTED_CURRENCY_CODES = (
    "USD",
    "EUR",
    "JPY",
    "BGN",
    "CZK",
    "DKK",
    "GBP",
    "HUF",
    "PLN",
    "RON",
    "SEK",
    "CHF",
    "ISK",
    "NOK",
    "TRY",
    "AUD",
    "BRL",
    "CAD",
    "CNY",
    "HKD",
    "IDR",
    "ILS",
    "INR",
    "KRW",
    "MKD",
    "MXN",
    "MYR",
    "NZD",
    "PHP",
    "SGD",
    "THB",
    "VND",
    "ZAR",
    "COP",
)


def decimal_digits(currency_code: str | None) -> int:
    """Return the currency's exponent; unknown/custom currencies use 2."""
    if currency_code and currency_code.upper() in ZERO_DECIMAL_CURRENCIES:
        return 0
    return 2


def currency_label(currency_code: str | None, fallback: str) -> str:
    """Return the label used in exports (ISO code when available)."""
    return currency_code or fallback


def format_amount_as_decimal(amount: int, currency_code: str | None) -> str:
    """Format minor units as a fixed-point decimal string."""
    digits = decimal_digits(currency_code)
    value = Decimal(int(amount)).scaleb(-digits)
    return f"{value:.{digits}f}"


def format_amount_for_csv(amount: int, currency_code: str | None) -> str:
    """Format an amount the way JSON2CSV renders a JavaScript number.

    The reference converts ``formatAmountAsDecimal`` to a number before writing
    it, which drops trailing zeros. ``-0`` is rendered as ``0``.
    """
    digits = decimal_digits(currency_code)
    value = Decimal(int(amount)).scaleb(-digits).quantize(Decimal(1).scaleb(-digits))
    text = f"{value:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"", "-0"}:
        return "0"
    return text
