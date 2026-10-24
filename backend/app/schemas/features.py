"""Runtime feature flags exposed to the SPA."""

from __future__ import annotations

from pydantic import BaseModel


class FeatureFlags(BaseModel):
    receipt_extract: bool = False
    receipt_items: bool = False
    category_extract: bool = False
    expense_documents: bool = False
