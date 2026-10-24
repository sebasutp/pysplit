"""Statistics response schemas.

The API exposes the documented snake_case names and keeps the reference names
as aliases so both the M1 UI and parity fixtures can consume the same payload.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import UTCDateTime


class StatsRange(BaseModel):
    from_: date | None = Field(default=None, alias="from", serialization_alias="from")
    to: date | None = None

    model_config = {"populate_by_name": True}


class SpendingPeriod(BaseModel):
    month: str
    total: int
    period: str | None = None
    amount: int | None = None


class ParticipantSpending(BaseModel):
    participant_id: str
    name: str
    amount: int
    paid: int
    paid_count: int
    share: int
    participantId: str | None = None
    paidCount: int | None = None


class CategorySpending(BaseModel):
    category_id: int
    grouping: str
    name: str
    amount: int
    total: int
    categoryId: int | None = None


class SpendingSummary(BaseModel):
    expense_count: int
    total_spending: int
    average_expense: int
    largest_expense: dict | None = None
    first_date: date | None = None
    last_date: date | None = None
    expenseCount: int | None = None
    totalSpending: int | None = None
    averageExpense: int | None = None
    largestExpense: dict | None = None
    firstDate: date | None = None
    lastDate: date | None = None


class RecurringPeriod(BaseModel):
    period: str
    count: int
    total: int


class RecurringStats(BaseModel):
    active_count: int = 0
    monthly_amount: int = 0
    yearly_amount: int = 0
    count: int = 0
    estimated_monthly: int = 0
    estimated_yearly: int = 0
    by_period: list[RecurringPeriod] = Field(default_factory=list)
    estimatedMonthly: int | None = None
    estimatedYearly: int | None = None
    byPeriod: list[RecurringPeriod] = Field(default_factory=list)


class StatsOverview(BaseModel):
    range: StatsRange
    total_group_spending: int
    total_active_user_share: int | None = None
    total_active_user_paid_for: int | None = None
    summary: SpendingSummary
    spending_over_time: list[SpendingPeriod]
    spending_by_participant: list[ParticipantSpending]
    spending_by_category: list[CategorySpending]
    recurring: RecurringStats

    # Reference-name aliases retained for parity.
    totalGroupSpendings: int | None = None
    totalParticipantSpendings: int | None = None
    totalParticipantShare: int | None = None
    months: list[SpendingPeriod] = Field(default_factory=list)
    participants: list[ParticipantSpending] = Field(default_factory=list)
    categories: list[CategorySpending] = Field(default_factory=list)


class DrilldownExpense(BaseModel):
    id: str
    title: str
    amount: int
    expense_date: date
    created_at: UTCDateTime | None = None


class ExpenseDrilldown(BaseModel):
    expenses: list[DrilldownExpense]
