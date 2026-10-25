"""Expense document upload, retrieval and deletion."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from sqlmodel import Session

from app.core.ids import new_id
from app.models.expense import Expense
from app.models.expense_document import ExpenseDocument
from app.models.group import Group
from app.schemas.expenses import ExpenseDocumentRead
from app.services.errors import InvalidInputError, NotFoundError, PayloadTooLargeError
from app.storage import BlobStorage, StorageError

CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
EXTENSION_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _upload_url(group_id: str, expense_id: str, document_id: str) -> str:
    return f"/api/groups/{group_id}/expenses/{expense_id}/documents/{document_id}"


def _active_expense(session: Session, group_id: str, expense_id: str) -> Expense:
    group = session.get(Group, group_id)
    if group is None or group.deleted_at is not None:
        raise NotFoundError("group not found")
    expense = session.get(Expense, expense_id)
    if expense is None or expense.group_id != group_id or expense.deleted_at is not None:
        raise NotFoundError("expense not found")
    return expense


def storage_key(document_id: str, content_type: str) -> str:
    extension = CONTENT_TYPE_EXTENSIONS.get(content_type.lower())
    if extension is None:
        raise InvalidInputError("unsupported document type", field="file")
    return f"documents/{document_id}{extension}"


def save_document(
    session: Session,
    storage: BlobStorage,
    *,
    group_id: str,
    expense_id: str,
    data: bytes,
    content_type: str | None,
    max_bytes: int,
    allowed_types: list[str],
    width: int = 1,
    height: int = 1,
    now: datetime | None = None,
) -> ExpenseDocumentRead:
    _active_expense(session, group_id, expense_id)
    if len(data) > max_bytes:
        raise PayloadTooLargeError(f"file exceeds the {max_bytes} byte limit")
    if not data:
        raise InvalidInputError("uploaded file is empty", field="file")

    normalized_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_type not in {item.lower() for item in allowed_types}:
        raise InvalidInputError("unsupported document type", field="file")

    document_id = new_id("doc")
    key = storage_key(document_id, normalized_type)
    storage.save(key, data, content_type=normalized_type)

    moment = now or datetime.now(UTC)
    document = ExpenseDocument(
        id=document_id,
        url=storage.public_url(key) or _upload_url(group_id, expense_id, document_id),
        width=max(1, int(width)),
        height=max(1, int(height)),
        expense_id=expense_id,
        created_at=moment,
        updated_at=moment,
        version=1,
    )
    try:
        session.add(document)
        session.commit()
        session.refresh(document)
    except Exception:
        session.rollback()
        storage.delete(key)
        raise

    return ExpenseDocumentRead(
        id=document.id,
        url=document.url,
        width=document.width,
        height=document.height,
    )


def resolve_document(
    session: Session,
    storage: BlobStorage,
    *,
    group_id: str,
    expense_id: str,
    document_id: str,
) -> tuple[ExpenseDocument, bytes, str, str]:
    _active_expense(session, group_id, expense_id)
    document = session.get(ExpenseDocument, document_id)
    if document is None or document.expense_id != expense_id:
        raise NotFoundError("document not found")

    for extension, media_type in EXTENSION_CONTENT_TYPES.items():
        key = f"documents/{document_id}{extension}"
        try:
            if storage.exists(key):
                return document, storage.read(key), media_type, f"{document_id}{extension}"
        except StorageError:
            continue
    raise NotFoundError("document file not found")


def delete_document(
    session: Session,
    storage: BlobStorage,
    *,
    group_id: str,
    expense_id: str,
    document_id: str,
) -> None:
    _active_expense(session, group_id, expense_id)
    document = session.get(ExpenseDocument, document_id)
    if document is None or document.expense_id != expense_id:
        raise NotFoundError("document not found")

    session.delete(document)
    session.commit()
    for extension in EXTENSION_CONTENT_TYPES:
        with contextlib.suppress(StorageError):
            storage.delete(f"documents/{document_id}{extension}")
