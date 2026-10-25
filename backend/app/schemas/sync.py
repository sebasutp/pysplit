"""Synchronization protocol request and response schemas.

The wire format is described in ``docs/adr/0002-offline-sync.md``. Payload
fields are intentionally typed as mappings here: the sync service validates
them against explicit per-entity field whitelists before constructing the
domain request models, so an unknown field produces a per-operation ``error``
result rather than a request-wide 422.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.activities import ActivityRead
from app.schemas.categories import CategoryRead
from app.schemas.expenses import ExpenseRead
from app.schemas.groups import GroupRead, ParticipantRead

SyncEntityType = str
SyncOpType = Literal["create", "update", "delete"]


class SyncOperationIn(BaseModel):
    """One offline mutation in the push envelope."""

    model_config = ConfigDict(extra="forbid")

    op_id: str = Field(min_length=1, max_length=64)
    group_id: str = Field(min_length=1, max_length=64)
    entity_type: SyncEntityType = Field(min_length=1, max_length=64)
    entity_id: str = Field(min_length=1, max_length=64)
    op_type: SyncOpType
    base_version: int | None = Field(default=None, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)
    client_time: datetime | None = None


class SyncPushRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations: list[SyncOperationIn] = Field(min_length=1, max_length=50)


class SyncPushResult(BaseModel):
    op_id: str
    status: Literal["applied", "conflict", "error"]
    entity: dict[str, Any] | None = None
    version: int | None = None
    seq: int | None = None
    server_entity: dict[str, Any] | None = None
    code: str | None = None
    detail: str | None = None
    duplicate: bool | None = None


class SyncPushResponse(BaseModel):
    results: list[SyncPushResult]
    cursor: int


class SyncPullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cursor: int = Field(default=0, ge=0)
    group_ids: list[str] = Field(default_factory=list, max_length=500)
    limit: int = Field(default=500, ge=1, le=500)


class SyncChangeRead(BaseModel):
    seq: int
    entity_type: str
    entity_id: str
    op_type: str
    snapshot: dict[str, Any] | None = None


class SyncPullResponse(BaseModel):
    changes: list[SyncChangeRead]
    cursor: int
    has_more: bool


class SyncReceiptSnapshot(BaseModel):
    receipt: dict[str, Any]
    items: list[dict[str, Any]] = Field(default_factory=list)
    portions: list[dict[str, Any]] = Field(default_factory=list)
    opt_outs: list[dict[str, Any]] = Field(default_factory=list)


class SyncBootstrapResponse(BaseModel):
    cursor: int
    group: GroupRead
    participants: list[ParticipantRead] = Field(default_factory=list)
    expenses: list[ExpenseRead] = Field(default_factory=list)
    activities: list[ActivityRead] = Field(default_factory=list)
    receipts: list[SyncReceiptSnapshot] = Field(default_factory=list)
    categories: list[CategoryRead] = Field(default_factory=list)
    user_group: dict[str, Any] | None = None
