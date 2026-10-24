"""Recurrence date arithmetic.

Mirrors ``calculateNextDate`` in ``spliit/src/lib/api.ts``. Monthly recurrence
clamps to the last valid day of the next month and then keeps that day for later
frames (Jan 31 → Feb 28 → Mar 28), matching the reference's documented
limitation.
"""

from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta

RECURRENCE_RULES = ("NONE", "DAILY", "WEEKLY", "MONTHLY")


def calculate_next_date(rule: str | None, prior: datetime) -> datetime:
    """Return the next occurrence, preserving time-of-day and timezone."""
    normalized = (rule or "NONE").upper()
    if prior.tzinfo is None:
        prior = prior.replace(tzinfo=UTC)

    if normalized == "DAILY":
        return prior + timedelta(days=1)
    if normalized == "WEEKLY":
        return prior + timedelta(days=7)
    if normalized != "MONTHLY":
        return prior

    next_month = prior.month + 1
    next_year = prior.year
    if next_month > 12:
        next_month = 1
        next_year += 1

    day = prior.day
    while day > calendar.monthrange(next_year, next_month)[1]:
        day -= 1

    return prior.replace(year=next_year, month=next_month, day=day)
