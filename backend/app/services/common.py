"""Helpers shared by service modules."""

from __future__ import annotations

from sqlmodel import Session

from app.models.group import Group
from app.services.errors import NotFoundError


def require_group(session: Session, group_id: str) -> Group:
    """Return a live group or raise the shared not-found error."""
    group = session.get(Group, group_id)
    if group is None or group.deleted_at is not None:
        raise NotFoundError("group not found")
    return group


def finish(session: Session, commit: bool) -> None:
    """Commit normally, or flush when a caller owns the transaction.

    The synchronization service applies each operation together with its
    change-log row and idempotency record in one transaction, so it passes
    ``commit=False``.
    """
    if commit:
        session.commit()
    else:
        session.flush()
