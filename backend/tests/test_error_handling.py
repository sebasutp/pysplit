"""The application maps every service error to its documented HTTP status."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.errors import (
    ConflictError,
    ForbiddenError,
    InvalidInputError,
    NotFoundError,
    PayloadTooLargeError,
    ServiceError,
)


@pytest.fixture()
def error_client() -> TestClient:
    app = create_app()

    @app.get("/_test/service-errors/{kind}")
    def _raise_service_error(kind: str) -> None:
        errors: dict[str, ServiceError] = {
            "not_found": NotFoundError("group not found"),
            "forbidden": ForbiddenError("not allowed"),
            "conflict": ConflictError("already exists"),
            "too_large": PayloadTooLargeError("too big"),
            "invalid_input": InvalidInputError("bad value", field="value"),
            "plain": ServiceError("unexpected"),
        }
        raise errors[kind]

    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    ("kind", "status_code", "detail"),
    [
        ("not_found", 404, "group not found"),
        ("forbidden", 403, "not allowed"),
        ("conflict", 409, "already exists"),
        ("too_large", 413, "too big"),
        ("invalid_input", 422, "bad value"),
        ("plain", 400, "unexpected"),
    ],
)
def test_service_error_maps_to_http_response(
    error_client: TestClient,
    kind: str,
    status_code: int,
    detail: str,
) -> None:
    response = error_client.get(f"/_test/service-errors/{kind}")

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
