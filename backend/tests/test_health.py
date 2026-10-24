"""Health endpoint contract tests (Stage 1 gate)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_session
from app.main import create_app


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_liveness(client: TestClient) -> None:
    response = client.get("/api/health/liveness")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness(client: TestClient) -> None:
    response = client.get("/api/health/readiness")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


class _BrokenSession:
    def execute(self, *_args, **_kwargs) -> None:
        raise SQLAlchemyError("database is down")


def test_readiness_returns_503_when_database_fails() -> None:
    app = create_app()

    def override_session() -> Generator[_BrokenSession, None, None]:
        yield _BrokenSession()

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        response = client.get("/api/health/readiness")

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}


def test_cors_allows_configured_origin(client: TestClient) -> None:
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_openapi_registers_health_routes(client: TestClient) -> None:
    schema = client.get("/api/openapi.json").json()
    assert "/api/health" in schema["paths"]
    assert "/api/health/liveness" in schema["paths"]
    assert "/api/health/readiness" in schema["paths"]


@pytest.mark.parametrize("path", ["/api/health", "/api/health/liveness", "/api/health/readiness"])
def test_health_paths_do_not_require_auth(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 200
