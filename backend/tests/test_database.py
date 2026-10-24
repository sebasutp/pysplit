"""Database helpers used by tests and local bootstrapping."""

from __future__ import annotations

import pytest
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
