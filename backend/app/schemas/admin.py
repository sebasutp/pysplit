"""Admin request and response schemas."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.core.enums import UserTier
from app.core.validation import is_valid_email


def iso_z(value: datetime) -> str:
    """Serialise a datetime as ISO-8601 UTC with a ``Z`` suffix."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class TierCounts(BaseModel):
    sync_users: int = 0
    group_creators: int = 0
    admin: int = 0


class AdminMetrics(BaseModel):
    total_groups: int
    total_expenses: int
    total_users: int
    tier_counts: TierCounts


class AdminUserRead(BaseModel):
    id: str
    name: str | None = None
    email: str | None = None
    image: str | None = None
    tier: UserTier
    created_at: datetime
    providers: list[str] = Field(default_factory=list)
    groups_count: int = 0

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return iso_z(value)


class AdminUserList(BaseModel):
    items: list[AdminUserRead]
    total: int
    limit: int
    offset: int


class PreAuthorizeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    tier: UserTier = UserTier.GROUP_CREATORS
    name: str | None = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        if not is_valid_email(value):
            raise ValueError("invalid email address")
        return value.strip().lower()


class PreAuthorizeResponse(BaseModel):
    user: AdminUserRead
    is_new: bool


class TierUpdateRequest(BaseModel):
    tier: UserTier


class TierUpdateResponse(BaseModel):
    id: str
    tier: UserTier


class AdminGroupRead(BaseModel):
    id: str
    name: str
    currency: str
    currency_code: str | None = None
    created_at: datetime
    participants_count: int = 0
    expenses_count: int = 0
    synced_users_count: int = 0

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return iso_z(value)


class AdminGroupList(BaseModel):
    items: list[AdminGroupRead]
    total: int
    limit: int
    offset: int
