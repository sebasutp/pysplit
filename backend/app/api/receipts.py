"""Receipt, line-item and AI HTTP endpoints (plan Stage 7)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, Response, UploadFile, status

from app.api.deps import CurrentUser, SessionDep, SettingsDep
from app.core.config import Settings
from app.core.limits import enforce_ai_rate_limit, enforce_upload_rate_limit
from app.schemas.receipts import (
    CategoryInferenceRequest,
    CategoryInferenceResponse,
    ReceiptApplyRequest,
    ReceiptApplyResult,
    ReceiptExtractionResult,
    ReceiptExtractRequest,
    ReceiptImageRead,
    ReceiptItemCreate,
    ReceiptItemUpdate,
    ReceiptLinkRequest,
    ReceiptOptOutUpdate,
    ReceiptPortionsReplace,
    ReceiptRead,
    ReceiptState,
    ReceiptTotalExtraction,
)
from app.services import groups as groups_service
from app.services import receipts as receipts_service
from app.services import uploads as uploads_service
from app.services.errors import ForbiddenError
from app.storage import get_storage

router = APIRouter(prefix="/groups", tags=["receipts"])
ai_router = APIRouter(prefix="/ai", tags=["ai"])


def _require_receipts(settings: Settings) -> None:
    if not settings.receipt_extract_enabled:
        raise ForbiddenError("Receipt extraction is not enabled.")


def _require_receipt_items(settings: Settings) -> None:
    if not settings.enable_receipt_items:
        raise ForbiddenError("Receipt items are not enabled.")


@router.post(
    "/{group_id}/receipts/upload",
    response_model=ReceiptImageRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_receipt_image(
    group_id: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    width: Annotated[int, Form(ge=1)] = 1,
    height: Annotated[int, Form(ge=1)] = 1,
) -> ReceiptImageRead:
    enforce_upload_rate_limit(request, settings)
    _require_receipts(settings)
    groups_service.get_active_group(session, group_id)

    data = await file.read(settings.max_upload_bytes + 1)
    saved = uploads_service.save_receipt_image(
        get_storage(settings),
        settings,
        group_id=group_id,
        data=data,
        content_type=file.content_type,
        width=width,
        height=height,
    )
    return ReceiptImageRead(
        url=str(saved["url"]),
        width=int(saved["width"]),
        height=int(saved["height"]),
    )


@router.get("/{group_id}/receipts/images/{image_id}")
def get_receipt_image(
    group_id: str,
    image_id: str,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    groups_service.get_active_group(session, group_id)
    data, media_type, filename = uploads_service.find_receipt_image(
        get_storage(settings),
        image_id,
        group_id=group_id,
        allow_legacy=uploads_service.receipt_image_owned_by_group(session, group_id, image_id),
    )
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post(
    "/{group_id}/receipts/extract-total",
    response_model=ReceiptTotalExtraction,
)
def extract_total(
    group_id: str,
    payload: ReceiptExtractRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    _user: CurrentUser,
) -> ReceiptTotalExtraction:
    enforce_ai_rate_limit(request, settings)
    return receipts_service.extract_total(
        session,
        settings,
        group_id=group_id,
        image_url=payload.image_url,
    )


@router.post(
    "/{group_id}/receipts/extract-items",
    response_model=ReceiptExtractionResult,
)
def extract_items(
    group_id: str,
    payload: ReceiptExtractRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    _user: CurrentUser,
) -> ReceiptExtractionResult:
    enforce_ai_rate_limit(request, settings)
    return receipts_service.extract_items(
        session,
        settings,
        group_id=group_id,
        image_url=payload.image_url,
        image_width=payload.image_width,
        image_height=payload.image_height,
        expense_id=payload.expense_id,
    )


@router.get("/{group_id}/receipts/{receipt_id}", response_model=ReceiptState)
def get_receipt(
    group_id: str,
    receipt_id: str,
    session: SessionDep,
    settings: SettingsDep,
) -> ReceiptState:
    _require_receipt_items(settings)
    return receipts_service.get_receipt_state(
        session,
        group_id,
        receipt_id=receipt_id,
    )


@router.get("/{group_id}/expenses/{expense_id}/receipt", response_model=ReceiptState)
def get_receipt_for_expense(
    group_id: str,
    expense_id: str,
    session: SessionDep,
    settings: SettingsDep,
) -> ReceiptState:
    _require_receipt_items(settings)
    return receipts_service.get_receipt_state(
        session,
        group_id,
        expense_id=expense_id,
    )


@router.post(
    "/{group_id}/receipts/{receipt_id}/items",
    response_model=ReceiptState,
    status_code=status.HTTP_201_CREATED,
)
def add_receipt_item(
    group_id: str,
    receipt_id: str,
    payload: ReceiptItemCreate,
    session: SessionDep,
    settings: SettingsDep,
) -> ReceiptState:
    _require_receipt_items(settings)
    return receipts_service.add_item(session, group_id, receipt_id, payload, settings=settings)


@router.patch(
    "/{group_id}/receipts/{receipt_id}/items/{item_id}",
    response_model=ReceiptState,
)
def update_receipt_item(
    group_id: str,
    receipt_id: str,
    item_id: str,
    payload: ReceiptItemUpdate,
    session: SessionDep,
    settings: SettingsDep,
) -> ReceiptState:
    _require_receipt_items(settings)
    return receipts_service.update_item(
        session,
        group_id,
        receipt_id,
        item_id,
        payload,
        settings=settings,
    )


@router.delete(
    "/{group_id}/receipts/{receipt_id}/items/{item_id}",
    response_model=ReceiptState,
)
def delete_receipt_item(
    group_id: str,
    receipt_id: str,
    item_id: str,
    session: SessionDep,
    settings: SettingsDep,
) -> ReceiptState:
    _require_receipt_items(settings)
    return receipts_service.delete_item(session, group_id, receipt_id, item_id)


@router.put(
    "/{group_id}/receipts/{receipt_id}/items/{item_id}/portions",
    response_model=ReceiptState,
)
def set_receipt_item_portions(
    group_id: str,
    receipt_id: str,
    item_id: str,
    payload: ReceiptPortionsReplace,
    session: SessionDep,
    settings: SettingsDep,
) -> ReceiptState:
    _require_receipt_items(settings)
    return receipts_service.set_item_portions(
        session,
        group_id,
        receipt_id,
        item_id,
        payload.portions,
        settings=settings,
    )


@router.put(
    "/{group_id}/receipts/{receipt_id}/opt-outs/{participant_id}",
    response_model=ReceiptState,
)
def set_receipt_opt_out(
    group_id: str,
    receipt_id: str,
    participant_id: str,
    payload: ReceiptOptOutUpdate,
    session: SessionDep,
    settings: SettingsDep,
) -> ReceiptState:
    _require_receipt_items(settings)
    return receipts_service.set_opt_out(
        session,
        group_id,
        receipt_id,
        participant_id,
        payload.opted_out,
    )


@router.post(
    "/{group_id}/receipts/{receipt_id}/apply",
    response_model=ReceiptApplyResult,
)
def apply_receipt(
    group_id: str,
    receipt_id: str,
    payload: ReceiptApplyRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> ReceiptApplyResult:
    _require_receipt_items(settings)
    receipt, expense, _split = receipts_service.apply_receipt_to_expense(
        session,
        group_id,
        receipt_id,
        payload.expense_id,
        participant_id=payload.participant_id,
    )
    state = receipts_service.receipt_state(session, group_id, receipt)
    return ReceiptApplyResult(
        receipt=state.receipt,
        expense=expense,
        split=state.split,
    )


@router.post(
    "/{group_id}/receipts/{receipt_id}/link",
    response_model=ReceiptRead,
)
def link_receipt(
    group_id: str,
    receipt_id: str,
    payload: ReceiptLinkRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> ReceiptRead:
    _require_receipt_items(settings)
    receipt = receipts_service.link_receipt_to_expense(
        session,
        group_id,
        receipt_id,
        payload.expense_id,
    )
    return receipts_service.receipt_state(session, group_id, receipt).receipt


@ai_router.post(
    "/categories/infer",
    response_model=CategoryInferenceResponse,
)
def infer_category(
    payload: CategoryInferenceRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    _user: CurrentUser,
) -> CategoryInferenceResponse:
    enforce_ai_rate_limit(request, settings)
    category_id = receipts_service.infer_category(
        session,
        settings,
        title=payload.title,
    )
    return CategoryInferenceResponse(category_id=category_id)
