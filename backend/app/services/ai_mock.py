"""Deterministic AI fixtures used only when ``AI_MOCK`` is enabled."""

from __future__ import annotations

import copy
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.ai import AiError

FIXTURE_PATH = Path(__file__).with_name("ai_mock_responses.json")
_REQUIRED_RESPONSES = {
    "receipt_response",
    "receipt_items_response",
    "category_response",
}


def load_fixtures() -> dict[str, Any]:
    try:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # pragma: no cover - packaging failure
        raise RuntimeError(f"Could not load AI mock fixtures: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("AI mock fixtures must be a JSON object")
    missing = _REQUIRED_RESPONSES - payload.keys()
    if missing:
        raise RuntimeError(f"AI mock fixtures missing: {', '.join(sorted(missing))}")
    return payload


_FIXTURES = load_fixtures()


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _resolve_tokens(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("{{today}}", _today())
    if isinstance(value, list):
        return [_resolve_tokens(item) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_tokens(item) for key, item in value.items()}
    return value


class MockChatCompletionClient:
    """Return canned JSON without touching the network."""

    def __init__(self, *, delay_ms: int = 0) -> None:
        self.delay_ms = max(0, delay_ms)
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> MockChatCompletionClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any],
    ) -> str | None:
        del model, messages
        if self.delay_ms:
            time.sleep(self.delay_ms / 1000)
        name = response_format.get("name") if isinstance(response_format, dict) else None
        fixture = _FIXTURES.get(str(name))
        if fixture is None:
            raise AiError(f"No mock fixture for response format {name!r}")
        return json.dumps(_resolve_tokens(copy.deepcopy(fixture)))
