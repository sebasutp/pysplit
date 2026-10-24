"""Change-log row for the synchronization feed.

Rows are append-only and ordered by the autoincrementing ``seq``. The payload
is the canonical server snapshot of the entity after the write, so a pull can
return full snapshots (plan §2.5) without joining every table.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, Text
from sqlmodel import Field, SQLModel

from app.models.base import utc_now
from app.models.types import UTCDateTime


class SyncChange(SQLModel, table=True):
    __tablename__ = "sync_changes"
    __table_args__ = (
        Index("ix_sync_changes_group_seq", "group_id", "seq"),
        Index("ix_sync_changes_entity", "entity_type", "entity_id"),
    )

    seq: int | None = Field(default=None, primary_key=True)
    group_id: str | None = Field(default=None, nullable=True, index=True, max_length=64)
    entity_type: str = Field(nullable=False, max_length=64)
    entity_id: str = Field(nullable=False, max_length=64)
    op_type: str = Field(nullable=False, max_length=16)
    payload_json: str | None = Field(default=None, sa_type=Text, nullable=True)
    user_id: str | None = Field(default=None, nullable=True, max_length=64)
    changed_at: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
        index=True,
    )
