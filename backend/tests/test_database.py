"""Database helpers used by tests and local bootstrapping."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Session

from app.core import database


def test_create_db_and_tables_is_idempotent(engine) -> None:
    database.create_db_and_tables(engine)
    database.create_db_and_tables(engine)


def test_get_session_yields_and_closes_a_session(engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(database, "engine", engine)
    generator = database.get_session()
    session = next(generator)
    assert isinstance(session, Session)
    with pytest.raises(StopIteration):
        next(generator)


def test_file_database_uses_wal_busy_timeout_and_foreign_keys(tmp_path) -> None:
    path = tmp_path / "pragmas.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() == (
            database.settings.sqlite_busy_timeout_ms
        )
        assert connection.execute(text("PRAGMA synchronous")).scalar() == 1
    engine.dispose()
