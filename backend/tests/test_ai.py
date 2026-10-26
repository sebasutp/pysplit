"""Stage 7 tests: AI configuration, prompts, extraction and category inference."""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import Settings
from app.services import ai as ai_service
from app.utils.receipt_extraction import (
    MAX_RECEIPT_ITEMS,
    normalize_receipt,
    parse_receipt_items_response,
)
from tests.helpers import access_headers, make_expense, make_group, make_user


class FakeAiClient:
    """Deterministic stand-in for the paid Chat Completions call."""

    def __init__(self, content: str | None = None, *, error: bool = False) -> None:
        self.content = content
        self.error = error
        self.calls: list[dict] = []
        self.closed = False

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise ai_service.AiError("provider down")
        return self.content

    def close(self) -> None:
        self.closed = True


def _patch_ai(monkeypatch, fake: FakeAiClient) -> None:
    monkeypatch.setattr(ai_service, "get_ai_client", lambda _settings: fake)


def _upload(client, group_id: str, data: bytes = b"\x89PNG\r\n\x1a\nexample"):
    return client.post(
        f"/api/groups/{group_id}/receipts/upload",
        files={"file": ("receipt.png", data, "image/png")},
        data={"width": "800", "height": "600"},
    )


def _auth(session) -> dict[str, str]:
    """Authenticated headers for paid-AI endpoints."""
    return access_headers(make_user(session))


# ---------------------------------------------------------------------------
# Configuration and prompts
# ---------------------------------------------------------------------------


def test_ai_config_precedence():
    settings = Settings(
        _env_file=None,
        openai_api_key="sk-openai",
        openai_base_url="https://api.openai.com/v1",
        openai_model_receipt_extract="gpt-vision",
        openai_model_category_extract="gpt-text",
        ai_api_key="gemini-key",
        ai_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ai_model_receipt_extract="gemini-2.5-flash",
        ai_model_category_extract="gemini-2.5-flash-lite",
    )

    assert ai_service.get_ai_api_key(settings) == "gemini-key"
    assert (
        ai_service.get_ai_base_url(settings)
        == "https://generativelanguage.googleapis.com/v1beta/openai"
    )
    assert settings.ai_provider == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert settings.receipt_extract_model == "gemini-2.5-flash"
    assert settings.category_extract_model == "gemini-2.5-flash-lite"
    assert settings.receipt_items_model == "gemini-2.5-flash"

    fallback = Settings(_env_file=None)
    assert ai_service.get_ai_api_key(fallback) is None
    assert ai_service.get_ai_base_url(fallback) is None
    assert fallback.ai_provider == "openai"
    assert fallback.receipt_extract_model == "gpt-5-nano"
    assert fallback.category_extract_model == "gpt-5-nano"

    # Public receipt labels never contain the internal base URL.
    assert settings.ai_provider_label == "google"
    assert fallback.ai_provider_label == "disabled"
    assert (
        Settings(_env_file=None, openai_api_key="sk-openai").ai_provider_label
        == "openai-compatible"
    )


def test_prompt_contract():
    categories = ['"General/General" (ID: 0)', '"Transport/Taxi" (ID: 4)']

    extract = ai_service.build_receipt_extract_prompt(categories)
    assert categories[0] in extract
    assert categories[1] in extract
    assert "Read the total amount" in extract
    assert "Guess a title" in extract

    items = ai_service.build_receipt_items_prompt(categories)
    assert categories[0] in items
    assert "List every purchased line item" in items
    assert "A normal purchased item must never be listed as a charge" in items

    category = ai_service.build_category_extract_system_prompt(categories, categories[0])
    assert f"Categories: {','.join(categories)}" in category
    assert f"default to {categories[0]}" in category


