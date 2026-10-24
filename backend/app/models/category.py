"""Category table (legacy Prisma ``Category``)."""

from __future__ import annotations

from sqlmodel import Field

from app.models.base import SyncColumns


class Category(SyncColumns, table=True):
    __tablename__ = "categories"

    # Prisma ``Int @id @default(autoincrement())``. The default 44 categories
    # use fixed ids 0..43, so imported ids are always explicit.
    id: int | None = Field(default=None, primary_key=True)
    grouping: str = Field(nullable=False)
    name: str = Field(nullable=False)
