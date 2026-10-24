"""Shared pytest fixtures.

Every test gets a fresh in-memory SQLite database. ``StaticPool`` keeps the
same connection alive for the whole test, which is required because an
in-memory database disappears when the last connection closes.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.limits import auth_rate_limiter
from app.main import create_app


@event.listens_for(Engine, "connect")
def _sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Every test connection enforces foreign keys, as production does."""
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


@pytest.fixture()
def engine():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)
    yield test_engine
    SQLModel.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture()
def session(engine) -> Generator[Session, None, None]:
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture()
def client(engine) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as db_session:
            yield db_session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def make_client(engine):
    """Build a client with optional settings overrides for one test."""
    clients: list[TestClient] = []

    def factory(**settings_overrides):
        app = create_app()

        def override_session() -> Generator[Session, None, None]:
            with Session(engine) as db_session:
                yield db_session

        app.dependency_overrides[get_session] = override_session
        if settings_overrides:
            app.dependency_overrides[get_settings] = lambda: Settings(
                _env_file=None, **settings_overrides
            )
        test_client = TestClient(app)
        test_client.__enter__()
        clients.append(test_client)
        return test_client

    yield factory

    for test_client in clients:
        test_client.__exit__(None, None, None)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Keep in-process rate-limit windows from leaking between tests."""
    auth_rate_limiter.reset()
    yield
    auth_rate_limiter.reset()
