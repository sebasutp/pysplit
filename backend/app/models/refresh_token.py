"""Refresh-token table.

Sessions and verification tokens from the reference are intentionally not
migrated. This table is new: the SPA authenticates with a short-lived JWT and a
rotating, hashed refresh token delivered in an HttpOnly cookie.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models.base import utc_now
from app.models.types import UTCDateTime


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"

    id: str = Field(primary_key=True, max_length=64)
    user_id: str = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        index=True,
        nullable=False,
        max_length=64,
    )
    token_hash: str = Field(unique=True, index=True, nullable=False)
    expires_at: datetime = Field(sa_type=UTCDateTime, nullable=False)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
    )
    revoked_at: datetime | None = Field(
        default=None,
        sa_type=UTCDateTime,
        nullable=True,
        index=True,
    )
    # Set when a token is rotated so refresh-token reuse can be detected.
    replaced_by_id: str | None = Field(default=None, nullable=True, max_length=64)
    user_agent: str | None = Field(default=None, nullable=True)
