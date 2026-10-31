"""Stage 5D tests: OpenAPI snapshot and route contract completeness."""

from __future__ import annotations

import json
from pathlib import Path

from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "docs" / "openapi.json"

NO_BODY_POST_PATHS = {
    "/api/auth/refresh",
    "/api/auth/logout",
    "/api/groups/{group_id}/access",
    "/api/groups/{group_id}/attachments/{attachment_id}/extract-total",
}
NO_RESPONSE_SCHEMA_PATHS = {
    "/api/groups/{group_id}/expenses/export.csv",
    "/api/groups/{group_id}/expenses/export.json",
    "/api/groups/{group_id}/attachments/{attachment_id}/file",
    "/api/groups/{group_id}/attachments/{attachment_id}/thumbnail",
    "/api/auth/oauth/{provider}/start",
    "/api/auth/oauth/{provider}/callback",
}

REQUIRED_PATHS = {
    "/api/groups",
    "/api/groups/{group_id}",
    "/api/groups/{group_id}/details",
    "/api/groups/{group_id}/participants",
    "/api/groups/{group_id}/participants/{participant_id}",
    "/api/groups/sync",
    "/api/groups/{group_id}/access",
    "/api/groups/{group_id}/membership",
    "/api/groups/{group_id}/expenses",
    "/api/groups/{group_id}/expenses/{expense_id}",
    "/api/groups/{group_id}/expenses/export.csv",
    "/api/groups/{group_id}/expenses/export.json",
    "/api/groups/{group_id}/balances",
    "/api/balances",
    "/api/groups/{group_id}/stats",
    "/api/groups/{group_id}/stats/categories/{category_id}/expenses",
    "/api/groups/{group_id}/stats/months/{month}/expenses",
    "/api/groups/{group_id}/activities",
    "/api/categories",
    "/api/features",
    "/api/groups/{group_id}/attachments",
    "/api/groups/{group_id}/attachments/{attachment_id}",
    "/api/groups/{group_id}/attachments/{attachment_id}/extract-total",
    "/api/groups/{group_id}/attachments/{attachment_id}/extract-items",
    "/api/groups/{group_id}/attachments/{attachment_id}/receipt",
    "/api/groups/{group_id}/attachments/{attachment_id}/items",
    "/api/groups/{group_id}/attachments/{attachment_id}/items/{item_id}",
    "/api/groups/{group_id}/attachments/{attachment_id}/items/{item_id}/portions",
    "/api/groups/{group_id}/attachments/{attachment_id}/opt-outs/{participant_id}",
    "/api/groups/{group_id}/attachments/{attachment_id}/apply",
    "/api/ai/categories/infer",
}


def test_openapi_snapshot_is_current():
    spec = create_app().openapi()
    assert SNAPSHOT.exists(), (
        "docs/openapi.json is missing; regenerate it with "
        "`backend/.venv/bin/python backend/scripts/export_openapi.py`"
    )
    assert json.loads(SNAPSHOT.read_text()) == spec


def test_every_route_has_request_and_response_schemas_where_applicable():
    spec = create_app().openapi()
    operation_ids: set[str] = set()

    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            label = f"{method.upper()} {path}"
            assert operation.get("tags"), f"{label} has no tag"
            operation_id = operation.get("operationId")
            assert operation_id, f"{label} has no operationId"
            assert operation_id not in operation_ids, f"duplicate operationId {operation_id}"
            operation_ids.add(operation_id)

            responses = operation["responses"]
            success = [
                (code, response)
                for code, response in responses.items()
                if code.startswith("2") or code.startswith("3")
            ]
            assert success, f"{label} has no success response"

            for code, response in success:
                if code in {"204", "302"} or path in NO_RESPONSE_SCHEMA_PATHS:
                    continue
                content = response.get("content", {})
                if not content:
                    continue
                assert any(schema.get("schema") for schema in content.values()), (
                    f"{label} {code} has content but no schema"
                )

            if method.lower() in {"post", "patch", "put"} and path not in NO_BODY_POST_PATHS:
                body = operation.get("requestBody")
                assert body is not None, f"{label} has no requestBody"
                assert any(media.get("schema") for media in body.get("content", {}).values()), (
                    f"{label} requestBody has no schema"
                )

    missing = REQUIRED_PATHS - set(spec["paths"])
    assert not missing, f"missing API paths: {sorted(missing)}"
