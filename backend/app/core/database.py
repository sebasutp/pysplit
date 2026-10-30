"""Database engine and session dependency.

The engine is intentionally created at import time from the environment so
Alembic, the API process and scripts agree on the same URL. Tests never use
this engine: they build an in-memory SQLite engine with ``StaticPool``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings

settings = get_settings()


def _connect_args(url: str) -> dict[str, object]:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


engine = create_engine(settings.database_url, connect_args=_connect_args(settings.database_url))


@event.listens_for(Engine, "connect")
def _enforce_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """Enable SQLite integrity and concurrency settings on every connection.

    Prisma enforced foreign keys; SQLite disables them by default. Without this
    pragma an import could silently create orphan rows.

    WAL and relaxed synchronous mode only apply to file-backed databases. They
    are skipped for ``:memory:`` databases (the test engine), where WAL is not
    supported and every connection already sees the same ``StaticPool``.
    """
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={int(settings.sqlite_busy_timeout_ms)}")
        cursor.execute("PRAGMA database_list")
        row = cursor.fetchone()
        # (seq, name, file); ``file`` is empty for an in-memory database.
        if row is not None and row[2]:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.fetchone()
            cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def get_session() -> Generator[Session, None, None]:
    """Yield a session, closing it even when the request fails."""
    with Session(engine) as session:
        yield session


def create_db_and_tables(target_engine: Engine = engine) -> None:
    """Create tables directly from SQLModel metadata (tests and bootstrap).

    Production schema changes go through Alembic; this helper exists for
    in-memory test databases and first-run development convenience.
    """
    SQLModel.metadata.create_all(target_engine)
