"""Attachment upload, retrieval, PDF support and receipt extraction tests."""

from __future__ import annotations

import json

import pytest
from sqlmodel import Session, select

from app.models.attachment import Attachment
from app.models.attachment_item import AttachmentItem
from app.services import ai as ai_service
from tests.helpers import (
    access_headers,
    make_expense,
    make_group,
    make_receipt,
    make_user,
)

PNG = b"\x89PNG\r\n\x1a\nexample"
PDF = b"%PDF-1.4\n% mock receipt\n"


class FakeAiClient:
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


def _upload(
    client,
    group_id: str,
    *,
    data: bytes = PNG,
    name: str = "receipt.png",
    content_type: str = "image/png",
    expense_id: str | None = None,
):
    form = {"width": "800", "height": "600"}
    if expense_id:
        form["expense_id"] = expense_id
    return client.post(
        f"/api/groups/{group_id}/attachments",
        files={"file": (name, data, content_type)},
        data=form,
    )


def test_upload_read_link_and_delete_attachment(make_client, session: Session, tmp_path):
    client = make_client(upload_dir=str(tmp_path))
    group, _people = make_group(session)
    upload = _upload(client, group.id)
    assert upload.status_code == 201, upload.text
    attachment = upload.json()
    assert attachment["group_id"] == group.id
    assert attachment["expense_id"] is None
    assert attachment["content_type"] == "image/png"
    assert attachment["width"] == 800
    assert attachment["url"].endswith(f"/attachments/{attachment['id']}/file")
    assert list((tmp_path / "attachments").rglob("*.png"))

    metadata = client.get(f"/api/groups/{group.id}/attachments/{attachment['id']}")
    assert metadata.status_code == 200
    assert metadata.json()["filename"] == "receipt.png"

    download = client.get(f"/api/groups/{group.id}/attachments/{attachment['id']}/file")
    assert download.status_code == 200
    assert download.content.startswith(b"\x89PNG")
    assert download.headers["content-type"].startswith("image/png")

    expense = make_expense(
        session,
        group=group,
        paid_by=_people["Alice"],
        paid_for=[(_people["Alice"], 1)],
        amount=1000,
    )
    linked = client.patch(
        f"/api/groups/{group.id}/attachments/{attachment['id']}",
        json={"expense_id": expense.id},
    )
    assert linked.status_code == 200
    assert linked.json()["expense_id"] == expense.id

    deleted = client.delete(f"/api/groups/{group.id}/attachments/{attachment['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/groups/{group.id}/attachments/{attachment['id']}").status_code == 404


def test_pdf_is_an_attachment_but_not_ai_scannable(make_client, session: Session, tmp_path):
    client = make_client(enable_receipt_ai=True, upload_dir=str(tmp_path))
    group, _people = make_group(session)
    upload = _upload(
        client,
        group.id,
        data=PDF,
        name="invoice.pdf",
        content_type="application/pdf",
    )
    assert upload.status_code == 201, upload.text
    attachment = upload.json()
    assert attachment["content_type"] == "application/pdf"
    assert attachment["thumbnail_url"] is None

    download = client.get(f"/api/groups/{group.id}/attachments/{attachment['id']}/file")
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")
    assert download.headers["content-type"].startswith("application/pdf")

    response = client.post(
        f"/api/groups/{group.id}/attachments/{attachment['id']}/extract-items",
        json={},
        headers=access_headers(make_user(session)),
    )
    assert response.status_code == 422
    assert "images only" in response.text.lower()


@pytest.mark.parametrize(
    ("content_type", "payload"),
    [
        ("text/plain", b"hello"),
        ("image/png", b""),
    ],
)
def test_upload_rejects_unsupported_files(
    make_client, session: Session, tmp_path, content_type, payload
):
    client = make_client(upload_dir=str(tmp_path))
    group, _people = make_group(session)
    response = _upload(
        client,
        group.id,
        data=payload,
        name="x.bin",
        content_type=content_type,
    )
    assert response.status_code in {413, 422}


def test_upload_signature_wins_over_browser_mime(make_client, session: Session, tmp_path):
    client = make_client(upload_dir=str(tmp_path))
    group, _people = make_group(session)
    response = _upload(client, group.id, data=PNG, name="x.bin", content_type="image/jpeg")
    assert response.status_code == 201
    assert response.json()["content_type"] == "image/png"


def test_upload_enforces_size_limit(make_client, session: Session, tmp_path):
    client = make_client(upload_dir=str(tmp_path), max_upload_bytes=3)
    group, _people = make_group(session)
    response = _upload(client, group.id)
    assert response.status_code == 413


