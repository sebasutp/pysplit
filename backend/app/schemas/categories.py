"""Category request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class CategoryRead(BaseModel):
    id: int
    grouping: str
    name: str


class CategoryList(BaseModel):
    items: list[CategoryRead]
    total: int
    limit: int
    offset: int
