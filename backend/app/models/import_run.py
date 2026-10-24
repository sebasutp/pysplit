"""Audit record for a legacy database import run."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Text
from sqlmodel import Field, SQLModel

from app.models.base import utc_now
from app.models.types import UTCDateTime


class ImportRun(SQLModel, table=True):
    __tablename__ = "import_runs"

    id: str = Field(primary_key=True, max_length=64)
    source_path: str = Field(nullable=False)
    source_checksum: str = Field(nullable=False, index=True, max_length=64)
    target_path: str = Field(nullable=False)
    status: str = Field(default="running", nullable=False, max_length=16)
    started_at: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
    )
    finished_at: datetime | None = Field(
        default=None,
        sa_type=UTCDateTime,
        nullable=True,
    )
    duration_ms: int | None = Field(default=None, nullable=True)
    counts_json: str = Field(default="{}", sa_type=Text, nullable=False)
    error: str | None = Field(default=None, nullable=True)
