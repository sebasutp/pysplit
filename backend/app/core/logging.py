"""Structured logging and request correlation.

The deployment runs a single Uvicorn worker per container, so a process-local
context variable is enough to attach the request id to every log line emitted
while handling a request. Container log collectors can parse ``LOG_FORMAT=json``
without a sidecar.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import Settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Only accept a caller-provided id that is safe to echo in a header and log.
_MAX_REQUEST_ID_LENGTH = 128
_ALLOWED_REQUEST_ID = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")

_LOG_EXTRA_FIELDS = (
    "event",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "client",
)


def current_request_id() -> str:
    """Return the active request id (``-`` outside a request)."""
    return request_id_var.get()


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = current_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per log line with stable, queryable fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", current_request_id()),
        }
        for field in _LOG_EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class TextFormatter(logging.Formatter):
    """Human-readable format that still carries the request id."""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "request_id"):
            record.request_id = current_request_id()
        return super().format(record)


_configured_signature: tuple[str, str] | None = None


def configure_logging(settings: Settings) -> None:
    """Install the process log handler once per (level, format) pair.

    Existing handlers (pytest, an embedding application) are preserved; the
    application handler is marked so repeated ``create_app`` calls do not
    duplicate lines. Tests may reconfigure with a different level/format.
    """
    global _configured_signature
    signature = (settings.log_level, settings.log_format)
    if _configured_signature == signature:
        return

    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_pysplit_handler", False):
            root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler._pysplit_handler = True  # type: ignore[attr-defined]
    handler.addFilter(_RequestIdFilter())
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            TextFormatter(
                "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )

    root.addHandler(handler)
    level = getattr(logging, settings.log_level, logging.INFO)
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)
    _configured_signature = signature


def _clean_request_id(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > _MAX_REQUEST_ID_LENGTH:
        return None
    if any(character not in _ALLOWED_REQUEST_ID for character in candidate):
        return None
    return candidate


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Correlate a request and emit one structured completion line.

    A trusted proxy may provide ``X-Request-ID``; otherwise a random id is
    generated. The value is always returned to the client so a browser error
    can be matched to server logs.
    """

    def __init__(self, app, *, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings
        self.logger = logging.getLogger("pysplit.request")

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = _clean_request_id(request.headers.get(self.settings.request_id_header))
        request_id = request_id or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        client = request.client.host if request.client else None
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            self.logger.exception(
                "request.failed",
                extra={
                    "event": "request.failed",
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                    "client": client,
                },
            )
            request_id_var.reset(token)
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers[self.settings.request_id_header] = request_id
        self.logger.info(
            "request.complete",
            extra={
                "event": "request.complete",
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client": client,
            },
        )
        request_id_var.reset(token)
        return response
