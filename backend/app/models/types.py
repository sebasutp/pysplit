"""Custom SQLAlchemy column types used by the SQLModel schema.

The legacy Prisma/SQLite database stores dates as ISO text and decimals as
text or numeric values. SQLite's built-in ``DateTime``/``Numeric`` types lose
the UTC offset and may route decimals through a float. These decorators keep
both exact: dates are always returned timezone-aware in UTC and decimals are
stored and read as canonical strings.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import DateTime, String
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Store a timezone-aware UTC datetime and read it back as aware UTC.

    SQLite has no native timezone support. The value is normalised to UTC,
    written as a naive ISO string (SQLAlchemy's SQLite date format), and the
    UTC timezone is re-attached on read. This preserves ordering, microseconds
    and the reference application's UTC-date semantics.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class DecimalString(TypeDecorator):
    """Persist a :class:`~decimal.Decimal` as an exact decimal string.

    ``Decimal('')`` never occurs; an empty legacy value is imported as
    ``None``. Using ``format(value, "f")`` avoids exponent notation so the
    stored text is stable and round-trips without float conversion.
    """

    impl = String(64)
    cache_ok = True

    def process_bind_param(self, value: Decimal | str | int | None, dialect):
        if value is None:
            return None
        if not isinstance(value, Decimal):
            try:
                value = Decimal(str(value))
            except InvalidOperation as exc:  # pragma: no cover - defensive
                raise ValueError(f"invalid decimal value: {value!r}") from exc
        return format(value, "f")

    def process_result_value(self, value: str | None, dialect):
        if value is None or value == "":
            return None
        return Decimal(value)
