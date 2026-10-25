"""Stage 7 tests: receipt lifecycle, provisional splits, item CRUD and uploads."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.core.config import Settings
from app.models.receipt import Receipt
from app.models.receipt_item import ReceiptItem
from app.schemas.receipts import ReceiptItemCreate
from app.services import receipts as receipts_service
from app.services import uploads as uploads_service
from app.services.errors import ConflictError, InvalidInputError
from app.storage import LocalBlobStorage, S3BlobStorage, build_storage
from app.utils.receipt_split import (
    compute_receipt_split,
    to_receipt_split_items,
)
from tests.helpers import make_expense, make_group, make_receipt


def _extracted_receipt(session: Session, *, items=None, opt_outs=()):
    group, people = make_group(session)
    resolved_items = items(people) if callable(items) else items
    resolved_opt_outs = opt_outs(people) if callable(opt_outs) else opt_outs
    receipt = make_receipt(
        session,
        group=group,
        items=resolved_items
        or [
            {
                "name": "Pizza",
                "quantity_milli": 1000,
                "amount": 1000,
            }
        ],
        opt_outs=resolved_opt_outs,
    )
    return group, people, receipt


def _settings(**overrides) -> Settings:
    defaults = {"_env_file": None, "enable_receipt_items": True}
    defaults.update(overrides)
    return Settings(**defaults)


# ---------------------------------------------------------------------------
# Pure split math
# ---------------------------------------------------------------------------


def test_provisional_split_unassigned_and_shared():
    result = compute_receipt_split(
        ["p1", "p2", "p3"],
        [],
        [{"amount": 1000, "quantity_milli": 1000, "portions": []}],
    )
    assert sorted(share.total for share in result.participants) == [333, 333, 334]
    assert sum(share.total for share in result.participants) == result.items_total == 1000

    mixed = compute_receipt_split(
        ["p1", "p2", "p3"],
        ["p1"],
        [
            {"amount": 900, "quantity_milli": 1000, "portions": []},
            {
                "amount": 300,
                "quantity_milli": 1000,
                "portions": [{"target": "SHARED", "quantity_milli": 1000}],
            },
        ],
    )
    by_id = {share.participant_id: share for share in mixed.participants}
    assert by_id["p1"].shared == 100
    assert by_id["p1"].unassigned == 0
    assert by_id["p1"].total == 100
    assert by_id["p2"].unassigned == 450
    assert by_id["p3"].unassigned == 450
    assert mixed.shared_pool == 300
    assert mixed.unassigned_pool == 900


def test_provisional_split_fractional_and_clamped():
    thirds = compute_receipt_split(
        ["p1", "p2", "p3"],
        [],
        [
            {
                "amount": 1000,
                "quantity_milli": 1000,
                "portions": [
                    {"target": "PARTICIPANT", "participant_id": "p1", "quantity_milli": 333},
                    {"target": "PARTICIPANT", "participant_id": "p2", "quantity_milli": 333},
                    {"target": "PARTICIPANT", "participant_id": "p3", "quantity_milli": 333},
                ],
            }
        ],
    )
    assert [share.total for share in thirds.participants] == [334, 333, 333]
    assert sum(share.total for share in thirds.participants) == thirds.items_total

    clamped = compute_receipt_split(
        ["p1", "p2"],
        [],
        [
            {
                "amount": 1000,
                "quantity_milli": 1000,
                "portions": [
                    {"target": "PARTICIPANT", "participant_id": "p1", "quantity_milli": 800},
                    {"target": "PARTICIPANT", "participant_id": "p2", "quantity_milli": 800},
                ],
            }
        ],
    )
    by_id = {share.participant_id: share for share in clamped.participants}
    assert by_id["p1"].direct == 800
    assert by_id["p2"].direct == 200
    assert clamped.unassigned_pool == 0


def test_provisional_split_ignores_unknown_participants_and_handles_zero_quantity():
    result = compute_receipt_split(
        ["p1", "p2"],
        [],
        [
            {
                "amount": 1000,
                "quantity_milli": 1000,
                "portions": [
                    {"target": "PARTICIPANT", "participant_id": "ghost", "quantity_milli": 500},
                    {"target": "PARTICIPANT", "participant_id": "p1", "quantity_milli": 500},
                ],
            }
        ],
    )
    by_id = {share.participant_id: share for share in result.participants}
    assert by_id["p1"].direct == 500
    assert result.unassigned_pool == 500
    assert "ghost" not in by_id

    zero_quantity = compute_receipt_split(
        ["p1", "p2"],
        [],
        [
            {
                "amount": 500,
                "quantity_milli": 0,
                "portions": [
                    {"target": "PARTICIPANT", "participant_id": "p1", "quantity_milli": 1}
                ],
            }
        ],
    )
    assert zero_quantity.participants[0].direct == 500
    assert zero_quantity.unassigned_pool == 0


def test_provisional_split_all_opted_out():
    result = compute_receipt_split(
        ["p1", "p2"],
        ["p1", "p2"],
        [{"amount": 1000, "quantity_milli": 1000, "portions": []}],
    )
    assert result.all_opted_out is True
    assert result.unassigned_pool == 1000


def test_receipt_draft_shared_fallback():
    items = to_receipt_split_items(
        [
            {
                "amount": 500,
                "quantity_milli": 1000,
                "is_shared": True,
                "portions": [],
            },
            {
                "amount": 1000,
                "quantity_milli": 1000,
                "is_shared": True,
                "portions": [
                    {"target": "PARTICIPANT", "participant_id": "p1", "quantity_milli": 1000}
                ],
            },
        ]
    )
    assert items[0].portions[0].target == "SHARED"
    assert items[1].portions[0].target == "PARTICIPANT"

    split = compute_receipt_split(["p1", "p2"], ["p1"], items)
    by_id = {share.participant_id: share for share in split.participants}
    assert by_id["p1"].shared == 250
    assert by_id["p1"].direct == 1000
    assert by_id["p2"].shared == 250


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_receipt_lifecycle(session: Session):
    group, _people = make_group(session)
    image_url = "https://uploads.example.com/lifecycle.png"
    receipt = receipts_service.create_pending_receipt(
        session,
        group_id=group.id,
        image_url=image_url,
        image_width=800,
        image_height=600,
    )
    assert receipt.status == "PENDING"
    assert receipts_service.get_receipt_by_image(session, group.id, image_url).id == receipt.id

    settings = _settings()
    assert receipts_service.claim_receipt_for_extraction(session, receipt.id, settings=settings)
    assert not receipts_service.claim_receipt_for_extraction(session, receipt.id, settings=settings)

    # A crashed claim older than the stale window is recoverable.
    session.refresh(receipt)
    receipt.updated_at = datetime.now(UTC) - timedelta(seconds=600)
    session.add(receipt)
    session.commit()
    assert receipts_service.claim_receipt_for_extraction(session, receipt.id, settings=settings)

    normalized = {
        "merchant": "Cafe",
        "date": "2026-04-01",
        "currency_code": "EUR",
        "total": 1500,
        "category_id": "7",
        "items": [
            {
                "name": "Coffee",
                "quantity_milli": 2000,
                "unit_price": 300,
                "amount": 600,
                "is_shared": False,
                "is_adjustment": False,
                "position": 0,
            },
            {
                "name": "Cake",
                "quantity_milli": 1000,
                "unit_price": None,
                "amount": 900,
                "is_shared": False,
                "is_adjustment": False,
                "position": 1,
            },
        ],
        "items_total": 1500,
    }
    completed = receipts_service.complete_receipt(
        session,
        receipt.id,
        raw_extraction='{"categoryId": 7}',
        provider="openai",
        model="test-model",
        normalized=normalized,
    )
    assert completed.status == "EXTRACTED"
    assert completed.merchant == "Cafe"
    assert completed.total == 1500
    assert completed.receipt_date.isoformat().startswith("2026-04-01")
    items = session.exec(select(ReceiptItem).where(ReceiptItem.receipt_id == receipt.id)).all()
    assert [item.name for item in items] == ["Coffee", "Cake"]
    assert [item.position for item in items] == [0, 1]

    # Re-completing replaces items instead of appending.
    second = receipts_service.complete_receipt(
        session,
        receipt.id,
        raw_extraction=None,
        provider=None,
        model=None,
        normalized={**normalized, "total": 600, "items": [normalized["items"][0]]},
    )
    assert second.total == 600
    items = session.exec(select(ReceiptItem).where(ReceiptItem.receipt_id == receipt.id)).all()
    assert len(items) == 1

    receipts_service.fail_receipt(
        session,
        receipt.id,
        raw_extraction="malformed",
        provider="openai",
        model="test-model",
    )
    session.refresh(receipt)
    assert receipt.status == "FAILED"
    assert receipt.raw_extraction == "malformed"


def test_claim_receipt_once(session: Session):
    group, _people = make_group(session)
    receipt = receipts_service.create_pending_receipt(
        session,
        group_id=group.id,
        image_url="https://uploads.example.com/claim.png",
    )
    settings = _settings()
    results = [
        receipts_service.claim_receipt_for_extraction(session, receipt.id, settings=settings)
        for _ in range(4)
    ]
    assert results == [True, False, False, False]


def test_claim_attempts_are_capped(session: Session):
    group, _people = make_group(session)
    settings = _settings(receipt_max_attempts=2)
    receipt = receipts_service.create_pending_receipt(
        session,
        group_id=group.id,
        image_url="https://uploads.example.com/attempts.png",
    )

    assert receipts_service.claim_receipt_for_extraction(session, receipt.id, settings=settings)
    session.refresh(receipt)
    assert receipt.attempts == 1

    receipts_service.fail_receipt(
        session,
        receipt.id,
        raw_extraction=None,
        provider=None,
        model=None,
    )
    # A failed receipt may be retried while the budget remains.
    assert receipts_service.claim_receipt_for_extraction(session, receipt.id, settings=settings)
    session.refresh(receipt)
    assert receipt.attempts == 2

    receipts_service.fail_receipt(
        session,
        receipt.id,
        raw_extraction=None,
        provider=None,
        model=None,
    )
    with pytest.raises(ConflictError, match="exhausted"):
        receipts_service.claim_receipt_for_extraction(session, receipt.id, settings=settings)
    session.refresh(receipt)
    assert receipt.attempts == 2


def test_manual_item_add_respects_configured_cap(session: Session):
    group, _people = make_group(session)
    receipt = make_receipt(
        session,
        group=group,
        items=[{"name": "Existing", "quantity_milli": 1000, "amount": 100}],
    )

    with pytest.raises(InvalidInputError, match="too many items"):
        receipts_service.add_item(
            session,
            group.id,
            receipt.id,
            ReceiptItemCreate(name="Extra", quantity_milli=1000, amount=100),
            settings=_settings(max_receipt_items=1),
        )


def test_concurrent_claim_calls_only_one_model(tmp_path):
    import threading

    from sqlalchemy import create_engine, text
    from sqlmodel import SQLModel

    engine = create_engine(
        f"sqlite:///{tmp_path / 'claims.db'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as setup:
        setup.execute(text("PRAGMA journal_mode=WAL"))
        group, _people = make_group(setup)
        receipt = receipts_service.create_pending_receipt(
            setup,
            group_id=group.id,
            image_url="https://uploads.example.com/concurrent.png",
        )
        receipt_id = receipt.id

    settings = _settings()
    barrier = threading.Barrier(2)
    results: list[bool] = []
    lock = threading.Lock()

    def claim() -> None:
        with Session(engine) as worker_session:
            barrier.wait(timeout=5)
            won = receipts_service.claim_receipt_for_extraction(
                worker_session,
                receipt_id,
                settings=settings,
            )
            with lock:
                results.append(won)

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(results) == [False, True]
    with Session(engine) as check:
        stored = check.get(Receipt, receipt_id)
        assert stored is not None
        assert stored.status == "EXTRACTING"
    engine.dispose()


def test_receipt_read_never_exposes_provider_url(make_client, session: Session):
    client = make_client(enable_receipt_items=True)
    group, _people = make_group(session)
    receipt = make_receipt(
        session,
        group=group,
        items=[{"name": "Pizza", "quantity_milli": 1000, "amount": 100}],
    )
    receipt.provider = "https://internal-ai.example.com/v1"
    session.add(receipt)
    session.commit()

    body = client.get(f"/api/groups/{group.id}/receipts/{receipt.id}").json()
    assert body["receipt"]["provider"] == "openai-compatible"


def test_get_receipt_split(make_client, session: Session):
    client = make_client(enable_receipt_items=True)
    group, people, receipt = _extracted_receipt(
        session,
        items=lambda people: [
            {
                "name": "Pizza",
                "quantity_milli": 1000,
                "amount": 1000,
                "portions": [
                    {
                        "target": "PARTICIPANT",
                        "participant_id": people["Alice"].id,
                        "quantity_milli": 1000,
                    }
                ],
            },
            {
                "name": "Tax",
                "quantity_milli": 1000,
                "amount": 100,
                "is_shared": True,
            },
        ],
    )
    response = client.get(f"/api/groups/{group.id}/receipts/{receipt.id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["receipt"]["id"] == receipt.id
    assert [item["name"] for item in body["items"]] == ["Pizza", "Tax"]
    assert body["split"]["items_total"] == 1100
    assert body["split"]["total"] == 1100
    assert body["split"]["shared"] == 100
    by_id = {row["participant_id"]: row for row in body["split"]["participants"]}
    assert by_id[people["Alice"].id]["total"] == 1050
    assert by_id[people["Bob"].id]["total"] == 50

    # Receipts are group-scoped capability URLs.
    assert client.get(f"/api/groups/missing/receipts/{receipt.id}").status_code == 404


def test_get_receipt_for_expense(make_client, session: Session):
    client = make_client(enable_receipt_items=True)
    group, people, receipt = _extracted_receipt(session)
    expense = make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1)],
        amount=1000,
    )
    assert client.get(f"/api/groups/{group.id}/expenses/{expense.id}/receipt").status_code == 404
    linked = client.post(
        f"/api/groups/{group.id}/receipts/{receipt.id}/link",
        json={"expense_id": expense.id},
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["expense_id"] == expense.id
    found = client.get(f"/api/groups/{group.id}/expenses/{expense.id}/receipt")
    assert found.status_code == 200
    assert found.json()["receipt"]["id"] == receipt.id


def test_add_update_delete_item(make_client, session: Session):
    client = make_client(enable_receipt_items=True)
    group, _people, receipt = _extracted_receipt(session)

    added = client.post(
        f"/api/groups/{group.id}/receipts/{receipt.id}/items",
        json={"name": "Dessert", "quantity_milli": 1000, "amount": 400, "is_shared": False},
    )
    assert added.status_code == 201, added.text
    body = added.json()
    new_item = next(item for item in body["items"] if item["name"] == "Dessert")
    assert new_item["position"] == 1
    assert body["split"]["items_total"] == 1400

    updated = client.patch(
        f"/api/groups/{group.id}/receipts/{receipt.id}/items/{new_item['id']}",
        json={"name": "Cake", "amount": 700, "quantity_milli": 2000},
    )
    assert updated.status_code == 200, updated.text
    changed = next(item for item in updated.json()["items"] if item["id"] == new_item["id"])
    assert changed["name"] == "Cake"
    assert changed["amount"] == 700
    assert changed["quantity_milli"] == 2000

    deleted = client.delete(f"/api/groups/{group.id}/receipts/{receipt.id}/items/{new_item['id']}")
    assert deleted.status_code == 200, deleted.text
    assert all(item["id"] != new_item["id"] for item in deleted.json()["items"])
    assert deleted.json()["split"]["items_total"] == 1000


def test_set_portions(make_client, session: Session):
    client = make_client(enable_receipt_items=True)
    group, people = make_group(session)
    receipt = make_receipt(
        session,
        group=group,
        items=[{"name": "Pizza", "quantity_milli": 1000, "amount": 1000}],
    )
    item_id = client.get(f"/api/groups/{group.id}/receipts/{receipt.id}").json()["items"][0]["id"]

    response = client.put(
        f"/api/groups/{group.id}/receipts/{receipt.id}/items/{item_id}/portions",
        json={
            "portions": [
                {
                    "target": "PARTICIPANT",
                    "participant_id": people["Alice"].id,
                    "quantity_milli": 500,
                },
                {"target": "SHARED", "quantity_milli": 500},
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"][0]["is_shared"] is False
    by_id = {row["participant_id"]: row for row in body["split"]["participants"]}
    assert by_id[people["Alice"].id]["direct"] == 500
    assert by_id[people["Alice"].id]["shared"] == 250
    assert by_id[people["Bob"].id]["shared"] == 250

    invalid_participant = client.put(
        f"/api/groups/{group.id}/receipts/{receipt.id}/items/{item_id}/portions",
        json={
            "portions": [
                {"target": "PARTICIPANT", "participant_id": "ghost", "quantity_milli": 500}
            ]
        },
    )
    assert invalid_participant.status_code == 422

    too_much = client.put(
        f"/api/groups/{group.id}/receipts/{receipt.id}/items/{item_id}/portions",
        json={
            "portions": [
                {
                    "target": "PARTICIPANT",
                    "participant_id": people["Alice"].id,
                    "quantity_milli": 600,
                },
                {
                    "target": "PARTICIPANT",
                    "participant_id": people["Bob"].id,
                    "quantity_milli": 600,
                },
            ]
        },
    )
    assert too_much.status_code == 422

    cleared = client.put(
        f"/api/groups/{group.id}/receipts/{receipt.id}/items/{item_id}/portions",
        json={"portions": []},
    )
    assert cleared.status_code == 200
    assert cleared.json()["items"][0]["portions"] == []
    assert cleared.json()["items"][0]["is_shared"] is False


def test_set_opt_out(make_client, session: Session):
    client = make_client(enable_receipt_items=True)
    group, people, receipt = _extracted_receipt(
        session,
        items=[{"name": "Pizza", "quantity_milli": 1000, "amount": 1000}],
    )
    url = f"/api/groups/{group.id}/receipts/{receipt.id}/opt-outs/{people['Alice'].id}"
    opted_out = client.put(url, json={"opted_out": True})
    assert opted_out.status_code == 200, opted_out.text
    body = opted_out.json()
    assert body["opt_outs"] == [people["Alice"].id]
    by_id = {row["participant_id"]: row for row in body["split"]["participants"]}
    assert by_id[people["Alice"].id]["unassigned"] == 0
    assert by_id[people["Bob"].id]["unassigned"] == 1000

    opted_in = client.put(url, json={"opted_out": False})
    assert opted_in.status_code == 200
    assert opted_in.json()["opt_outs"] == []

    unknown = client.put(
        f"/api/groups/{group.id}/receipts/{receipt.id}/opt-outs/ghost",
        json={"opted_out": True},
    )
    assert unknown.status_code == 422


def test_item_limits(make_client, session: Session):
    client = make_client(enable_receipt_items=True)
    group, _people, receipt = _extracted_receipt(session)
    base = f"/api/groups/{group.id}/receipts/{receipt.id}/items"

    assert (
        client.post(base, json={"name": "x" * 201, "quantity_milli": 1000, "amount": 1}).status_code
        == 422
    )
    assert (
        client.post(base, json={"name": "x", "quantity_milli": 0, "amount": 1}).status_code == 422
    )
    assert (
        client.post(base, json={"name": "x", "quantity_milli": 1000, "amount": 0}).status_code
        == 422
    )
    assert (
        client.post(
            base,
            json={"name": "x", "quantity_milli": 1000, "amount": 10_000_000_01},
        ).status_code
        == 422
    )

    item_id = client.get(f"/api/groups/{group.id}/receipts/{receipt.id}").json()["items"][0]["id"]
    too_many = [
        {"target": "PARTICIPANT", "participant_id": "ghost", "quantity_milli": 0}
        for _ in range(101)
    ]
    assert (
        client.put(
            f"{base}/{item_id}/portions",
            json={"portions": too_many},
        ).status_code
        == 422
    )


def test_configured_item_limits(make_client, session: Session):
    client = make_client(
        enable_receipt_items=True,
        max_receipt_item_name_length=3,
        max_receipt_item_amount=50,
        max_receipt_item_portions=1,
    )
    group, _people, receipt = _extracted_receipt(session)
    base = f"/api/groups/{group.id}/receipts/{receipt.id}/items"

    assert (
        client.post(base, json={"name": "four", "quantity_milli": 1, "amount": 1}).status_code
        == 422
    )
    assert (
        client.post(base, json={"name": "ok", "quantity_milli": 1, "amount": 51}).status_code == 422
    )

    item_id = client.get(f"/api/groups/{group.id}/receipts/{receipt.id}").json()["items"][0]["id"]
    too_many = [
        {"target": "SHARED", "quantity_milli": 0},
        {"target": "SHARED", "quantity_milli": 0},
    ]
    assert client.put(f"{base}/{item_id}/portions", json={"portions": too_many}).status_code == 422


def test_upload_receipt_image(make_client, session, tmp_path):
    client = make_client(enable_receipt_extract=True, upload_dir=str(tmp_path))
    group, _people = make_group(session)

    response = client.post(
        f"/api/groups/{group.id}/receipts/upload",
        files={"file": ("receipt.png", b"\x89PNG\r\n\x1a\nexample", "image/png")},
        data={"width": "800", "height": "600"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["width"] == 800
    assert body["height"] == 600
    assert body["url"].startswith(f"/api/groups/{group.id}/receipts/images/")
    assert list((tmp_path / "receipts").rglob("*.png"))

    image = client.get(body["url"])
    assert image.status_code == 200
    assert image.content.startswith(b"\x89PNG")
    assert image.headers["content-type"].startswith("image/png")

    assert (
        client.post(
            f"/api/groups/{group.id}/receipts/upload",
            files={"file": ("x.txt", b"hello", "text/plain")},
        ).status_code
        == 422
    )

    tiny = make_client(enable_receipt_extract=True, upload_dir=str(tmp_path), max_upload_bytes=3)
    assert (
        tiny.post(
            f"/api/groups/{group.id}/receipts/upload",
            files={"file": ("x.png", b"1234", "image/png")},
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/api/groups/missing/receipts/upload",
            files={"file": ("x.png", b"\x89PNG", "image/png")},
        ).status_code
        == 404
    )


def test_document_upload(make_client, session, tmp_path):
    client = make_client(enable_expense_documents=True, upload_dir=str(tmp_path))
    group, people = make_group(session)
    expense = make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1)],
        amount=1000,
    )
    upload = client.post(
        f"/api/groups/{group.id}/expenses/{expense.id}/documents",
        files={"file": ("receipt.png", b"\x89PNG\r\n\x1a\nexample", "image/png")},
    )
    assert upload.status_code == 201, upload.text
    document = upload.json()
    assert document["url"].endswith(f"/documents/{document['id']}")
    download = client.get(
        f"/api/groups/{group.id}/expenses/{expense.id}/documents/{document['id']}"
    )
    assert download.status_code == 200
    assert download.content.startswith(b"\x89PNG")


def test_receipt_image_reads_are_scoped_to_group(make_client, session, tmp_path):
    client = make_client(enable_receipt_extract=True, upload_dir=str(tmp_path))
    group, _people = make_group(session)
    other, _other_people = make_group(session, name="Other")

    upload = client.post(
        f"/api/groups/{group.id}/receipts/upload",
        files={"file": ("receipt.png", b"\x89PNG\r\n\x1a\nexample", "image/png")},
    )
    assert upload.status_code == 201, upload.text
    image_id = upload.json()["url"].rsplit("/", 1)[-1]

    # The owning group can read it.
    same = client.get(f"/api/groups/{group.id}/receipts/images/{image_id}")
    assert same.status_code == 200, same.text

    # Knowing the id is not enough to read it through another group.
    cross = client.get(f"/api/groups/{other.id}/receipts/images/{image_id}")
    assert cross.status_code == 422, cross.text


def test_legacy_receipt_image_is_readable_only_for_owning_group(make_client, session, tmp_path):
    client = make_client(enable_receipt_extract=True, upload_dir=str(tmp_path))
    group, _people = make_group(session)
    other, _other_people = make_group(session, name="Other")
    # Simulate an image stored before group-scoped keys were introduced.
    LocalBlobStorage(tmp_path).save("receipts/img_legacy.png", b"\x89PNG legacy")
    make_receipt(
        session,
        group=group,
        items=[{"name": "Legacy", "quantity_milli": 1000, "amount": 100}],
        image_url=f"/api/groups/{group.id}/receipts/images/img_legacy",
    )

    same = client.get(f"/api/groups/{group.id}/receipts/images/img_legacy")
    assert same.status_code == 200, same.text
    assert same.content == b"\x89PNG legacy"

    cross = client.get(f"/api/groups/{other.id}/receipts/images/img_legacy")
    assert cross.status_code == 422, cross.text


def test_document_downloads_and_ai_reads_are_scoped(make_client, session, tmp_path):
    client = make_client(enable_expense_documents=True, upload_dir=str(tmp_path))
    group, people = make_group(session)
    other, other_people = make_group(session, name="Other")
    expense = make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1)],
        amount=1000,
    )
    other_expense = make_expense(
        session,
        group=other,
        paid_by=other_people["Alice"],
        paid_for=[(other_people["Alice"], 1)],
        amount=1000,
    )
    upload = client.post(
        f"/api/groups/{group.id}/expenses/{expense.id}/documents",
        files={"file": ("receipt.png", b"\x89PNG\r\n\x1a\nexample", "image/png")},
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["id"]

    same = client.get(f"/api/groups/{group.id}/expenses/{expense.id}/documents/{document_id}")
    assert same.status_code == 200, same.text

    cross = client.get(
        f"/api/groups/{other.id}/expenses/{other_expense.id}/documents/{document_id}"
    )
    assert cross.status_code == 404, cross.text

    settings = _settings(upload_dir=str(tmp_path))
    storage = LocalBlobStorage(tmp_path)
    with pytest.raises(InvalidInputError):
        uploads_service.resolve_image_for_ai(
            session,
            storage,
            settings,
            group_id=other.id,
            image_url=(
                f"/api/groups/{other.id}/expenses/{other_expense.id}/documents/{document_id}"
            ),
        )
    inline = uploads_service.resolve_image_for_ai(
        session,
        storage,
        settings,
        group_id=group.id,
        image_url=f"/api/groups/{group.id}/expenses/{expense.id}/documents/{document_id}",
    )
    assert inline.startswith("data:image/png;base64,")


def test_document_routes_require_feature_flag(make_client, session, tmp_path):
    client = make_client(upload_dir=str(tmp_path))
    group, people = make_group(session)
    expense = make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1)],
        amount=1000,
    )
    response = client.post(
        f"/api/groups/{group.id}/expenses/{expense.id}/documents",
        files={"file": ("receipt.png", b"\x89PNG", "image/png")},
    )
    assert response.status_code == 403, response.text


def test_public_upload_url():
    storage = S3BlobStorage(
        bucket="bucket",
        region="eu-central-1",
        access_key="key",
        secret_key="secret",
        public_url="https://files.example.com/",
    )
    assert (
        storage.public_url("folder/document-1.jpg")
        == "https://files.example.com/folder/document-1.jpg"
    )
    local = LocalBlobStorage("/tmp/uploads")
    assert local.public_url("folder/document-1.jpg") is None


def test_build_storage_selects_backend(tmp_path):
    local = build_storage(Settings(_env_file=None, upload_dir=str(tmp_path)))
    assert isinstance(local, LocalBlobStorage)

    remote = build_storage(
        Settings(
            _env_file=None,
            s3_upload_key="key",
            s3_upload_secret="secret",
            s3_upload_bucket="bucket",
            s3_upload_region="auto",
            s3_upload_endpoint="https://minio.example.com",
        )
    )
    assert isinstance(remote, S3BlobStorage)
    assert remote.public_url("documents/file.png") is None


def test_s3_storage_round_trip_and_signing():
    import httpx

    state: dict[str, bytes] = {}
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            {
                "method": request.method,
                "url": str(request.url),
                "auth": request.headers.get("authorization"),
                "content_type": request.headers.get("content-type"),
            }
        )
        if request.method == "PUT":
            state[str(request.url)] = request.content
            return httpx.Response(200)
        if request.method == "HEAD":
            return httpx.Response(200 if str(request.url) in state else 404)
        if request.method == "GET":
            if str(request.url) not in state:
                return httpx.Response(404)
            return httpx.Response(200, content=state[str(request.url)])
        if request.method == "DELETE":
            state.pop(str(request.url), None)
            return httpx.Response(204)
        return httpx.Response(405)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    storage = S3BlobStorage(
        bucket="bucket",
        region="eu-central-1",
        access_key="key",
        secret_key="secret",
        endpoint="https://minio.example.com",
        http_client=client,
    )
    storage.save("documents/file.png", b"payload", content_type="image/png")
    assert storage.exists("documents/file.png")
    assert storage.read("documents/file.png") == b"payload"
    storage.delete("documents/file.png")
    assert not storage.exists("documents/file.png")

    put = requests[0]
    assert put["method"] == "PUT"
    assert put["url"] == "https://minio.example.com/bucket/documents/file.png"
    assert put["content_type"] == "image/png"
    assert put["auth"].startswith("AWS4-HMAC-SHA256 Credential=key/")
    assert "SignedHeaders=host;x-amz-content-sha256;x-amz-date" in put["auth"]


def test_uploaded_image_url():
    settings = Settings(
        _env_file=None,
        base_url="https://app.example.com",
        s3_upload_endpoint="https://accountid.r2.cloudflarestorage.com",
        s3_public_url="https://files.example.com",
    )
    assert uploads_service.is_allowed_upload_url(
        settings,
        "https://files.example.com/document-1.jpg",
    )
    assert not uploads_service.is_allowed_upload_url(
        settings,
        "https://accountid.r2.cloudflarestorage.com/bucket/document-1.jpg",
    )
    assert not uploads_service.is_allowed_upload_url(
        settings,
        "https://evil.example.com/document-1.jpg",
    )
    assert uploads_service.is_allowed_upload_url(
        settings,
        "/api/groups/grp/receipts/images/img.png",
    )
    assert not uploads_service.is_allowed_upload_url(settings, "//evil.example.com/x")
    assert not uploads_service.is_allowed_upload_url(settings, "ftp://files.example.com/x")
    assert not uploads_service.is_allowed_upload_url(settings, "data:image/png;base64,xx")

    endpoint = Settings(_env_file=None, s3_upload_endpoint="https://minio.example.com:9000")
    assert uploads_service.is_allowed_upload_url(
        endpoint,
        "https://minio.example.com:9000/bucket/receipt.jpg",
    )
    assert uploads_service.is_allowed_upload_url(
        endpoint,
        "http://minio.example.com/bucket/receipt.jpg",
    )
    assert not uploads_service.is_allowed_upload_url(
        endpoint,
        "https://minio.example.com.evil.com/receipt.jpg",
    )

    aws = Settings(
        _env_file=None,
        s3_upload_bucket="my-bucket",
        s3_upload_region="eu-central-1",
    )
    assert uploads_service.is_allowed_upload_url(
        aws,
        "https://my-bucket.s3.eu-central-1.amazonaws.com/receipts/1.png",
    )
    assert not uploads_service.is_allowed_upload_url(
        aws,
        "https://my-bucket.s3.us-east-1.amazonaws.com/receipts/1.png",
    )

    empty = Settings(_env_file=None)
    assert not uploads_service.is_allowed_upload_url(
        empty,
        "https://minio.example.com/bucket/receipt.jpg",
    )


@pytest.mark.parametrize(
    ("image_url", "expected"),
    [
        ("https://uploads.example.com/receipt.jpg", True),
        ("/api/groups/g1/expenses/e1/documents/d1", True),
        ("/api/groups/g1/receipts/images/i1", True),
        ("/api/health", False),
    ],
)
def test_relative_upload_routes(image_url, expected):
    settings = Settings(_env_file=None, s3_public_url="https://uploads.example.com")
    assert uploads_service.is_allowed_upload_url(settings, image_url) is expected


def test_link_cross_group_is_rejected(make_client, session: Session):
    client = make_client(enable_receipt_items=True)
    group, people, receipt = _extracted_receipt(session)
    other_group, other_people = make_group(session, name="Other")
    other_expense = make_expense(
        session,
        group=other_group,
        paid_by=other_people["Alice"],
        paid_for=[(other_people["Alice"], 1)],
        amount=1000,
    )
    response = client.post(
        f"/api/groups/{group.id}/receipts/{receipt.id}/link",
        json={"expense_id": other_expense.id},
    )
    assert response.status_code == 404
    assert people["Alice"].id != other_people["Alice"].id
