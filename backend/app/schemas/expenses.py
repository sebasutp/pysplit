"""Expense and document request/response schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from app.core.enums import RecurrenceRule, SplitMode
from app.schemas.categories import CategoryRead
from app.schemas.common import UTCDateTime

MAX_AMOUNT = 10_000_000_00


def _valid_url(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("/") and not cleaned.startswith("//"):
        return cleaned
    parsed = urlsplit(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("must be an absolute http(s) URL or a same-origin path")
    return cleaned


class DocumentInput(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=64)
    url: str = Field(min_length=1, max_length=2000)
    width: int = Field(ge=1)
    height: int = Field(ge=1)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        return _valid_url(value)


class ExpensePaidForInput(BaseModel):
    participant_id: str = Field(min_length=1, max_length=64)
    shares: Decimal | None = None
    amount: int | None = None
    percentage: Decimal | None = None

    @field_validator("shares", "percentage", mode="before")
    @classmethod
    def _decimal_comma(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.replace(",", ".")
        return value


class ExpenseCreate(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=64)
    expense_date: date
    title: str = Field(min_length=2)
    category_id: int = Field(default=0, ge=0)
    amount: int = Field(ge=-MAX_AMOUNT, le=MAX_AMOUNT)
    original_amount: int | None = Field(default=None, ge=-MAX_AMOUNT, le=MAX_AMOUNT)
    original_currency: str | None = Field(default=None, max_length=8)
    conversion_rate: Decimal | None = None
    paid_by_id: str = Field(min_length=1, max_length=64)
    is_reimbursement: bool = False
    split_mode: SplitMode = SplitMode.EVENLY
    notes: str | None = Field(default=None, max_length=20_000)
    recurrence_rule: RecurrenceRule = RecurrenceRule.NONE
    paid_for: list[ExpensePaidForInput] = Field(min_length=1)
    documents: list[DocumentInput] = Field(default_factory=list)
    participant_id: str | None = Field(
        default=None,
        max_length=64,
        validation_alias=AliasChoices("participant_id", "participantId"),
    )

    @field_validator("original_amount", mode="before")
    @classmethod
    def _empty_amount(cls, value: Any) -> Any:
        return None if value == "" else value

    @field_validator("amount", "original_amount")
    @classmethod
    def _non_zero(cls, value: int | None) -> int | None:
        if value == 0:
            raise ValueError("amountNotZero")
        return value

    @field_validator("conversion_rate", mode="before")
    @classmethod
    def _empty_rate(cls, value: Any) -> Any:
        return None if value == "" else value

    @field_validator("conversion_rate")
    @classmethod
    def _positive_rate(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value <= 0:
            raise ValueError("ratePositive")
        return value

    @field_validator("original_currency")
    @classmethod
    def _original_currency(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip().upper()
        if len(cleaned) != 3:
            raise ValueError("original_currency must contain exactly 3 characters")
        return cleaned

    @model_validator(mode="after")
    def _no_self_referential_id(self):
        if self.id is not None and not self.id.strip():
            raise ValueError("id must not be blank")
        return self


class ExpenseUpdate(BaseModel):
    expense_date: date | None = None
    title: str | None = Field(default=None, min_length=2)
    category_id: int | None = Field(default=None, ge=0)
    amount: int | None = Field(default=None, ge=-MAX_AMOUNT, le=MAX_AMOUNT)
    original_amount: int | None = Field(default=None, ge=-MAX_AMOUNT, le=MAX_AMOUNT)
    original_currency: str | None = Field(default=None, max_length=8)
    conversion_rate: Decimal | None = None
    paid_by_id: str | None = Field(default=None, min_length=1, max_length=64)
    is_reimbursement: bool | None = None
    split_mode: SplitMode | None = None
    notes: str | None = Field(default=None, max_length=20_000)
    recurrence_rule: RecurrenceRule | None = None
    paid_for: list[ExpensePaidForInput] | None = None
    documents: list[DocumentInput] | None = None
    participant_id: str | None = Field(
        default=None,
        max_length=64,
        validation_alias=AliasChoices("participant_id", "participantId"),
    )

    @field_validator("original_amount", mode="before")
    @classmethod
    def _empty_amount(cls, value: Any) -> Any:
        return None if value == "" else value

    @field_validator("amount", "original_amount")
    @classmethod
    def _non_zero(cls, value: int | None) -> int | None:
        if value == 0:
            raise ValueError("amountNotZero")
        return value

    @field_validator("conversion_rate", mode="before")
    @classmethod
    def _empty_rate(cls, value: Any) -> Any:
        return None if value == "" else value

    @field_validator("conversion_rate")
    @classmethod
    def _positive_rate(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value <= 0:
            raise ValueError("ratePositive")
        return value

    @field_validator("original_currency")
    @classmethod
    def _original_currency(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip().upper()
        if len(cleaned) != 3:
            raise ValueError("original_currency must contain exactly 3 characters")
        return cleaned


class ExpensePaidForRead(BaseModel):
    participant_id: str
    shares: int
    participant_name: str | None = None


class ExpenseDocumentRead(BaseModel):
    id: str
    url: str
    width: int
    height: int


class ReceiptSummary(BaseModel):
    id: str
    status: str


class ExpenseRead(BaseModel):
    id: str
    group_id: str
    expense_date: date
    title: str
    category_id: int
    category: CategoryRead | None = None
    amount: int
    original_amount: int | None = None
    original_currency: str | None = None
    conversion_rate: str | None = None
    paid_by_id: str
    paid_by_name: str | None = None
    is_reimbursement: bool
    split_mode: SplitMode
    notes: str | None = None
    recurrence_rule: RecurrenceRule
    created_at: UTCDateTime
    updated_at: UTCDateTime
    version: int = 1
    deleted_at: UTCDateTime | None = None
    paid_for: list[ExpensePaidForRead] = Field(default_factory=list)
    documents: list[ExpenseDocumentRead] = Field(default_factory=list)
    receipt: ReceiptSummary | None = None


class ExpenseList(BaseModel):
    items: list[ExpenseRead]
    total: int
    limit: int
    offset: int


class ExpenseDeleteOptions(BaseModel):
    participant_id: str | None = Field(
        default=None,
        max_length=64,
        validation_alias=AliasChoices("participant_id", "participantId"),
    )


def dump_payload(payload: BaseModel) -> dict[str, Any]:
    """Return explicitly-set fields without dropping explicit nulls."""
    return payload.model_dump(exclude_unset=True)
