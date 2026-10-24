"""Group and cross-group balance endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import SessionDep
from app.api.errors import raise_service_error
from app.schemas.balances import GroupBalances, UserBalanceList
from app.services import balances as balances_service
from app.services.errors import ServiceError

group_router = APIRouter(prefix="/groups", tags=["balances"])
global_router = APIRouter(tags=["balances"])


@group_router.get("/{group_id}/balances", response_model=GroupBalances)
def group_balances(group_id: str, session: SessionDep) -> GroupBalances:
    try:
        return balances_service.get_group_balances(session, group_id)
    except ServiceError as exc:
        raise_service_error(exc)


@global_router.get("/balances", response_model=UserBalanceList)
def global_balances(
    session: SessionDep,
    groups: Annotated[list[str] | None, Query()] = None,
) -> UserBalanceList:
    tokens: list[str] = []
    for value in groups or []:
        tokens.extend(item.strip() for item in value.split(",") if item.strip())

    entries: list[tuple[str, str]] = []
    for token in tokens:
        group_id, separator, participant_id = token.rpartition(":")
        if not separator or not group_id or not participant_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="groups must use the format group_id:participant_id",
            )
        entries.append((group_id, participant_id))

    return balances_service.balances_for_user(session, entries)
