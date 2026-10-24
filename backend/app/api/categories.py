"""Category listing endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import SessionDep
from app.schemas.categories import CategoryList
from app.services.categories import list_categories

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=CategoryList)
def get_categories(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CategoryList:
    return list_categories(session, limit=limit, offset=offset)
