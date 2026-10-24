"""Participant table (legacy Prisma ``Participant``)."""

from __future__ import annotations

from sqlmodel import Field

from app.models.base import SyncColumns


class Participant(SyncColumns, table=True):
    __tablename__ = "participants"

    id: str = Field(primary_key=True, max_length=64)
    name: str = Field(nullable=False)
    group_id: str = Field(
        foreign_key="groups.id",
        ondelete="CASCADE",
        index=True,
        nullable=False,
        max_length=64,
    )
