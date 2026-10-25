"""Security-hardening regression tests: identity, limits and storage reuse."""

from __future__ import annotations

from types import SimpleNamespace

from starlette.datastructures import Headers

from app.core.config import Settings
from app.core.limits import (
    SlidingWindowRateLimiter,
    ai_rate_limiter,
    client_key,
    sync_rate_limiter,
)
from app.storage import get_storage, reset_storage
from tests.helpers import access_headers, make_group, make_user


def _request(headers: dict[str, str] | None = None, host: str = "10.0.0.1"):
    return SimpleNamespace(
        headers=Headers(headers or {}),
        client=SimpleNamespace(host=host),
    )


def test_client_key_ignores_forwarded_headers_by_default():
    request = _request({"x-forwarded-for": "203.0.113.9, 10.0.0.5"})
    untrusted = Settings(_env_file=None)
    trusted = Settings(_env_file=None, trust_forwarded_headers=True)

    assert client_key(request, untrusted) == "10.0.0.1"
    assert client_key(request, trusted) == "203.0.113.9"


def test_client_key_falls_back_without_client_or_valid_forwarded_value():
    trusted = Settings(_env_file=None, trust_forwarded_headers=True)

    assert client_key(_request({"x-forwarded-for": "  "}), trusted) == "10.0.0.1"
    assert client_key(_request(), trusted) == "10.0.0.1"
    assert client_key(SimpleNamespace(headers=Headers({}), client=None), trusted) == "unknown"


def test_rate_limiter_evicts_stale_keys():
    limiter = SlidingWindowRateLimiter()
    limiter.check("old", limit=1, window_seconds=60, now=0)

    for index in range(limiter._prune_every):
        limiter.check(f"key-{index}", limit=1, window_seconds=60, now=1000)

    assert "old" not in limiter._events
    assert len(limiter._events) <= limiter._prune_every


def test_storage_is_cached_and_can_be_reset(tmp_path):
    settings = Settings(_env_file=None, upload_dir=str(tmp_path))
    first = get_storage(settings)
    second = get_storage(settings)
    assert first is second

    moved = Settings(_env_file=None, upload_dir=str(tmp_path / "other"))
    assert get_storage(moved) is not first

    reset_storage()
    rebuilt = get_storage(settings)
    assert rebuilt is not second


def test_sync_push_is_rate_limited(make_client, session):
    sync_rate_limiter.reset()
    client = make_client(sync_rate_limit_per_minute=2)
    group, _people = make_group(session)
    operation = {
        "op_id": "op-rate-1",
        "group_id": group.id,
        "entity_type": "unknown",
        "entity_id": "entity-rate-1",
        "op_type": "create",
        "payload": {},
        "client_time": "2026-10-25T12:00:00Z",
    }

    assert client.post("/api/sync/push", json={"operations": [operation]}).status_code == 200
    assert client.post("/api/sync/push", json={"operations": [operation]}).status_code == 200
    throttled = client.post("/api/sync/push", json={"operations": [operation]})
    assert throttled.status_code == 429, throttled.text
    assert "Retry-After" in throttled.headers
    sync_rate_limiter.reset()


class _FakeAi:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, **_kwargs):
        self.calls += 1
        return '{"amount": 1, "categoryId": "0", "date": "2026-10-25", "title": "x"}'

    def close(self) -> None:
        pass


def test_anonymous_ai_calls_do_not_consume_the_ai_budget(make_client, session, monkeypatch):
    from app.services import ai as ai_service

    ai_rate_limiter.reset()
    fake = _FakeAi()
    monkeypatch.setattr(ai_service, "get_ai_client", lambda _settings: fake)
    client = make_client(enable_receipt_extract=True, ai_rate_limit_per_minute=1)
    group, _people = make_group(session)
    payload = {"image_url": "/api/groups/g/receipts/images/img_missing.png"}

    # Authentication fails before the paid-call limiter is touched.
    assert (
        client.post(f"/api/groups/{group.id}/receipts/extract-total", json=payload).status_code
        == 401
    )
    assert (
        client.post(f"/api/groups/{group.id}/receipts/extract-total", json=payload).status_code
        == 401
    )

    headers = access_headers(make_user(session))
    response = client.post(
        f"/api/groups/{group.id}/receipts/extract-total",
        json=payload,
        headers=headers,
    )
    # The unknown image is rejected after the rate-limit check, which proves
    # the authenticated caller still has its full budget.
    assert response.status_code == 422, response.text
    assert fake.calls == 0
    ai_rate_limiter.reset()
