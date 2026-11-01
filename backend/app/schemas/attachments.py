"""Unified attachment, receipt-state and AI request/response schemas."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UTCDateTime

MAX_RECEIPT_ITEMS = 200
MAX_RECEIPT_ITEM_NAME_LENGTH = 200
MAX_RECEIPT_ITEM_AMOUNT = 10_000_000_00
MAX_RECEIPT_ITEM_QUANTITY_MILLI = 1_000_000_000
MAX_RECEIPT_ITEM_PORTIONS = 100


class AttachmentPortionRead(BaseModel):
    id: str
    item_id: str
    target: Literal["PARTICIPANT", "SHARED"]
    participant_id: str | None = None
    quantity_milli: int
    version: int = 1


class AttachmentItemRead(BaseModel):
    id: str
    attachment_id: str
    name: str
    quantity_milli: int
    unit_price: int | None = None
    amount: int
    is_shared: bool
    is_adjustment: bool
    position: int
    version: int = 1
    updated_at: UTCDateTime | None = None
    deleted_at: UTCDateTime | None = None
    portions: list[AttachmentPortionRead] = Field(default_factory=list)


class AttachmentRead(BaseModel):
    id: str
    group_id: str
    expense_id: str | None = None
    url: str
    thumbnail_url: str | None = None
    filename: str
    content_type: str
    byte_size: int = 0
    width: int = 1
    height: int = 1
    receipt_status: Literal["PENDING", "EXTRACTING", "EXTRACTED", "FAILED"] | None = None
    attempts: int = 0
    merchant: str | None = None
    receipt_date: date | None = None
    currency_code: str | None = None
    total: int | None = None
    provider: str | None = None
    model: str | None = None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    version: int = 1
    deleted_at: UTCDateTime | None = None


class AttachmentSplitParticipant(BaseModel):
    participant_id: str
    direct: int
    shared: int
    unassigned: int
    total: int


class AttachmentSplitRead(BaseModel):
    participants: list[AttachmentSplitParticipant] = Field(default_factory=list)
    items_total: int
    shared_pool: int
    unassigned_pool: int
    all_opted_out: bool
    participant_totals: list[dict[str, int | str]] = Field(default_factory=list)
    unassigned: int = 0
    shared: int = 0
    adjustments: int = 0
    total: int = 0


class AttachmentState(BaseModel):
    attachment: AttachmentRead
    items: list[AttachmentItemRead] = Field(default_factory=list)
    opt_outs: list[str] = Field(default_factory=list)
    split: AttachmentSplitRead


class AttachmentExtractionResult(BaseModel):
    status: Literal["EXTRACTED", "FAILED"]
    attachment_id: str
    # Short, user-safe provider/parse reason for a FAILED result. It is
    # transient (not stored on the attachment) and never includes the prompt,
    # image data or API key.
    error: str | None = None
    total: int | None = None
    items_total: int = 0
    merchant: str | None = None
    date: str | None = None
    currency_code: str | None = None
    category_id: str | None = None
    attachment: AttachmentRead
    items: list[AttachmentItemRead] = Field(default_factory=list)
    opt_outs: list[str] = Field(default_factory=list)
    split: AttachmentSplitRead


class AttachmentTotalExtraction(BaseModel):
    amount: float | None = None
    category_id: str | None = None
    date: str | None = None
    title: str | None = None


class AttachmentExtractItemsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expense_id: str | None = Field(default=None, min_length=1, max_length=64)


class AttachmentLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expense_id: str | None = Field(default=None, min_length=1, max_length=64)


class AttachmentItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(default=None, min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=MAX_RECEIPT_ITEM_NAME_LENGTH)
    quantity_milli: int = Field(ge=1, le=MAX_RECEIPT_ITEM_QUANTITY_MILLI)
    amount: int = Field(ge=1, le=MAX_RECEIPT_ITEM_AMOUNT)
    is_shared: bool = False


class AttachmentItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=MAX_RECEIPT_ITEM_NAME_LENGTH)
    quantity_milli: int | None = Field(
        default=None,
        ge=1,
        le=MAX_RECEIPT_ITEM_QUANTITY_MILLI,
    )
    amount: int | None = Field(default=None, ge=1, le=MAX_RECEIPT_ITEM_AMOUNT)
    is_shared: bool | None = None


class AttachmentPortionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Literal["PARTICIPANT", "SHARED"]
    participant_id: str | None = Field(default=None, min_length=1, max_length=64)
    quantity_milli: int = Field(ge=0, le=MAX_RECEIPT_ITEM_QUANTITY_MILLI)


class AttachmentPortionsReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portions: list[AttachmentPortionInput] = Field(
        default_factory=list,
        max_length=MAX_RECEIPT_ITEM_PORTIONS,
    )


class AttachmentOptOutUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opted_out: bool


class AttachmentApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expense_id: str = Field(min_length=1, max_length=64)
    participant_id: str | None = Field(default=None, min_length=1, max_length=64)


class AttachmentApplyResult(BaseModel):
    attachment: AttachmentRead
    split: AttachmentSplitRead


class CategoryInferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)


class CategoryInferenceResponse(BaseModel):
    category_id: int
