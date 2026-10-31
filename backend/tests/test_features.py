"""Stage 5D tests: runtime feature flags."""

from __future__ import annotations


def test_feature_flags_default_off(client):
    response = client.get("/api/features")
    assert response.status_code == 200
    assert response.json() == {"receipt_ai": False, "category_ai": False}


def test_feature_flags_reflect_settings(make_client):
    client = make_client(enable_receipt_ai=True, enable_category_extract=True)
    assert client.get("/api/features").json() == {
        "receipt_ai": True,
        "category_ai": True,
    }