def test_extract_total_and_items(make_client, session: Session, tmp_path, monkeypatch):
    fake = FakeAiClient(
        json.dumps(
            {
                "merchant": "Cafe",
                "date": "2026-04-01",
                "currencyCode": "EUR",
                "total": 30,
                "categoryId": 0,
                "items": [
                    {"name": "Pizza", "quantity": 1, "unitPrice": 20, "amount": 20},
                    {"name": "Beer", "quantity": 2, "unitPrice": 5, "amount": 10},
                ],
                "charges": [{"name": "Tax", "amount": 2}],
            }
        )
    )
    _patch_ai(monkeypatch, fake)
    client = make_client(enable_receipt_ai=True, upload_dir=str(tmp_path))
    group, people = make_group(session)
    expense = make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1), (people["Bob"], 1)],
        amount=1000,
    )
    headers = access_headers(make_user(session))
    upload = _upload(client, group.id)
    attachment_id = upload.json()["id"]

    fake.content = json.dumps(
        {
            "amount": 24.5,
            "categoryId": "0",
            "date": "2026-04-01",
            "title": "Lunch",
        }
    )
    total = client.post(
        f"/api/groups/{group.id}/attachments/{attachment_id}/extract-total",
        headers=headers,
    )
    assert total.status_code == 200, total.text
    assert total.json()["amount"] == 24.5
    fake.content = json.dumps(
        {
            "merchant": "Cafe",
            "date": "2026-04-01",
            "currencyCode": "EUR",
            "total": 30,
            "categoryId": 0,
            "items": [
                {"name": "Pizza", "quantity": 1, "unitPrice": 20, "amount": 20},
                {"name": "Beer", "quantity": 2, "unitPrice": 5, "amount": 10},
            ],
            "charges": [{"name": "Tax", "amount": 2}],
        }
    )

    response = client.post(
        f"/api/groups/{group.id}/attachments/{attachment_id}/extract-items",
        json={"expense_id": expense.id},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "EXTRACTED"
    assert body["attachment"]["id"] == attachment_id
    assert body["attachment"]["expense_id"] == expense.id
    assert len(body["items"]) == 4
    assert body["items"][-1]["name"] == "Adjustment"

    # Reposting a completed attachment reuses the parse without another call.
    again = client.post(
        f"/api/groups/{group.id}/attachments/{attachment_id}/extract-items",
        json={},
        headers=headers,
    )
    assert again.status_code == 200
    assert again.json()["attachment"]["id"] == attachment_id

    state = client.get(
        f"/api/groups/{group.id}/attachments/{attachment_id}/receipt",
        headers=headers,
    )
    assert state.status_code == 200
    assert state.json()["items"][0]["name"] == "Pizza"


def test_extraction_failure_is_recorded(make_client, session: Session, tmp_path, monkeypatch):
    _patch_ai(monkeypatch, FakeAiClient("not json"))
    client = make_client(enable_receipt_ai=True, upload_dir=str(tmp_path))
    group, _people = make_group(session)
    attachment_id = _upload(client, group.id).json()["id"]

    response = client.post(
        f"/api/groups/{group.id}/attachments/{attachment_id}/extract-items",
        json={},
        headers=access_headers(make_user(session)),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "FAILED"
    assert response.json()["attachment"]["receipt_status"] == "FAILED"


def test_items_and_apply(make_client, session: Session, tmp_path):
    client = make_client(enable_receipt_ai=True, upload_dir=str(tmp_path))
    group, people = make_group(session)
    expense = make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1), (people["Bob"], 1)],
        amount=1000,
    )
    attachment = make_receipt(
        session,
        group=group,
        expense_id=expense.id,
        total=1000,
        items=[
            {
                "name": "Pizza",
                "amount": 600,
                "portions": [{"participant": people["Alice"].id, "quantity_milli": 1000}],
            },
            {
                "name": "Beer",
                "amount": 400,
                "portions": [{"participant": people["Bob"].id, "quantity_milli": 1000}],
            },
        ],
    )

    state = client.get(f"/api/groups/{group.id}/attachments/{attachment.id}/receipt")
    assert state.status_code == 200
    assert state.json()["split"]["items_total"] == 1000

    added = client.post(
        f"/api/groups/{group.id}/attachments/{attachment.id}/items",
        json={"name": "Tip", "quantity_milli": 1000, "amount": 100, "is_shared": True},
    )
    assert added.status_code == 201, added.text
    item_id = added.json()["items"][-1]["id"]

    updated = client.patch(
        f"/api/groups/{group.id}/attachments/{attachment.id}/items/{item_id}",
        json={"name": "Service"},
    )
    assert updated.status_code == 200
    assert updated.json()["items"][-1]["name"] == "Service"

    portions = client.put(
        f"/api/groups/{group.id}/attachments/{attachment.id}/items/{item_id}/portions",
        json={
            "portions": [
                {
                    "target": "PARTICIPANT",
                    "participant_id": people["Alice"].id,
                    "quantity_milli": 1000,
                }
            ]
        },
    )
    assert portions.status_code == 200

    opt_out = client.put(
        f"/api/groups/{group.id}/attachments/{attachment.id}/opt-outs/{people['Bob'].id}",
        json={"opted_out": True},
    )
    assert opt_out.status_code == 200
    assert people["Bob"].id in opt_out.json()["opt_outs"]

    applied = client.post(
        f"/api/groups/{group.id}/attachments/{attachment.id}/apply",
        json={"expense_id": expense.id},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["attachment"]["id"] == attachment.id

    session.expire_all()
    stored = session.get(Attachment, attachment.id)
    assert stored is not None
    items = session.exec(
        select(AttachmentItem).where(AttachmentItem.attachment_id == attachment.id)
    ).all()
    assert items
