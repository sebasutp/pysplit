"""OAuth account table (legacy Prisma ``Account``)."""

from __future__ import annotations

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Account(SQLModel, table=True):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_account_id",
            name="uq_accounts_provider_account",
        ),
    )

    id: str = Field(primary_key=True, max_length=64)
    user_id: str = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        index=True,
        nullable=False,
        max_length=64,
    )
    type: str = Field(nullable=False, max_length=32)
    provider: str = Field(nullable=False, max_length=32)
    provider_account_id: str = Field(nullable=False, max_length=255)
    refresh_token: str | None = Field(default=None, nullable=True)
    access_token: str | None = Field(default=None, nullable=True)
    expires_at: int | None = Field(default=None, nullable=True)
    token_type: str | None = Field(default=None, nullable=True, max_length=64)
    scope: str | None = Field(default=None, nullable=True)
    id_token: str | None = Field(default=None, nullable=True)
    session_state: str | None = Field(default=None, nullable=True)
