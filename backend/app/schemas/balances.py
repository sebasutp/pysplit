"""Balance and global-balance response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BalanceEntry(BaseModel):
    participant_id: str
    total: int
    paid: int = 0
    paid_for: int = 0


class ReimbursementRead(BaseModel):
    from_: str = Field(alias="from", serialization_alias="from")
    to: str
    amount: int

    model_config = {"populate_by_name": True}


class GroupBalances(BaseModel):
    balances: list[BalanceEntry]
    reimbursements: list[ReimbursementRead]


class UserBalanceRead(BaseModel):
    group_id: str
    group_name: str
    currency: str
    currency_code: str | None = None
    participant_id: str
    participant_name: str
    amount: int


class UserBalanceList(BaseModel):
    items: list[UserBalanceRead]
    total: int
    limit: int
    offset: int
