"""Statistics HTTP endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import SessionDep
from app.api.errors import raise_service_error
from app.schemas.stats import ExpenseDrilldown, StatsOverview
from app.services import stats as stats_service
from app.services.errors import ServiceError

router = APIRouter(prefix="/groups", tags=["stats"])


@router.get("/{group_id}/stats", response_model=StatsOverview)
def stats_overview(
    group_id: str,
    session: SessionDep,
    participant_id: Annotated[str | None, Query(max_length=64)] = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> StatsOverview:
    try:
        return stats_service.stats_overview(
            session,
            group_id,
            participant_id=participant_id,
            date_from=date_from,
            date_to=date_to,
        )
    except ServiceError as exc:
        raise_service_error(exc)


@router.get(
    "/{group_id}/stats/categories/{category_id}/expenses",
    response_model=ExpenseDrilldown,
)
def category_expenses(
    group_id: str,
    category_id: int,
    session: SessionDep,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> ExpenseDrilldown:
    try:
        return stats_service.category_expenses(
            session,
            group_id,
            category_id,
            date_from=date_from,
            date_to=date_to,
        )
    except ServiceError as exc:
        raise_service_error(exc)


@router.get(
    "/{group_id}/stats/months/{month}/expenses",
    response_model=ExpenseDrilldown,
)
def month_expenses(
    group_id: str,
    month: Annotated[str, Path(pattern=r"^\d{4}-\d{2}$")],
    session: SessionDep,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> ExpenseDrilldown:
    try:
        return stats_service.month_expenses(
            session,
            group_id,
            month,
            date_from=date_from,
            date_to=date_to,
        )
    except ServiceError as exc:
        raise_service_error(exc)
