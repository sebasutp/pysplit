"""Readiness checks."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session


def database_is_ready(session: Session) -> bool:
    """Return whether a trivial query can reach the database."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True
