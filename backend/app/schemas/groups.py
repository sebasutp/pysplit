"""Group, participant and membership request/response schemas."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from app.schemas.common import UTCDateTime


def _clean_currency_code(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) != 3:
        raise ValueError("currency_code must contain exactly 3 characters")
    return cleaned.upper()


class ParticipantInput(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=64)
    name: str = Field(min_length=2, max_length=50)


class ParticipantCreate(ParticipantInput):
    pass


class ParticipantUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=50)


class _NamedParticipants(BaseModel):
    participants: list[ParticipantInput] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_names(self):
        seen: set[str] = set()
        for participant in self.participants:
            if participant.name in seen:
                raise ValueError("duplicateParticipantName")
            seen.add(participant.name)
        return self


class GroupCreate(_NamedParticipants):
    id: str | None = Field(default=None, min_length=1, max_length=64)
    name: str = Field(min_length=2, max_length=50)
    information: str | None = Field(default=None, max_length=10_000)
    currency: str = Field(default="$", min_length=1, max_length=5)
    currency_code: str | None = Field(
        default=None,
        validation_alias=AliasChoices("currency_code", "currencyCode"),
    )

    @field_validator("currency_code")
    @classmethod
    def _currency_code(cls, value: str | None) -> str | None:
        return _clean_currency_code(value)


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=50)
    information: str | None = Field(default=None, max_length=10_000)
    currency: str | None = Field(default=None, min_length=1, max_length=5)
    currency_code: str | None = Field(
        default=None,
        validation_alias=AliasChoices("currency_code", "currencyCode"),
    )
    participants: list[ParticipantInput] | None = Field(default=None, min_length=1)
    participant_id: str | None = Field(
        default=None,
        max_length=64,
        validation_alias=AliasChoices("participant_id", "participantId"),
    )

    @field_validator("currency_code")
    @classmethod
    def _currency_code(cls, value: str | None) -> str | None:
        return _clean_currency_code(value)

    @model_validator(mode="after")
    def _unique_names(self):
        if self.participants is None:
            return self
        seen: set[str] = set()
        for participant in self.participants:
            if participant.name in seen:
                raise ValueError("duplicateParticipantName")
            seen.add(participant.name)
        return self


class ParticipantRead(BaseModel):
    id: str
    name: str
    group_id: str
    updated_at: UTCDateTime
    version: int = 1
    deleted_at: UTCDateTime | None = None


class UserGroupRead(BaseModel):
    user_id: str
    group_id: str
    is_starred: bool
    is_archived: bool
    created_at: UTCDateTime
    updated_at: UTCDateTime | None = None
    version: int = 1


class GroupRead(BaseModel):
    id: str
    name: str
    information: str | None = None
    currency: str
    currency_code: str | None = None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    version: int = 1
    deleted_at: UTCDateTime | None = None
    participants: list[ParticipantRead] = Field(default_factory=list)
    participants_count: int | None = None
    user_group: UserGroupRead | None = None
    # Present on /groups/sync rows for compatibility with the reference shape.
    is_starred: bool | None = None
    is_archived: bool | None = None
    isStarred: bool | None = None
    isArchived: bool | None = None


class GroupList(BaseModel):
    items: list[GroupRead]
    total: int
    limit: int
    offset: int


class GroupDetails(BaseModel):
    group: GroupRead
    participants_with_expenses: list[str] = Field(default_factory=list)
    participants_with_expense_details: list[ParticipantRead] = Field(default_factory=list)
    participantsWithExpenses: list[str] = Field(default_factory=list)


class MembershipUpdate(BaseModel):
    is_starred: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("is_starred", "isStarred"),
    )
    is_archived: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("is_archived", "isArchived"),
    )

    @model_validator(mode="after")
    def _one_field(self):
        if self.is_starred is None and self.is_archived is None:
            raise ValueError("at least one of is_starred or is_archived is required")
        return self


class GroupSyncRequest(BaseModel):
    group_ids: list[str] = Field(default_factory=list, max_length=500)
    local_group_ids: list[str] = Field(
        default_factory=list,
        max_length=500,
        validation_alias=AliasChoices("local_group_ids", "localGroupIds"),
    )
    starred_group_ids: list[str] = Field(
        default_factory=list,
        max_length=500,
        validation_alias=AliasChoices("starred_group_ids", "starredGroupIds"),
    )
    archived_group_ids: list[str] = Field(
        default_factory=list,
        max_length=500,
        validation_alias=AliasChoices("archived_group_ids", "archivedGroupIds"),
    )


class GroupSyncResponse(BaseModel):
    is_authenticated: bool
    groups: list[GroupRead]
    user_groups: list[UserGroupRead] = Field(default_factory=list)
    isAuthenticated: bool | None = None
