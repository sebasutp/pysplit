"""Runtime feature flags endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SettingsDep
from app.schemas.features import FeatureFlags

router = APIRouter(prefix="/features", tags=["features"])


@router.get("", response_model=FeatureFlags)
def get_features(settings: SettingsDep) -> FeatureFlags:
    return FeatureFlags(
        receipt_ai=settings.receipt_ai_enabled,
        category_ai=settings.enable_category_extract,
    )