def test_ai_request_uses_json_schema_and_bearer(monkeypatch):
    settings = Settings(
        _env_file=None, ai_api_key="secret", ai_base_url="https://ai.example.com/v1"
    )
    captured: dict = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"categoryId": 7}'}}]},
        )

    client = ai_service.ChatCompletionClient(
        settings,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    content = client.complete(
        model="model-x",
        messages=[{"role": "user", "content": "hi"}],
        response_format=ai_service.CATEGORY_EXTRACT_JSON_SCHEMA,
    )

    assert content == '{"categoryId": 7}'
    assert captured["url"] == "https://ai.example.com/v1/chat/completions"
    assert captured["auth"] == "Bearer secret"
    assert captured["body"]["response_format"]["type"] == "json_schema"
    assert captured["body"]["response_format"]["json_schema"]["name"] == "category_response"


# ---------------------------------------------------------------------------
# Defensive parsing
# ---------------------------------------------------------------------------


def test_receipt_extraction_returns_none_for_bad_output():
    assert parse_receipt_items_response(None) is None
    assert parse_receipt_items_response("") is None
    assert parse_receipt_items_response("   ") is None
    assert parse_receipt_items_response("not json") is None
    assert parse_receipt_items_response("[]") is None
    assert parse_receipt_items_response(json.dumps({"total": "a lot"})) is None
    assert (
        parse_receipt_items_response(
            json.dumps({"items": [{"name": "Coffee", "quantity": "two", "amount": 6}]})
        )
        is None
    )
    assert parse_receipt_items_response(json.dumps({"items": None})) is None


def test_receipt_extraction_normalizes_adjustments_and_quantities():
    parsed = parse_receipt_items_response(
        json.dumps(
            {
                "merchant": "Café ",
                "date": "2026-04-01",
                "currencyCode": "eur",
                "total": 16,
                "categoryId": 7,
                "items": [
                    {"name": " A ", "quantity": 0, "amount": 10},
                    {"name": "B", "quantity": 2, "unitPrice": 2, "amount": 4},
                ],
                "charges": [{"name": " Tax ", "amount": 1}],
            }
        )
    )
    assert parsed is not None
    normalized = normalize_receipt(parsed, 2)

    assert normalized["merchant"] == "Café"
    assert normalized["currency_code"] == "EUR"
    assert normalized["total"] == 1600
    assert normalized["category_id"] == "7"
    assert [item["position"] for item in normalized["items"]] == [0, 1, 2, 3]
    assert normalized["items"][0]["quantity_milli"] == 1000
    assert normalized["items"][0]["name"] == "A"
    assert normalized["items"][2]["is_shared"] is True
    assert normalized["items"][3] == {
        "name": "Adjustment",
        "quantity_milli": 1000,
        "unit_price": None,
        "amount": 100,
        "is_shared": True,
        "is_adjustment": True,
        "position": 3,
    }


def test_receipt_extraction_caps_items_and_uses_currency_decimals():
    payload = {
        "total": 1000,
        "items": [
            {"name": f"Item {index}", "quantity": 1, "amount": 1}
            for index in range(MAX_RECEIPT_ITEMS + 5)
        ],
        "charges": [{"name": "Tax", "amount": 2}],
    }
    parsed = parse_receipt_items_response(json.dumps(payload))
    assert parsed is not None
    assert len(parsed["items"]) == MAX_RECEIPT_ITEMS
    assert len(parsed["charges"]) == 1

    yen = normalize_receipt(
        {
            "merchant": None,
            "date": None,
            "currency_code": "JPY",
            "total": 1000,
            "category_id": None,
            "items": [{"name": "Ramen", "quantity": 1, "unit_price": 1000, "amount": 1000}],
            "charges": [],
        },
        0,
    )
    assert yen["items"][0]["amount"] == 1000
    assert yen["total"] == 1000


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


def test_receipt_endpoints_require_feature_flags(client, session):
    group, _people = make_group(session)
    headers = _auth(session)
    payload = {"image_url": "https://uploads.example.com/receipt.jpg"}

    assert (
        client.post(
            f"/api/groups/{group.id}/receipts/extract-total",
            json=payload,
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/groups/{group.id}/receipts/extract-items",
            json=payload,
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/groups/{group.id}/receipts/upload",
            files={"file": ("x.png", b"\x89PNG", "image/png")},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/ai/categories/infer",
            json={"title": "Dinner"},
            headers=headers,
        ).status_code
        == 403
    )


def test_ai_endpoints_require_authentication(client, session):
    group, _people = make_group(session)
    payload = {"image_url": "https://uploads.example.com/receipt.jpg"}

    assert (
        client.post(f"/api/groups/{group.id}/receipts/extract-total", json=payload).status_code
        == 401
    )
    assert (
        client.post(f"/api/groups/{group.id}/receipts/extract-items", json=payload).status_code
        == 401
    )
    assert client.post("/api/ai/categories/infer", json={"title": "Dinner"}).status_code == 401


def test_feature_flags(make_client):
    client = make_client(enable_receipt_items=True)
    body = client.get("/api/features").json()
    assert body["receipt_items"] is True
    # Enabling line items implies base receipt extraction.
    assert body["receipt_extract"] is True


def test_extract_total_endpoint(make_client, session, tmp_path, monkeypatch):
    fake = FakeAiClient(
        json.dumps({"amount": 42.5, "categoryId": "7", "date": "2026-04-01", "title": "Lunch"})
    )
    _patch_ai(monkeypatch, fake)
    client = make_client(enable_receipt_extract=True, upload_dir=str(tmp_path))
    group, _people = make_group(session)
    headers = _auth(session)
    upload = _upload(client, group.id)
    assert upload.status_code == 201, upload.text

    response = client.post(
        f"/api/groups/{group.id}/receipts/extract-total",
        json={"image_url": upload.json()["url"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "amount": 42.5,
        "category_id": "7",
        "date": "2026-04-01",
        "title": "Lunch",
    }
    assert len(fake.calls) == 1
    # The provider receives an inline data URL for locally stored images.
    assert fake.calls[0]["messages"][1]["content"][0]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


def test_extract_items_endpoint(make_client, session, tmp_path, monkeypatch):
    fake = FakeAiClient(
        json.dumps(
            {
                "merchant": "Cafe",
                "date": "2026-04-01",
                "currencyCode": "EUR",
                "total": 30,
                "categoryId": 7,
                "items": [
                    {"name": "Pizza", "quantity": 1, "unitPrice": 20, "amount": 20},
                    {"name": "Beer", "quantity": 2, "unitPrice": 5, "amount": 10},
                ],
                "charges": [{"name": "Tax", "amount": 2}],
            }
        )
    )
    _patch_ai(monkeypatch, fake)
    client = make_client(enable_receipt_items=True, upload_dir=str(tmp_path))
    group, _people = make_group(session)
    headers = _auth(session)
    upload = _upload(client, group.id)
    assert upload.status_code == 201, upload.text

    response = client.post(
        f"/api/groups/{group.id}/receipts/extract-items",
        json={"image_url": upload.json()["url"], "image_width": 800, "image_height": 600},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "EXTRACTED"
    assert body["receipt"]["status"] == "EXTRACTED"
    assert body["split"]["items_total"] == 3000
    assert len(body["items"]) == 4
    assert body["items"][-1]["name"] == "Adjustment"
    assert body["items"][-1]["is_adjustment"] is True
    # The internal AI base URL must never leak into the read model.
    assert body["receipt"]["provider"] in {"openai-compatible", "google", "disabled"}
    assert "://" not in (body["receipt"]["provider"] or "")

    # Re-uploading the same image reuses the successful parse (one paid call).
    again = client.post(
        f"/api/groups/{group.id}/receipts/extract-items",
        json={"image_url": upload.json()["url"]},
        headers=headers,
    )
    assert again.status_code == 200, again.text
    assert again.json()["receipt"]["id"] == body["receipt"]["id"]
    assert len(fake.calls) == 1


def test_extract_items_links_queued_receipt_to_expense(make_client, session, tmp_path, monkeypatch):
    fake = FakeAiClient(
        json.dumps(
            {
                "merchant": "Cafe",
                "date": "2026-04-01",
                "currencyCode": "USD",
                "total": 10,
                "items": [{"name": "Coffee", "quantity": 1, "amount": 10}],
            }
        )
    )
    _patch_ai(monkeypatch, fake)
    client = make_client(enable_receipt_items=True, upload_dir=str(tmp_path))
    group, people = make_group(session)
    expense = make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1), (people["Bob"], 1)],
        amount=1000,
    )
    headers = _auth(session)
    upload = _upload(client, group.id)
    assert upload.status_code == 201, upload.text

    response = client.post(
        f"/api/groups/{group.id}/receipts/extract-items",
        json={"image_url": upload.json()["url"], "expense_id": expense.id},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["receipt"]["expense_id"] == expense.id

    # The post-sync bootstrap reads the link from the server, so it survives.
    linked = client.get(
        f"/api/groups/{group.id}/expenses/{expense.id}/receipt",
        headers=headers,
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["receipt"]["id"] == body["receipt"]["id"]


def test_configured_item_cap(make_client, session, tmp_path, monkeypatch):
    fake = FakeAiClient(
        json.dumps(
            {
                "total": None,
                "items": [
                    {"name": "One", "quantity": 1, "amount": 1},
                    {"name": "Two", "quantity": 1, "amount": 2},
                ],
                "charges": [],
            }
        )
    )
    _patch_ai(monkeypatch, fake)
    client = make_client(
        enable_receipt_items=True,
        upload_dir=str(tmp_path),
        max_receipt_items=1,
    )
    group, _people = make_group(session)
    headers = _auth(session)
    upload = _upload(client, group.id)

    response = client.post(
        f"/api/groups/{group.id}/receipts/extract-items",
        json={"image_url": upload.json()["url"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert [item["name"] for item in response.json()["items"]] == ["One"]
    assert response.json()["split"]["items_total"] == 100


def test_configured_charge_cap(make_client, session, tmp_path, monkeypatch):
    fake = FakeAiClient(
        json.dumps(
            {
                "total": None,
                "items": [],
                "charges": [{"name": f"Charge {index}", "amount": 1} for index in range(5)],
            }
        )
    )
    _patch_ai(monkeypatch, fake)
    client = make_client(
        enable_receipt_items=True,
        upload_dir=str(tmp_path),
        max_receipt_items=2,
    )
    group, _people = make_group(session)
    headers = _auth(session)
    upload = _upload(client, group.id)

    response = client.post(
        f"/api/groups/{group.id}/receipts/extract-items",
        json={"image_url": upload.json()["url"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert [item["name"] for item in response.json()["items"]] == ["Charge 0", "Charge 1"]


def test_normalized_ai_items_respect_configured_limits(make_client, session, tmp_path, monkeypatch):
    fake = FakeAiClient(
        json.dumps(
            {
                "total": 1000,
                "items": [{"name": "Too expensive", "quantity": 1, "amount": 1000}],
                "charges": [],
            }
        )
    )
    _patch_ai(monkeypatch, fake)
    client = make_client(
        enable_receipt_items=True,
        upload_dir=str(tmp_path),
        max_receipt_item_amount=100,
    )
    group, _people = make_group(session)
    headers = _auth(session)
    upload = _upload(client, group.id)

    response = client.post(
        f"/api/groups/{group.id}/receipts/extract-items",
        json={"image_url": upload.json()["url"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["items"] == []
    assert len(fake.calls) == 1


def test_malformed_ai_output_fails_receipt(make_client, session, tmp_path, monkeypatch):
    fake = FakeAiClient("not json")
    _patch_ai(monkeypatch, fake)
    client = make_client(enable_receipt_items=True, upload_dir=str(tmp_path))
    group, _people = make_group(session)
    headers = _auth(session)
    upload = _upload(client, group.id)
    assert upload.status_code == 201, upload.text

    response = client.post(
        f"/api/groups/{group.id}/receipts/extract-items",
        json={"image_url": upload.json()["url"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["receipt"]["status"] == "FAILED"
    assert body["receipt"]["attempts"] == 1
    assert body["split"]["items_total"] == 0
    assert body["items"] == []

    # A failed receipt can be retried by the same image; claim permits FAILED.
    fake.content = json.dumps({"total": 10, "items": [], "charges": []})
    retried = client.post(
        f"/api/groups/{group.id}/receipts/extract-items",
        json={"image_url": upload.json()["url"]},
        headers=headers,
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "EXTRACTED"
    assert retried.json()["receipt"]["attempts"] == 2
    assert len(fake.calls) == 2


def test_retry_attempt_cap_returns_conflict(make_client, session, tmp_path, monkeypatch):
    fake = FakeAiClient("not json")
    _patch_ai(monkeypatch, fake)
    client = make_client(
        enable_receipt_items=True,
        upload_dir=str(tmp_path),
        receipt_max_attempts=1,
    )
    group, _people = make_group(session)
    headers = _auth(session)
    upload = _upload(client, group.id)

    first = client.post(
        f"/api/groups/{group.id}/receipts/extract-items",
        json={"image_url": upload.json()["url"]},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "FAILED"

    blocked = client.post(
        f"/api/groups/{group.id}/receipts/extract-items",
        json={"image_url": upload.json()["url"]},
        headers=headers,
    )
    assert blocked.status_code == 409, blocked.text
    assert "exhausted" in blocked.json()["detail"].lower()
    assert len(fake.calls) == 1


def test_ai_provider_failure_becomes_failed_receipt(make_client, session, tmp_path, monkeypatch):
    fake = FakeAiClient(error=True)
    _patch_ai(monkeypatch, fake)
    client = make_client(enable_receipt_items=True, upload_dir=str(tmp_path))
    group, _people = make_group(session)
    headers = _auth(session)
    upload = _upload(client, group.id)

    response = client.post(
        f"/api/groups/{group.id}/receipts/extract-items",
        json={"image_url": upload.json()["url"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "FAILED"
    assert response.json()["receipt"]["status"] == "FAILED"


def test_category_inference_endpoint(make_client, session, monkeypatch):
    fake = FakeAiClient(json.dumps({"categoryId": 7}))
    _patch_ai(monkeypatch, fake)
    client = make_client(enable_category_extract=True)
    headers = _auth(session)

    response = client.post(
        "/api/ai/categories/infer", json={"title": "Team dinner"}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"category_id": 7}
    assert fake.calls[0]["messages"][1]["content"] == "Team dinner"

    fake.content = "garbage"
    fallback = client.post(
        "/api/ai/categories/infer", json={"title": "Team dinner"}, headers=headers
    )
    assert fallback.json() == {"category_id": 0}

    # An unknown category id also falls back to General (0).
    fake.content = json.dumps({"categoryId": 9999})
    unknown = client.post(
        "/api/ai/categories/infer", json={"title": "Team dinner"}, headers=headers
    )
    assert unknown.json() == {"category_id": 0}


def test_category_inference_truncates_title(make_client, session, monkeypatch):
    fake = FakeAiClient(json.dumps({"categoryId": 1}))
    _patch_ai(monkeypatch, fake)
    client = make_client(enable_category_extract=True)
    headers = _auth(session)

    title = "x" * 100
    response = client.post("/api/ai/categories/infer", json={"title": title}, headers=headers)
    assert response.status_code == 200, response.text
    assert fake.calls[0]["messages"][1]["content"] == "x" * 40


@pytest.mark.parametrize("bad_url", ["https://evil.example.com/x.png", "data:image/png;base64,xx"])
def test_extraction_rejects_untrusted_image_urls(make_client, session, monkeypatch, bad_url):
    fake = FakeAiClient(json.dumps({"total": 1, "items": [], "charges": []}))
    _patch_ai(monkeypatch, fake)
    client = make_client(enable_receipt_items=True)
    group, _people = make_group(session)

    response = client.post(
        f"/api/groups/{group.id}/receipts/extract-items",
        json={"image_url": bad_url},
        headers=_auth(session),
    )
    assert response.status_code == 422, response.text
    assert fake.calls == []
