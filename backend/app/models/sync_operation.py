"""Idempotency record for pushed synchronization operations.

A replayed ``op_id`` returns the stored result instead of applying the write
again. Rows are retained for seven days (plan §2.5).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Text
from sqlmodel import Field, SQLModel

from app.models.base import utc_now
from app.models.types import UTCDateTime


class SyncOperation(SQLModel, table=True):
    __tablename__ = "sync_operations"

    op_id: str = Field(primary_key=True, max_length=64)
    user_id: str | None = Field(default=None, nullable=True, index=True, max_length=64)
    applied_at: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
    )
    expires_at: datetime = Field(
        sa_type=UTCDateTime,
        nullable=False,
        index=True,
    )
    result_json: str = Field(sa_type=Text, nullable=False)
