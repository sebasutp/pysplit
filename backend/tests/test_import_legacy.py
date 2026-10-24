"""Stage 2 tests: migrations, schema constraints and legacy import integrity."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select

from alembic import command
from app.core.config import get_settings
from app.models import (
    Activity,
    Category,
    Expense,
    ExpenseDocument,
    ExpensePaidFor,
    Group,
    ImportRun,
    Participant,
    Receipt,
    User,
    UserGroup,
)
from scripts.legacy_importer import (
    ImportErrorBase,
    SourceIntegrityError,
    SourceUnreadableError,
    TargetNotEmptyError,
    file_checksum,
    import_database,
    parse_bool,
    parse_datetime,
    parse_decimal,
)
from scripts.verify_import import verify

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
FIXTURE_DB = BACKEND / "tests" / "fixtures" / "legacy" / "legacy_fixture.db"
GOLDEN_DIR = ROOT / "shared" / "fixtures" / "legacy"
PRIMARY_DB = ROOT / "spliit" / "spliit-data" / "spliit.db"
LARGE_DB = ROOT / "spliit" / "spliit.db"

TARGET_TABLES = {
    "groups",
    "participants",
    "categories",
    "expenses",
    "expense_paid_for",
    "expense_documents",
    "activities",
    "recurring_expense_links",
    "users",
    "accounts",
    "user_groups",
    "receipts",
    "receipt_items",
    "receipt_item_portions",
    "receipt_opt_outs",
    "sync_changes",
    "sync_operations",
    "import_runs",
}


def count(db_path: Path, table: str) -> int:
    connection = sqlite3.connect(db_path)
    try:
        return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    finally:
        connection.close()


@pytest.fixture()
def imported(tmp_path: Path) -> tuple[Path, dict]:
    target = tmp_path / "imported.db"
    result = import_database(FIXTURE_DB, target)
    return target, result


# ---------------------------------------------------------------------------
# Value parsing
# ---------------------------------------------------------------------------


def test_parse_datetime_preserves_microseconds_and_normalises_to_utc():
    parsed = parse_datetime("2026-09-03T11:23:49.573123+02:00")
    assert parsed == datetime(2026, 9, 3, 9, 23, 49, 573123, tzinfo=UTC)
    assert parsed.microsecond == 573123
    assert parse_datetime("2026-09-03T11:23:49.573Z") == datetime(
        2026, 9, 3, 11, 23, 49, 573000, tzinfo=UTC
    )
    assert parse_datetime("2026-09-03 11:23:49.573") == datetime(
        2026, 9, 3, 11, 23, 49, 573000, tzinfo=UTC
    )
    assert parse_datetime(None) is None
    assert parse_datetime("") is None
    with pytest.raises(SourceIntegrityError):
        parse_datetime("not-a-date")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, False),
        (1, True),
        ("0", False),
        ("1", True),
        ("true", True),
        ("false", False),
        (None, False),
    ],
)
def test_parse_bool_handles_prisma_representations(raw, expected):
    assert parse_bool(raw) is expected
    assert isinstance(parse_bool(raw), bool)


def test_parse_bool_rejects_unknown_values():
    with pytest.raises(SourceIntegrityError):
        parse_bool(2)


def test_parse_decimal_never_uses_float():
    assert parse_decimal("1.0812345678901234") == Decimal("1.0812345678901234")
    assert parse_decimal(0.5) == Decimal("0.5")
    assert parse_decimal("") is None
    assert parse_decimal(None) is None
    with pytest.raises(SourceIntegrityError):
        parse_decimal("not-a-decimal")


# ---------------------------------------------------------------------------
# Import behaviour
# ---------------------------------------------------------------------------


def test_import_creates_all_tables_and_every_row(imported):
    target, result = imported
    assert result["status"] == "imported"
    assert result["seeded_categories"] == 40
    expected = {
        "groups": 2,
        "participants": 4,
        "categories": 44,
        "expenses": 9,
        "expense_paid_for": 20,
        "expense_documents": 2,
        "activities": 3,
        "recurring_expense_links": 2,
        "users": 2,
        "accounts": 2,
        "user_groups": 3,
        "receipts": 2,
        "receipt_items": 3,
        "receipt_item_portions": 4,
        "receipt_opt_outs": 1,
    }
    for table, expected_count in expected.items():
        assert count(target, table) == expected_count, table
    assert count(target, "sync_changes") == 0
    assert count(target, "sync_operations") == 0
    assert count(target, "import_runs") == 1

    connection = sqlite3.connect(target)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    finally:
        connection.close()
    assert tables >= TARGET_TABLES
    assert "Session" not in tables
    assert "VerificationToken" not in tables


def test_import_preserves_legacy_ids_and_never_imports_sessions(imported):
    target, _ = imported
    connection = sqlite3.connect(target)
    try:
        group_ids = {row[0] for row in connection.execute("SELECT id FROM groups")}
        assert group_ids == {"group-1", "group-2"}
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name LIKE '%session%'"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name LIKE '%verification%'"
            ).fetchone()[0]
            == 0
        )
    finally:
        connection.close()


def test_import_preserves_timestamps_booleans_and_decimals(imported):
    target, _ = imported
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    try:
        even = connection.execute("SELECT * FROM expenses WHERE id = 'exp-even'").fetchone()
        reimbursement = connection.execute(
            "SELECT * FROM expenses WHERE id = 'exp-reimbursement'"
        ).fetchone()
        float_rate = connection.execute(
            "SELECT * FROM expenses WHERE id = 'exp-float-decimal'"
        ).fetchone()
        group = connection.execute("SELECT * FROM groups WHERE id = 'group-1'").fetchone()
        user_group = connection.execute(
            "SELECT * FROM user_groups WHERE user_id = 'user-admin' AND group_id = 'group-1'"
        ).fetchone()
    finally:
        connection.close()

    assert even["expense_date"] == "2026-03-01 10:11:12.345678"
    assert even["created_at"] == "2026-03-01 10:11:12.345678"
    assert even["is_reimbursement"] == 0
    assert even["recurrence_rule"] == "NONE"
    assert reimbursement["is_reimbursement"] == 1
    assert reimbursement["conversion_rate"] == "1.0812345678901234"
    assert reimbursement["original_amount"] == 2600
    assert float_rate["conversion_rate"] == "0.5"
    assert group["created_at"] == "2026-01-02 03:04:05.678000"
    assert group["currency_code"] == "EUR"
    assert user_group["is_starred"] == 1
    assert user_group["is_archived"] == 0


def test_import_preserves_orphan_documents_and_activities(imported):
    target, _ = imported
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    try:
        orphan_doc = connection.execute(
            "SELECT * FROM expense_documents WHERE id = 'doc-orphan'"
        ).fetchone()
        orphan_activity = connection.execute(
            "SELECT * FROM activities WHERE id = 'act-delete'"
        ).fetchone()
        closed_link = connection.execute(
            "SELECT * FROM recurring_expense_links WHERE id = 'link-closed'"
        ).fetchone()
    finally:
        connection.close()

    assert orphan_doc["expense_id"] is None
    assert orphan_activity["expense_id"] == "exp-deleted-long-ago"
    assert closed_link["next_expense_created_at"] == "2026-02-28 00:00:00.000000"
    assert closed_link["next_expense_date"] == "2026-02-28 00:00:00.000000"


def test_import_rolls_back_completely_when_a_row_is_invalid(tmp_path: Path):
    source = tmp_path / "broken.db"
    source.write_bytes(FIXTURE_DB.read_bytes())
    connection = sqlite3.connect(source)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "UPDATE ExpensePaidFor SET participantId = 'missing' "
            "WHERE expenseId = 'exp-even' AND participantId = 'p1'"
        )
        connection.commit()
    finally:
        connection.close()

    target = tmp_path / "rollback.db"
    with pytest.raises(IntegrityError):
        import_database(source, target)
    # DDL remains, but no rows and no audit row: the retry starts clean.
    assert count(target, "groups") == 0
    assert count(target, "expenses") == 0
    assert count(target, "import_runs") == 0

    assert import_database(FIXTURE_DB, target, reset=True)["status"] == "imported"
    assert count(target, "groups") == 2


def test_import_seeds_all_default_categories_when_source_is_partial(imported):
    target, _ = imported
    connection = sqlite3.connect(target)
    try:
        rows = connection.execute(
            "SELECT id, grouping, name FROM categories ORDER BY id"
        ).fetchall()
    finally:
        connection.close()
    assert len(rows) == 44
    assert rows[0] == (0, "Uncategorized", "General")
    assert rows[7] == (7, "Food and Drink", "Food and Drink")
    assert rows[43] == (43, "Life", "Donation")


def test_import_writes_import_run_with_checksum_counts_and_duration(imported):
    target, result = imported
    with Session(create_engine(f"sqlite:///{target}")) as session:
        runs = session.exec(select(ImportRun)).all()
        assert len(runs) == 1
        run = runs[0]
        assert run.status == "completed"
        assert run.source_checksum == file_checksum(FIXTURE_DB)
        assert run.source_checksum == result["checksum"]
        assert run.duration_ms is not None and run.duration_ms >= 0
        assert run.finished_at is not None
        assert '"seeded_categories": 40' in run.counts_json
        assert run.error is None


def test_import_is_idempotent_for_same_source(imported):
    target, first = imported
    second = import_database(FIXTURE_DB, target)
    assert second["status"] == "skipped"
    assert second["import_run_id"] == first["import_run_id"]
    assert count(target, "import_runs") == 1
    assert count(target, "groups") == 2


def test_import_refuses_non_empty_target_without_reset(imported, tmp_path: Path):
    target, _ = imported
    # Remove the audit row so the checksum shortcut cannot apply.
    connection = sqlite3.connect(target)
    try:
        connection.execute("DELETE FROM import_runs")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(TargetNotEmptyError):
        import_database(FIXTURE_DB, target)


def test_import_reset_replaces_existing_target(imported):
    target, _ = imported
    connection = sqlite3.connect(target)
    try:
        connection.execute(
            "INSERT INTO groups (id, name, information, currency, currency_code,"
            " created_at, updated_at, version, deleted_at) VALUES"
            " ('junk', 'junk', NULL, '$', NULL,"
            " '2026-01-01 00:00:00.000000', '2026-01-01 00:00:00.000000', 1, NULL)"
        )
        connection.commit()
    finally:
        connection.close()
    assert count(target, "groups") == 3

    result = import_database(FIXTURE_DB, target, reset=True)
    assert result["status"] == "imported"
    assert count(target, "groups") == 2
    assert count(target, "import_runs") == 1


def test_import_does_not_modify_source(tmp_path: Path):
    before = hashlib.sha256(FIXTURE_DB.read_bytes()).hexdigest()
    import_database(FIXTURE_DB, tmp_path / "copy.db")
    assert file_checksum(FIXTURE_DB) == before


def test_import_rejects_same_source_and_target(tmp_path: Path):
    with pytest.raises(ImportErrorBase):
        import_database(FIXTURE_DB, FIXTURE_DB)


def test_import_rejects_missing_source(tmp_path: Path):
    with pytest.raises(SourceUnreadableError):
        import_database(tmp_path / "missing.db", tmp_path / "new.db")


def test_import_rejects_database_without_application_tables(tmp_path: Path):
    source = tmp_path / "empty.db"
    sqlite3.connect(source).close()
    with pytest.raises(SourceUnreadableError):
        import_database(source, tmp_path / "new.db")


# ---------------------------------------------------------------------------
# Schema constraints (metadata-created database)
# ---------------------------------------------------------------------------


@pytest.fixture()
def schema_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schema.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session, engine


def _seed_minimal(session: Session) -> None:
    session.add(Group(id="g", name="G", currency="$", currency_code=None))
    session.add(Category(id=0, grouping="Uncategorized", name="General"))
    session.add(Participant(id="p1", name="P1", group_id="g"))
    session.add(Participant(id="p2", name="P2", group_id="g"))
    session.add(User(id="u", email="u@example.com"))
    session.commit()
    session.add(Expense(id="e", group_id="g", title="E", amount=100, paid_by_id="p1"))
    session.commit()
    session.add(ExpensePaidFor(expense_id="e", participant_id="p1", shares=1))
    session.add(UserGroup(user_id="u", group_id="g"))
    session.commit()


def test_composite_primary_keys_reject_duplicates(schema_session):
    session, engine = schema_session
    _seed_minimal(session)
    session.add(ExpensePaidFor(expense_id="e", participant_id="p1", shares=2))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.add(UserGroup(user_id="u", group_id="g"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    engine.dispose()


def test_receipt_unique_constraints(schema_session):
    session, engine = schema_session
    _seed_minimal(session)
    session.add(Receipt(id="r1", group_id="g", image_url="https://x/1.jpg"))
    session.add(Receipt(id="r2", group_id="g", image_url="https://x/1.jpg"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.add(Receipt(id="r1", group_id="g", image_url="https://x/1.jpg", expense_id="e"))
    session.add(Receipt(id="r2", group_id="g", image_url="https://x/2.jpg", expense_id="e"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    engine.dispose()


def test_expense_document_orphan_and_set_null(schema_session):
    session, engine = schema_session
    _seed_minimal(session)
    session.add(ExpenseDocument(id="d", url="u", width=1, height=1))
    session.commit()

    document = session.get(ExpenseDocument, "d")
    assert document is not None and document.expense_id is None

    session.add(ExpenseDocument(id="d2", url="u2", width=1, height=1, expense_id="e"))
    session.commit()
    session.delete(session.get(Expense, "e"))
    session.commit()
    document = session.get(ExpenseDocument, "d2")
    assert document is not None and document.expense_id is None
    engine.dispose()


def test_group_delete_cascades(schema_session):
    session, engine = schema_session
    _seed_minimal(session)
    session.delete(session.get(Group, "g"))
    session.commit()
    assert session.exec(select(Participant)).all() == []
    assert session.exec(select(Expense)).all() == []
    assert session.exec(select(ExpensePaidFor)).all() == []
    assert session.exec(select(UserGroup)).all() == []
    engine.dispose()


def test_activity_has_no_foreign_key_to_expense(schema_session):
    session, engine = schema_session
    _seed_minimal(session)
    session.add(
        Activity(
            id="a",
            group_id="g",
            activity_type="DELETE_EXPENSE",
            expense_id="missing-expense",
            participant_id="missing-participant",
        )
    )
    session.commit()
    activity = session.get(Activity, "a")
    assert activity is not None
    assert activity.expense_id == "missing-expense"
    engine.dispose()


def test_custom_types_round_trip(schema_session):
    session, engine = schema_session
    _seed_minimal(session)
    expense = session.get(Expense, "e")
    assert expense is not None
    expense.expense_date = datetime(2026, 5, 6, 7, 8, 9, 123456, tzinfo=UTC)
    expense.conversion_rate = Decimal("1.2300000000000001")
    session.add(expense)
    session.commit()
    session.expire_all()
    replayed = session.get(Expense, "e")
    assert replayed is not None
    assert replayed.expense_date == datetime(2026, 5, 6, 7, 8, 9, 123456, tzinfo=UTC)
    assert replayed.conversion_rate == Decimal("1.2300000000000001")
    assert isinstance(replayed.conversion_rate, Decimal)
    engine.dispose()


# ---------------------------------------------------------------------------
# Migration and metadata consistency
# ---------------------------------------------------------------------------


def test_migration_upgrade_downgrade_upgrade(tmp_path: Path, monkeypatch):
    database = tmp_path / "migrate.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")
    get_settings.cache_clear()
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    try:
        command.upgrade(config, "head")
        assert (
            set(inspect(create_engine(f"sqlite:///{database}")).get_table_names()) >= TARGET_TABLES
        )
        command.downgrade(config, "base")
        assert "groups" not in inspect(create_engine(f"sqlite:///{database}")).get_table_names()
        command.upgrade(config, "head")
        with sqlite3.connect(database) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        get_settings.cache_clear()


def test_metadata_and_migrations_produce_the_same_schema(tmp_path: Path, monkeypatch):
    database = tmp_path / "migrate-schema.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")
    get_settings.cache_clear()
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    try:
        command.upgrade(config, "head")
    finally:
        get_settings.cache_clear()

    metadata_db = tmp_path / "metadata-schema.db"
    engine = create_engine(f"sqlite:///{metadata_db}")
    SQLModel.metadata.create_all(engine)
    engine.dispose()

    def describe(path: Path) -> dict[str, tuple]:
        connection = sqlite3.connect(path)
        try:
            result = {}
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
                )
            ]
            for table in tables:
                columns = tuple(
                    (row[1], row[2], row[3], row[5])
                    for row in connection.execute(f'PRAGMA table_info("{table}")')
                )
                indexes = tuple(
                    sorted(
                        (row[1], row[2], row[3])
                        for row in connection.execute(f'PRAGMA index_list("{table}")')
                    )
                )
                result[table] = (columns, indexes)
            return result
        finally:
            connection.close()

    assert describe(database) == describe(metadata_db)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def test_verify_passes_for_fixture_with_reference_golden(imported):
    target, _ = imported
    summary = verify(FIXTURE_DB, target, GOLDEN_DIR, require_golden=True)
    assert summary["ok"], summary["problems"]
    assert summary["group_count"] == 2


def test_verify_detects_lost_or_changed_rows(imported):
    target, _ = imported
    connection = sqlite3.connect(target)
    try:
        connection.execute("UPDATE expenses SET amount = 1001 WHERE id = 'exp-even'")
        connection.execute("DELETE FROM receipt_opt_outs")
        connection.commit()
    finally:
        connection.close()
    summary = verify(FIXTURE_DB, target, GOLDEN_DIR, require_golden=True)
    assert not summary["ok"]
    joined = "\n".join(summary["problems"])
    assert "expenses" in joined
    assert "receipt_opt_outs" in joined


def test_verify_detects_timestamp_truncation(imported):
    target, _ = imported
    connection = sqlite3.connect(target)
    try:
        connection.execute(
            "UPDATE expenses SET expense_date = '2026-03-01 00:00:00.000000' WHERE id = 'exp-even'"
        )
        connection.commit()
    finally:
        connection.close()
    summary = verify(FIXTURE_DB, target, GOLDEN_DIR, require_golden=True)
    assert not summary["ok"]
    assert any("expenses" in problem for problem in summary["problems"])


def test_verify_requires_golden_when_requested(imported, tmp_path: Path):
    target, _ = imported
    summary = verify(FIXTURE_DB, target, tmp_path, require_golden=True)
    assert not summary["ok"]
    assert any("no reference golden" in problem for problem in summary["problems"])


def test_verify_falls_back_to_source_balances_without_golden(imported, tmp_path: Path):
    target, _ = imported
    summary = verify(FIXTURE_DB, target, tmp_path, require_golden=False)
    assert summary["ok"], summary["problems"]
    assert any("compared target to source" in check for check in summary["checks"])


# ---------------------------------------------------------------------------
# The two confirmed production fixture databases
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not PRIMARY_DB.exists(), reason="reference fixture database absent")
def test_import_primary_reference_database(tmp_path: Path):
    target = tmp_path / "primary.db"
    result = import_database(PRIMARY_DB, target)
    assert result["status"] == "imported"
    assert result["counts"]["groups"] == 6
    assert result["counts"]["expenses"] == 122
    assert result["counts"]["receipts"] == 1
    assert result["seeded_categories"] == 0
    summary = verify(PRIMARY_DB, target, GOLDEN_DIR, require_golden=True)
    assert summary["ok"], summary["problems"]


@pytest.mark.skipif(not LARGE_DB.exists(), reason="reference fixture database absent")
def test_import_large_reference_database(tmp_path: Path):
    target = tmp_path / "large.db"
    result = import_database(LARGE_DB, target)
    assert result["status"] == "imported"
    assert result["counts"]["groups"] == 296
    assert result["counts"]["expenses"] == 0
    assert result["seeded_categories"] == 44
    summary = verify(LARGE_DB, target, GOLDEN_DIR, require_golden=True)
    assert summary["ok"], summary["problems"]


# ---------------------------------------------------------------------------
# CLI smoke tests
# ---------------------------------------------------------------------------


def test_import_cli_smoke(tmp_path: Path):
    target = tmp_path / "cli.db"
    completed = subprocess.run(
        [
            sys.executable,
            str(BACKEND / "scripts" / "import_legacy_sqlite.py"),
            "--source",
            str(FIXTURE_DB),
            "--target",
            str(target),
            "--json",
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
    )
    assert completed.returncode == 0, completed.stderr
    assert '"status": "imported"' in completed.stdout
    assert target.exists()


def test_verify_cli_smoke(imported, tmp_path: Path):
    target, _ = imported
    completed = subprocess.run(
        [
            sys.executable,
            str(BACKEND / "scripts" / "verify_import.py"),
            "--old",
            str(FIXTURE_DB),
            "--new",
            str(target),
            "--golden-dir",
            str(GOLDEN_DIR),
            "--require-golden",
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
    )
    assert completed.returncode == 0, completed.stderr
    assert "PASS" in completed.stdout
