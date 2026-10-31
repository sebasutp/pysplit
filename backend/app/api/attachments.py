"""Unified attachment, receipt-item and AI HTTP endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, File, Form, Request, Response, UploadFile, status

from app.api.deps import CurrentUser, SessionDep, SettingsDep
from app.core.limits import enforce_ai_rate_limit, enforce_upload_rate_limit
from app.schemas.attachments import (
    AttachmentApplyRequest,
    AttachmentApplyResult,
    AttachmentExtractionResult,
    AttachmentExtractItemsRequest,
    AttachmentItemCreate,
    AttachmentItemUpdate,
    AttachmentLinkRequest,
    AttachmentOptOutUpdate,
    AttachmentPortionsReplace,
    AttachmentRead,
    AttachmentState,
    AttachmentTotalExtraction,
    CategoryInferenceRequest,
    CategoryInferenceResponse,
)
from app.services import attachments as attachments_service
from app.services import groups as groups_service
from app.storage import get_storage

router = APIRouter(prefix="/groups", tags=["attachments"])
ai_router = APIRouter(prefix="/ai", tags=["ai"])


def _require_receipt_ai(settings) -> None:
    attachments_service._require_receipt_ai(settings)


@router.post(
    "/{group_id}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    group_id: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    expense_id: Annotated[str | None, Form(max_length=64)] = None,
    width: Annotated[int, Form(ge=1)] = 1,
    height: Annotated[int, Form(ge=1)] = 1,
) -> AttachmentRead:
    enforce_upload_rate_limit(request, settings)
    groups_service.get_active_group(session, group_id)
    data = await file.read(settings.max_upload_bytes + 1)
    return attachments_service.save_attachment(
        session,
        get_storage(settings),
        settings,
        group_id=group_id,
        data=data,
        content_type=file.content_type,
        filename=file.filename,
        expense_id=expense_id,
        width=width,
        height=height,
    )


@router.get("/{group_id}/attachments/{attachment_id}", response_model=AttachmentRead)
def get_attachment(
    group_id: str,
    attachment_id: str,
    session: SessionDep,
) -> AttachmentRead:
    attachment = attachments_service.get_attachment(session, group_id, attachment_id)
    return attachments_service._attachment_read(attachment)


@router.get("/{group_id}/attachments/{attachment_id}/file")
def get_attachment_file(
    group_id: str,
    attachment_id: str,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    _attachment, data, media_type, filename = attachments_service.resolve_attachment_file(
        session,
        get_storage(settings),
        group_id=group_id,
        attachment_id=attachment_id,
    )
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/{group_id}/attachments/{attachment_id}/thumbnail")
def get_attachment_thumbnail(
    group_id: str,
    attachment_id: str,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    _attachment, data, media_type, filename = attachments_service.resolve_attachment_file(
        session,
        get_storage(settings),
        group_id=group_id,
        attachment_id=attachment_id,
    )
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.patch("/{group_id}/attachments/{attachment_id}", response_model=AttachmentRead)
def update_attachment(
    group_id: str,
    attachment_id: str,
    payload: AttachmentLinkRequest,
    session: SessionDep,
) -> AttachmentRead:
    attachment = attachments_service.link_attachment_to_expense(
        session,
        group_id,
        attachment_id,
        payload.expense_id,
    )
    return attachments_service._attachment_read(attachment)


@router.delete(
    "/{group_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_attachment(
    group_id: str,
    attachment_id: str,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    attachments_service.delete_attachment(
        session,
        get_storage(settings),
        group_id=group_id,
        attachment_id=attachment_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{group_id}/attachments/{attachment_id}/extract-total",
    response_model=AttachmentTotalExtraction,
)
def extract_total(
    group_id: str,
    attachment_id: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    _user: CurrentUser,
) -> AttachmentTotalExtraction:
    enforce_ai_rate_limit(request, settings)
    _require_receipt_ai(settings)
    return attachments_service.extract_total(
        session,
        settings,
        group_id=group_id,
        attachment_id=attachment_id,
    )


@router.post(
    "/{group_id}/attachments/{attachment_id}/extract-items",
    response_model=AttachmentExtractionResult,
)
def extract_items(
    group_id: str,
    attachment_id: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    _user: CurrentUser,
    payload: Annotated[AttachmentExtractItemsRequest | None, Body()] = None,
) -> AttachmentExtractionResult:
    enforce_ai_rate_limit(request, settings)
    _require_receipt_ai(settings)
    return attachments_service.extract_items(
        session,
        settings,
        group_id=group_id,
        attachment_id=attachment_id,
        expense_id=payload.expense_id if payload else None,
    )


@router.get(
    "/{group_id}/attachments/{attachment_id}/receipt",
    response_model=AttachmentState,
)
def get_attachment_receipt(
    group_id: str,
    attachment_id: str,
    session: SessionDep,
    settings: SettingsDep,
) -> AttachmentState:
    _require_receipt_ai(settings)
    return attachments_service.get_attachment_state(
        session,
        group_id,
        attachment_id=attachment_id,
    )


@router.post(
    "/{group_id}/attachments/{attachment_id}/items",
    response_model=AttachmentState,
    status_code=status.HTTP_201_CREATED,
)
def add_attachment_item(
    group_id: str,
    attachment_id: str,
    payload: AttachmentItemCreate,
    session: SessionDep,
    settings: SettingsDep,
) -> AttachmentState:
    _require_receipt_ai(settings)
    return attachments_service.add_item(
        session, group_id, attachment_id, payload, settings=settings
    )


@router.patch(
    "/{group_id}/attachments/{attachment_id}/items/{item_id}",
    response_model=AttachmentState,
)
def update_attachment_item(
    group_id: str,
    attachment_id: str,
    item_id: str,
    payload: AttachmentItemUpdate,
    session: SessionDep,
    settings: SettingsDep,
) -> AttachmentState:
    _require_receipt_ai(settings)
    return attachments_service.update_item(
        session,
        group_id,
        attachment_id,
        item_id,
        payload,
        settings=settings,
    )


@router.delete(
    "/{group_id}/attachments/{attachment_id}/items/{item_id}",
    response_model=AttachmentState,
)
def delete_attachment_item(
    group_id: str,
    attachment_id: str,
    item_id: str,
    session: SessionDep,
    settings: SettingsDep,
) -> AttachmentState:
    _require_receipt_ai(settings)
    return attachments_service.delete_item(session, group_id, attachment_id, item_id)


@router.put(
    "/{group_id}/attachments/{attachment_id}/items/{item_id}/portions",
    response_model=AttachmentState,
)
def set_attachment_item_portions(
    group_id: str,
    attachment_id: str,
    item_id: str,
    payload: AttachmentPortionsReplace,
    session: SessionDep,
    settings: SettingsDep,
) -> AttachmentState:
    _require_receipt_ai(settings)
    return attachments_service.set_item_portions(
        session,
        group_id,
        attachment_id,
        item_id,
        payload.portions,
        settings=settings,
    )


@router.put(
    "/{group_id}/attachments/{attachment_id}/opt-outs/{participant_id}",
    response_model=AttachmentState,
)
def set_attachment_opt_out(
    group_id: str,
    attachment_id: str,
    participant_id: str,
    payload: AttachmentOptOutUpdate,
    session: SessionDep,
    settings: SettingsDep,
) -> AttachmentState:
    _require_receipt_ai(settings)
    return attachments_service.set_opt_out(
        session,
        group_id,
        attachment_id,
        participant_id,
        payload.opted_out,
    )


@router.post(
    "/{group_id}/attachments/{attachment_id}/apply",
    response_model=AttachmentApplyResult,
)
def apply_attachment(
    group_id: str,
    attachment_id: str,
    payload: AttachmentApplyRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> AttachmentApplyResult:
    _require_receipt_ai(settings)
    attachment, _split = attachments_service.apply_attachment_to_expense(
        session,
        group_id,
        attachment_id,
        payload.expense_id,
        participant_id=payload.participant_id,
    )
    state = attachments_service.attachment_state(session, group_id, attachment)
    return AttachmentApplyResult(attachment=state.attachment, split=state.split)


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
    category_id = attachments_service.infer_category(
        session,
        settings,
        title=payload.title,
    )
    return CategoryInferenceResponse(category_id=category_id)
