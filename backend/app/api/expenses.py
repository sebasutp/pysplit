"""Expense, recurrence, export and document HTTP endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Body,
    File,
    Form,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)

from app.api.deps import SessionDep, SettingsDep
from app.core.config import Settings
from app.core.limits import enforce_upload_rate_limit
from app.schemas.expenses import (
    ExpenseCreate,
    ExpenseDeleteOptions,
    ExpenseDocumentRead,
    ExpenseList,
    ExpenseRead,
    ExpenseUpdate,
)
from app.services import documents as documents_service
from app.services import expenses as expenses_service
from app.services import exports as exports_service
from app.services.errors import ForbiddenError
from app.storage import get_storage

router = APIRouter(prefix="/groups", tags=["expenses"])

LimitQuery = Annotated[int, Query(ge=1, le=200)]
OffsetQuery = Annotated[int, Query(ge=0)]


def _require_documents(settings: Settings) -> None:
    if not settings.enable_expense_documents:
        raise ForbiddenError("Expense documents are not enabled.")


def _export_response(file) -> Response:
    return Response(
        content=file.body,
        media_type=file.media_type,
        headers={"Content-Disposition": file.disposition},
    )


@router.get("/{group_id}/expenses", response_model=ExpenseList)
def list_expenses(
    group_id: str,
    session: SessionDep,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
    cursor: Annotated[int | None, Query(ge=0)] = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    title_filter: Annotated[str | None, Query(alias="filter", max_length=200)] = None,
) -> ExpenseList:
    return expenses_service.list_expenses(
        session,
        group_id,
        limit=limit,
        offset=offset or cursor or 0,
        date_from=date_from,
        date_to=date_to,
        query=q or title_filter,
    )


@router.get("/{group_id}/expenses/export.csv")
def export_csv(
    group_id: str,
    session: SessionDep,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> Response:
    return _export_response(
        exports_service.csv_export(
            session,
            group_id,
            date_from=date_from,
            date_to=date_to,
        )
    )


@router.get("/{group_id}/expenses/export.json")
def export_json(
    group_id: str,
    session: SessionDep,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> Response:
    return _export_response(
        exports_service.json_export(
            session,
            group_id,
            date_from=date_from,
            date_to=date_to,
        )
    )


@router.post(
    "/{group_id}/expenses",
    response_model=ExpenseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_expense(
    group_id: str,
    payload: ExpenseCreate,
    session: SessionDep,
) -> ExpenseRead:
    return expenses_service.create_expense(session, group_id, payload)


@router.get("/{group_id}/expenses/{expense_id}", response_model=ExpenseRead)
def get_expense(
    group_id: str,
    expense_id: str,
    session: SessionDep,
) -> ExpenseRead:
    return expenses_service.get_expense(session, group_id, expense_id)


@router.patch("/{group_id}/expenses/{expense_id}", response_model=ExpenseRead)
def update_expense(
    group_id: str,
    expense_id: str,
    payload: ExpenseUpdate,
    session: SessionDep,
) -> ExpenseRead:
    return expenses_service.update_expense(session, group_id, expense_id, payload)


@router.delete("/{group_id}/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    group_id: str,
    expense_id: str,
    session: SessionDep,
    participant_id: Annotated[str | None, Query(max_length=64)] = None,
    payload: Annotated[ExpenseDeleteOptions | None, Body()] = None,
) -> Response:
    body_participant = payload.participant_id if payload else None
    expenses_service.delete_expense(
        session,
        group_id,
        expense_id,
        participant_id=participant_id or body_participant,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{group_id}/expenses/{expense_id}/documents",
    response_model=ExpenseDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    group_id: str,
    expense_id: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    width: Annotated[int, Form(ge=1)] = 1,
    height: Annotated[int, Form(ge=1)] = 1,
) -> ExpenseDocumentRead:
    enforce_upload_rate_limit(request, settings)
    _require_documents(settings)
    data = await file.read(settings.max_upload_bytes + 1)
    return documents_service.save_document(
        session,
        get_storage(settings),
        group_id=group_id,
        expense_id=expense_id,
        data=data,
        content_type=file.content_type,
        max_bytes=settings.max_upload_bytes,
        allowed_types=settings.upload_allowed_type_list,
        width=width,
        height=height,
    )


@router.get("/{group_id}/expenses/{expense_id}/documents/{document_id}")
def download_document(
    group_id: str,
    expense_id: str,
    document_id: str,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    _require_documents(settings)
    _document, data, media_type, filename = documents_service.resolve_document(
        session,
        get_storage(settings),
        group_id=group_id,
        expense_id=expense_id,
        document_id=document_id,
    )
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.delete(
    "/{group_id}/expenses/{expense_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(
    group_id: str,
    expense_id: str,
    document_id: str,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    _require_documents(settings)
    documents_service.delete_document(
        session,
        get_storage(settings),
        group_id=group_id,
        expense_id=expense_id,
        document_id=document_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
