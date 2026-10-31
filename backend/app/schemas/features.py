"""Runtime feature flags exposed to the SPA."""

from __future__ import annotations

from pydantic import BaseModel


class FeatureFlags(BaseModel):
    receipt_ai: bool = False
    category_ai: bool = False
