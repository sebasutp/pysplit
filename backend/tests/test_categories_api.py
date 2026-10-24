"""Stage 5C tests: seeded categories."""

from __future__ import annotations

from sqlmodel import Session, select

from app.models.category import Category


def test_list_categories(client, session: Session):
    first = client.get("/api/categories")
    assert first.status_code == 200
    body = first.json()
    assert body["total"] == 44
    assert body["limit"] == 200
    assert len(body["items"]) == 44
    assert body["items"][0] == {"id": 0, "grouping": "Uncategorized", "name": "General"}
    assert [item["id"] for item in body["items"]] == list(range(44))

    second = client.get("/api/categories")
    assert second.status_code == 200
    assert len(session.exec(select(Category)).all()) == 44

    paged = client.get("/api/categories", params={"limit": 5, "offset": 40}).json()
    assert paged["total"] == 44
    assert [item["id"] for item in paged["items"]] == [40, 41, 42, 43]
    assert client.get("/api/categories", params={"limit": 0}).status_code == 422


def test_categories_repairs_partial_table(client, session: Session):
    session.add(Category(id=0, grouping="Custom", name="Kept"))
    session.add(Category(id=100, grouping="Custom", name="Extra"))
    session.commit()

    body = client.get("/api/categories").json()
    assert body["total"] == 45
    assert body["items"][0]["name"] == "Kept"
    assert any(item["id"] == 100 for item in body["items"])
    assert any(item["id"] == 43 for item in body["items"])
