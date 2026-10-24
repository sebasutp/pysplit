"""Runtime feature flags endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SettingsDep
from app.schemas.features import FeatureFlags

router = APIRouter(prefix="/features", tags=["features"])


@router.get("", response_model=FeatureFlags)
def get_features(settings: SettingsDep) -> FeatureFlags:
    return FeatureFlags(
        receipt_extract=settings.receipt_extract_enabled,
        receipt_items=settings.enable_receipt_items,
        category_extract=settings.enable_category_extract,
        expense_documents=settings.enable_expense_documents,
    )
