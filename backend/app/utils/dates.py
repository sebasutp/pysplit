"""Date boundary helpers for expense dates.

``expense_date`` is stored as a full UTC timestamp but treated as a UTC date at
the API boundary and by statistics. These helpers keep that conversion in one
place.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta


def as_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def date_to_datetime(value: date) -> datetime:
    """Return UTC midnight for a date-only input."""
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def datetime_to_date(value: datetime) -> date:
    """Return the UTC calendar date of an expense timestamp."""
    return as_utc_datetime(value).date()


def date_string(value: datetime | date) -> str:
    if isinstance(value, datetime):
        return datetime_to_date(value).isoformat()
    return value.isoformat()


def start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def end_of_day_exclusive(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC) + timedelta(days=1)
