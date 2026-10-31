"""Stage 5 architecture checks: routers stay HTTP-only and utils stay pure."""

from __future__ import annotations

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROUTERS = (
    "groups.py",
    "expenses.py",
    "attachments.py",
    "balances.py",
    "stats.py",
    "activities.py",
    "categories.py",
    "features.py",
    "health.py",
    "sync.py",
)
UTILS = (
    "shares.py",
    "balances.py",
    "totals.py",
    "recurrence.py",
    "currency.py",
    "dates.py",
    "receipt_split.py",
    "receipt_extraction.py",
)


def test_stage_five_routers_do_not_import_models_or_sql():
    for name in ROUTERS:
        source = (BACKEND / "app" / "api" / name).read_text()
        for forbidden in ("app.models", "sqlmodel", "sqlalchemy", "app.core.database"):
            assert forbidden not in source, f"{name} imports {forbidden}"


def test_domain_utils_are_pure():
    for name in UTILS:
        source = (BACKEND / "app" / "utils" / name).read_text()
        for forbidden in (
            "app.models",
            "sqlmodel",
            "sqlalchemy",
            "app.storage",
            "app.core.config",
            "fastapi",
            "httpx",
        ):
            assert forbidden not in source, f"utils/{name} imports {forbidden}"


def test_stage_five_specs_exist():
    for name in (
        "test_groups_api.py",
        "test_group_sync.py",
        "test_expenses_api.py",
        "test_recurrence.py",
        "test_balances_api.py",
        "test_stats_api.py",
        "test_activities_api.py",
        "test_categories_api.py",
        "test_exports.py",
        "test_openapi.py",
    ):
        assert (BACKEND / "tests" / name).is_file(), f"missing {name}"


def test_stage_six_sync_specs_exist():
    for name in ("test_sync.py", "test_sync_conflicts.py"):
        assert (BACKEND / "tests" / name).is_file(), f"missing {name}"


def test_stage_six_sync_router_does_not_import_models_or_sql():
    source = (BACKEND / "app" / "api" / "sync.py").read_text()
    for forbidden in ("app.models", "sqlmodel", "sqlalchemy", "app.core.database"):
        assert forbidden not in source, f"sync.py imports {forbidden}"


def test_stage_seven_specs_exist():
    for name in ("test_attachments.py", "test_ai.py", "test_receipt_apply.py"):
        assert (BACKEND / "tests" / name).is_file(), f"missing {name}"


def test_stage_eleven_sync_specs_exist():
    for name in ("test_group_sync.py", "test_groups_sync.py", "test_admin.py"):
        assert (BACKEND / "tests" / name).is_file(), f"missing {name}"


def test_stage_seven_attachment_router_is_http_only():
    source = (BACKEND / "app" / "api" / "attachments.py").read_text()
    for forbidden in ("app.models", "sqlmodel", "sqlalchemy", "app.core.database"):
        assert forbidden not in source, f"attachments.py imports {forbidden}"


def test_stage_seven_receipt_parsers_are_pure():
    for name in ("receipt_split.py", "receipt_extraction.py"):
        source = (BACKEND / "app" / "utils" / name).read_text()
        for forbidden in (
            "app.models",
            "sqlmodel",
            "sqlalchemy",
            "app.storage",
            "app.core.config",
            "fastapi",
            "httpx",
        ):
            assert forbidden not in source, f"utils/{name} imports {forbidden}"
