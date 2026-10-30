"""Stage 12: request correlation, structured logs and optional Sentry."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core import observability
from app.core.config import Settings
from app.core.logging import JsonFormatter, RequestContextMiddleware, current_request_id


def test_request_id_is_generated_and_echoed(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32
    assert all(character in "0123456789abcdef" for character in request_id)


def test_caller_request_id_is_preserved(client: TestClient) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "request-123"})
    assert response.headers["X-Request-ID"] == "request-123"


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "bad value\r\n"})
    assert response.headers["X-Request-ID"] != "bad value"
    assert response.status_code == 200


def test_custom_request_id_header(make_client) -> None:
    client = make_client(request_id_header="X-Correlation-ID")
    response = client.get("/api/health", headers={"X-Correlation-ID": "trace-9"})
    assert response.headers["X-Correlation-ID"] == "trace-9"


def test_json_formatter_includes_request_context() -> None:
    record = logging.LogRecord(
        name="pysplit.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request.complete",
        args=(),
        exc_info=None,
    )
    record.request_id = "abc123"
    record.method = "GET"
    record.status_code = 200
    payload = json.loads(JsonFormatter().format(record))
    assert payload["request_id"] == "abc123"
    assert payload["message"] == "request.complete"
    assert payload["method"] == "GET"
    assert payload["status_code"] == 200
    assert payload["level"] == "INFO"


def test_current_request_id_default() -> None:
    assert current_request_id() == "-"


def test_request_middleware_is_registered() -> None:
    from app.main import create_app

    app = create_app(Settings(_env_file=None))
    assert any(middleware.cls is RequestContextMiddleware for middleware in app.user_middleware)


def test_sentry_is_disabled_without_a_dsn() -> None:
    assert observability.init_sentry(Settings(_env_file=None)) is False


def test_sentry_without_sdk_warns(monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    monkeypatch.setitem(__import__("sys").modules, "sentry_sdk", None)
    settings = Settings(_env_file=None, sentry_dsn="https://example.invalid/1")
    with caplog.at_level(logging.WARNING, logger="pysplit.observability"):
        assert observability.init_sentry(settings) is False
    assert "sentry-sdk is not installed" in caplog.text


def test_logging_settings_are_validated() -> None:
    from pydantic import ValidationError

    assert Settings(_env_file=None, log_level="debug").log_level == "DEBUG"
    assert Settings(_env_file=None, log_format="json").log_format == "json"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level="verbose")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, request_id_header="bad header")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, sentry_traces_sample_rate=2)
