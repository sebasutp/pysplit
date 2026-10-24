"""Stage 5D tests: runtime feature flags."""

from __future__ import annotations


def test_feature_flags_default_off(client):
    response = client.get("/api/features")
    assert response.status_code == 200
    assert response.json() == {
        "receipt_extract": False,
        "receipt_items": False,
        "category_extract": False,
        "expense_documents": False,
    }


def test_feature_flags_reflect_settings(make_client):
    client = make_client(
        enable_receipt_extract=False,
        enable_receipt_items=True,
        enable_category_extract=True,
        enable_expense_documents=True,
    )
    assert client.get("/api/features").json() == {
        "receipt_extract": True,
        "receipt_items": True,
        "category_extract": True,
        "expense_documents": True,
    }
