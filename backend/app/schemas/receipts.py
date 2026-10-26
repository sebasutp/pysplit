"""Receipt, line-item, split and AI request/response schemas."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UTCDateTime
from app.schemas.expenses import ExpenseRead

MAX_RECEIPT_ITEMS = 200
MAX_RECEIPT_ITEM_NAME_LENGTH = 200
MAX_RECEIPT_ITEM_AMOUNT = 10_000_000_00
MAX_RECEIPT_ITEM_QUANTITY_MILLI = 1_000_000_000
MAX_RECEIPT_ITEM_PORTIONS = 100


class ReceiptPortionRead(BaseModel):
    id: str
    item_id: str
    target: Literal["PARTICIPANT", "SHARED"]
    participant_id: str | None = None
    quantity_milli: int
    version: int = 1


class ReceiptItemRead(BaseModel):
    id: str
    receipt_id: str
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
    portions: list[ReceiptPortionRead] = Field(default_factory=list)


class ReceiptRead(BaseModel):
    id: str
    group_id: str
    image_url: str
    image_width: int | None = None
    image_height: int | None = None
    status: Literal["PENDING", "EXTRACTING", "EXTRACTED", "FAILED"]
    attempts: int = 0
    merchant: str | None = None
    receipt_date: date | None = None
    currency_code: str | None = None
    total: int | None = None
    expense_id: str | None = None
    provider: str | None = None
    model: str | None = None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    version: int = 1
    deleted_at: UTCDateTime | None = None


class ReceiptSplitParticipant(BaseModel):
    participant_id: str
    direct: int
    shared: int
    unassigned: int
    total: int


class ReceiptSplitRead(BaseModel):
    participants: list[ReceiptSplitParticipant] = Field(default_factory=list)
    items_total: int
    shared_pool: int
    unassigned_pool: int
    all_opted_out: bool
    # Convenience shape documented in docs/api.md.
    participant_totals: list[dict[str, int | str]] = Field(default_factory=list)
    unassigned: int = 0
    shared: int = 0
    adjustments: int = 0
    total: int = 0


class ReceiptState(BaseModel):
    receipt: ReceiptRead
    items: list[ReceiptItemRead] = Field(default_factory=list)
    opt_outs: list[str] = Field(default_factory=list)
    split: ReceiptSplitRead


class ReceiptExtractionResult(BaseModel):
    status: Literal["EXTRACTED", "FAILED"]
    receipt_id: str
    total: int | None = None
    items_total: int = 0
    merchant: str | None = None
    date: str | None = None
    currency_code: str | None = None
    category_id: str | None = None
    receipt: ReceiptRead
    items: list[ReceiptItemRead] = Field(default_factory=list)
    opt_outs: list[str] = Field(default_factory=list)
    split: ReceiptSplitRead


class ReceiptTotalExtraction(BaseModel):
    amount: float | None = None
    category_id: str | None = None
    date: str | None = None
    title: str | None = None


class ReceiptImageRead(BaseModel):
    url: str
    width: int
    height: int


class ReceiptExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_url: str = Field(min_length=1, max_length=2000)
    image_width: int | None = Field(default=None, ge=1)
    image_height: int | None = Field(default=None, ge=1)
    # Optional link for offline line-item scans: the client already knows which
    # expense the queued receipt belongs to, and a later sync bootstrap would
    # otherwise overwrite the local link with the unlinked server row.
    expense_id: str | None = Field(default=None, min_length=1, max_length=64)


class ReceiptItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Optional client-generated id. Offline clients supply it so a retried
    # create is idempotent and dependent portion edits can address the item.
    id: str | None = Field(default=None, min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=MAX_RECEIPT_ITEM_NAME_LENGTH)
    quantity_milli: int = Field(ge=1, le=MAX_RECEIPT_ITEM_QUANTITY_MILLI)
    amount: int = Field(ge=1, le=MAX_RECEIPT_ITEM_AMOUNT)
    is_shared: bool = False


class ReceiptItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=MAX_RECEIPT_ITEM_NAME_LENGTH)
    quantity_milli: int | None = Field(
        default=None,
        ge=1,
        le=MAX_RECEIPT_ITEM_QUANTITY_MILLI,
    )
    amount: int | None = Field(default=None, ge=1, le=MAX_RECEIPT_ITEM_AMOUNT)
    is_shared: bool | None = None


class ReceiptPortionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Literal["PARTICIPANT", "SHARED"]
    participant_id: str | None = Field(default=None, min_length=1, max_length=64)
    quantity_milli: int = Field(ge=0, le=MAX_RECEIPT_ITEM_QUANTITY_MILLI)


class ReceiptPortionsReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portions: list[ReceiptPortionInput] = Field(
        default_factory=list,
        max_length=MAX_RECEIPT_ITEM_PORTIONS,
    )


class ReceiptOptOutUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opted_out: bool


class ReceiptApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expense_id: str = Field(min_length=1, max_length=64)
    participant_id: str | None = Field(default=None, min_length=1, max_length=64)


class ReceiptLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expense_id: str = Field(min_length=1, max_length=64)


class ReceiptApplyResult(BaseModel):
    receipt: ReceiptRead
    expense: ExpenseRead
    split: ReceiptSplitRead


class CategoryInferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)


class CategoryInferenceResponse(BaseModel):
    category_id: int
