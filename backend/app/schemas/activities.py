"""Activity list schemas."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.schemas.common import UTCDateTime


class ActivityExpenseRef(BaseModel):
    id: str
    title: str
    amount: int
    expense_date: date


class ActivityRead(BaseModel):
    id: str
    group_id: str
    time: UTCDateTime
    activity_type: str
    participant_id: str | None = None
    expense_id: str | None = None
    data: str | None = None
    expense: ActivityExpenseRef | None = None


class ActivityList(BaseModel):
    items: list[ActivityRead]
    next_cursor: str | None = None
    has_more: bool = False
    total: int | None = None
    limit: int | None = None
    offset: int | None = None
