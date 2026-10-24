"""Helpers for importing the legacy Prisma/SQLite database.

This module lives outside ``app`` on purpose: it is migration tooling, not
runtime application code. The scripts are importable as ``scripts.*`` from the
backend root and also runnable directly.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel

import app.models  # noqa: F401  (registers every table on the metadata)
from app.core.categories import DEFAULT_CATEGORIES
from app.models.base import utc_now

# Source Prisma table -> target SQLModel table.
TABLE_MAP: dict[str, str] = {
    "Group": "groups",
    "Participant": "participants",
    "Category": "categories",
    "Expense": "expenses",
    "ExpensePaidFor": "expense_paid_for",
    "ExpenseDocument": "expense_documents",
    "Activity": "activities",
    "RecurringExpenseLink": "recurring_expense_links",
    "User": "users",
    "Account": "accounts",
    "UserGroup": "user_groups",
    "Receipt": "receipts",
    "ReceiptItem": "receipt_items",
    "ReceiptItemPortion": "receipt_item_portions",
    "ReceiptOptOut": "receipt_opt_outs",
}

# Deliberately not migrated: users log in again with the new flow.
SKIPPED_TABLES: tuple[str, ...] = ("Session", "VerificationToken")

REQUIRED_SOURCE_TABLES: tuple[str, ...] = (
    "Group",
    "Participant",
    "Category",
    "Expense",
    "ExpensePaidFor",
    "ExpenseDocument",
    "Activity",
    "RecurringExpenseLink",
    "User",
    "Account",
    "UserGroup",
    "Receipt",
    "ReceiptItem",
    "ReceiptItemPortion",
    "ReceiptOptOut",
)


class ImportErrorBase(RuntimeError):
    """Base class for import failures with a user-facing message."""


class SourceUnreadableError(ImportErrorBase):
    """The legacy database is missing or cannot be opened read-only."""


class TargetNotEmptyError(ImportErrorBase):
    """The target contains data and ``--reset`` was not supplied."""


class SourceIntegrityError(ImportErrorBase):
    """A source row cannot be represented without loss."""


def repository_root() -> Path:
    """Return the backend root for direct-script execution."""
    return Path(__file__).resolve().parents[1]


def ensure_import_path() -> None:
    """Allow ``python scripts/foo.py`` to import the ``app`` package."""
    root = str(repository_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def file_checksum(path: Path) -> str:
    """SHA-256 of the database file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_datetime(value: Any) -> datetime | None:
    """Parse a Prisma SQLite datetime without losing precision or the zone.

    Prisma writes ISO text such as ``2026-09-03T11:23:49.573+00:00``. Naive
    values are treated as UTC (SQLite has no zone); offsets are honoured and
    normalised to UTC.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise SourceIntegrityError(f"invalid datetime value: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_bool(value: Any) -> bool:
    """Interpret Prisma's 0/1 booleans without relying on truthiness."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        raise SourceIntegrityError(f"invalid boolean value: {value!r}")
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "t", "yes"}:
            return True
        if lowered in {"0", "false", "f", "no", ""}:
            return False
    raise SourceIntegrityError(f"invalid boolean value: {value!r}")


def parse_decimal(value: Any) -> Decimal | None:
    """Parse a Prisma decimal as an exact :class:`Decimal` (never a float)."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        # A float here means the legacy database stored a REAL. Convert via
        # repr so we at least do not add an extra binary rounding step.
        return Decimal(repr(value))
    text = str(value).strip()
    if text == "":
        return None
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise SourceIntegrityError(f"invalid decimal value: {value!r}") from exc


def parse_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SourceIntegrityError(f"invalid integer value: {value!r}") from exc


def parse_required_int(value: Any, default: int | None = None) -> int:
    parsed = parse_optional_int(value)
    if parsed is None:
        if default is None:
            raise SourceIntegrityError(f"missing integer value: {value!r}")
        return default
    return parsed


def parse_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def connect_read_only(path: Path) -> sqlite3.Connection:
    """Open the legacy database strictly read-only (no accidental writes)."""
    if not path.exists() or not path.is_file():
        raise SourceUnreadableError(f"source database not found: {path}")
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("SELECT 1 FROM sqlite_master LIMIT 1")
        return connection
    except sqlite3.Error as exc:
        raise SourceUnreadableError(f"cannot read source database: {path}") from exc


def source_table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


def ensure_source_tables(connection: sqlite3.Connection) -> None:
    present = source_table_names(connection)
    missing = [table for table in REQUIRED_SOURCE_TABLES if table not in present]
    if missing:
        raise SourceUnreadableError(
            "source database is missing application tables: " + ", ".join(missing)
        )


def make_target_engine(path: Path) -> Engine:
    """Create an engine with SQLite foreign keys and a busy timeout enabled."""
    engine = create_engine(
        f"sqlite:///{path.resolve().as_posix()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record) -> None:
        if not isinstance(dbapi_connection, sqlite3.Connection):
            return
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()

    return engine


def target_row_count(path: Path) -> int:
    """Count rows in all application tables of an existing target."""
    if not path.exists():
        return 0
    connection = sqlite3.connect(path)
    try:
        present = source_table_names(connection)
        total = 0
        for table in {
            *TABLE_MAP.values(),
            "sync_changes",
            "sync_operations",
            "import_runs",
        }:
            if table in present:
                total += connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        return total
    finally:
        connection.close()


def find_completed_run(path: Path, checksum: str) -> dict[str, Any] | None:
    """Return a completed ImportRun for this source checksum, if any."""
    if not path.exists():
        return None
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        present = source_table_names(connection)
        if "import_runs" not in present:
            return None
        row = connection.execute(
            """
            SELECT id, status, started_at, finished_at, duration_ms, counts_json
            FROM import_runs
            WHERE source_checksum = ? AND status = 'completed'
            ORDER BY finished_at DESC
            LIMIT 1
            """,
            (checksum,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def remove_target(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            candidate.unlink()


def read_source_counts(connection: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source_table in TABLE_MAP:
        counts[source_table] = connection.execute(
            f'SELECT COUNT(*) FROM "{source_table}"'
        ).fetchone()[0]
    for skipped in SKIPPED_TABLES:
        if skipped in source_table_names(connection):
            counts[f"skipped:{skipped}"] = connection.execute(
                f'SELECT COUNT(*) FROM "{skipped}"'
            ).fetchone()[0]
    return counts


def _rows(connection: sqlite3.Connection, table: str, columns: str) -> list[sqlite3.Row]:
    return connection.execute(f'SELECT {columns} FROM "{table}"').fetchall()


def _build_rows(
    connection: sqlite3.Connection, now: datetime
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    """Translate every legacy row into target-column dictionaries."""
    buckets: dict[str, list[dict[str, Any]]] = {target: [] for target in TABLE_MAP.values()}

    buckets["groups"] = [
        {
            "id": row["id"],
            "name": row["name"],
            "information": parse_str(row["information"]),
            "currency": row["currency"],
            "currency_code": parse_str(row["currencyCode"]),
            "created_at": parse_datetime(row["createdAt"]) or now,
            "updated_at": parse_datetime(row["createdAt"]) or now,
            "version": 1,
            "deleted_at": None,
        }
        for row in _rows(
            connection,
            "Group",
            "id, name, information, currency, currencyCode, createdAt",
        )
    ]

    buckets["participants"] = [
        {
            "id": row["id"],
            "name": row["name"],
            "group_id": row["groupId"],
            "updated_at": now,
            "version": 1,
            "deleted_at": None,
        }
        for row in _rows(connection, "Participant", "id, name, groupId")
    ]

    source_categories = _rows(connection, "Category", "id, grouping, name")
    seen_category_ids = {parse_required_int(row["id"]) for row in source_categories}
    category_rows = [
        {
            "id": parse_required_int(row["id"]),
            "grouping": row["grouping"],
            "name": row["name"],
            "updated_at": now,
            "version": 1,
            "deleted_at": None,
        }
        for row in source_categories
    ]
    seeded = 0
    for category_id, grouping, name in DEFAULT_CATEGORIES:
        if category_id not in seen_category_ids:
            category_rows.append(
                {
                    "id": category_id,
                    "grouping": grouping,
                    "name": name,
                    "updated_at": now,
                    "version": 1,
                    "deleted_at": None,
                }
            )
            seeded += 1
    buckets["categories"] = category_rows

    buckets["expenses"] = []
    for row in _rows(
        connection,
        "Expense",
        "id, groupId, expenseDate, title, categoryId, amount, originalAmount, "
        "originalCurrency, conversionRate, paidById, isReimbursement, splitMode, "
        "createdAt, notes, recurrenceRule, recurringExpenseLinkId",
    ):
        created_at = parse_datetime(row["createdAt"]) or now
        buckets["expenses"].append(
            {
                "id": row["id"],
                "group_id": row["groupId"],
                "expense_date": parse_datetime(row["expenseDate"]) or created_at,
                "title": row["title"],
                "category_id": parse_required_int(row["categoryId"], default=0),
                "amount": parse_required_int(row["amount"]),
                "original_amount": parse_optional_int(row["originalAmount"]),
                "original_currency": parse_str(row["originalCurrency"]),
                "conversion_rate": parse_decimal(row["conversionRate"]),
                "paid_by_id": row["paidById"],
                "is_reimbursement": parse_bool(row["isReimbursement"]),
                "split_mode": row["splitMode"] or "EVENLY",
                "created_at": created_at,
                "notes": parse_str(row["notes"]),
                "recurrence_rule": parse_str(row["recurrenceRule"]),
                "recurring_expense_link_id": parse_str(row["recurringExpenseLinkId"]),
                "updated_at": created_at,
                "version": 1,
                "deleted_at": None,
            }
        )

    buckets["expense_paid_for"] = [
        {
            "expense_id": row["expenseId"],
            "participant_id": row["participantId"],
            "shares": parse_required_int(row["shares"], default=1),
            "updated_at": now,
            "version": 1,
            "deleted_at": None,
        }
        for row in _rows(connection, "ExpensePaidFor", "expenseId, participantId, shares")
    ]

    buckets["expense_documents"] = [
        {
            "id": row["id"],
            "url": row["url"],
            "width": parse_required_int(row["width"]),
            "height": parse_required_int(row["height"]),
            "expense_id": parse_str(row["expenseId"]),
            "created_at": now,
            "updated_at": now,
            "version": 1,
            "deleted_at": None,
        }
        for row in _rows(connection, "ExpenseDocument", "id, url, width, height, expenseId")
    ]

    buckets["activities"] = []
    for row in _rows(
        connection,
        "Activity",
        "id, groupId, time, activityType, participantId, expenseId, data",
    ):
        activity_time = parse_datetime(row["time"]) or now
        buckets["activities"].append(
            {
                "id": row["id"],
                "group_id": row["groupId"],
                "time": activity_time,
                "activity_type": row["activityType"],
                "participant_id": parse_str(row["participantId"]),
                "expense_id": parse_str(row["expenseId"]),
                "data": parse_str(row["data"]),
                "updated_at": activity_time,
                "version": 1,
                "deleted_at": None,
            }
        )

    buckets["recurring_expense_links"] = []
    for row in _rows(
        connection,
        "RecurringExpenseLink",
        "id, groupId, currentFrameExpenseId, nextExpenseCreatedAt, nextExpenseDate",
    ):
        next_created = parse_datetime(row["nextExpenseCreatedAt"])
        buckets["recurring_expense_links"].append(
            {
                "id": row["id"],
                "group_id": row["groupId"],
                "current_frame_expense_id": row["currentFrameExpenseId"],
                "next_expense_created_at": next_created,
                "next_expense_date": parse_datetime(row["nextExpenseDate"]) or now,
                "updated_at": next_created or now,
                "version": 1,
                "deleted_at": None,
            }
        )

    buckets["users"] = []
    for row in _rows(
        connection,
        "User",
        "id, name, email, emailVerified, image, tier, createdAt, updatedAt",
    ):
        created_at = parse_datetime(row["createdAt"]) or now
        buckets["users"].append(
            {
                "id": row["id"],
                "name": parse_str(row["name"]),
                "email": parse_str(row["email"]),
                "email_verified": parse_datetime(row["emailVerified"]),
                "image": parse_str(row["image"]),
                "tier": row["tier"] or "sync_users",
                "created_at": created_at,
                "updated_at": parse_datetime(row["updatedAt"]) or created_at,
                "version": 1,
                "deleted_at": None,
            }
        )

    buckets["accounts"] = [
        {
            "id": row["id"],
            "user_id": row["userId"],
            "type": row["type"],
            "provider": row["provider"],
            "provider_account_id": row["providerAccountId"],
            "refresh_token": parse_str(row["refresh_token"]),
            "access_token": parse_str(row["access_token"]),
            "expires_at": parse_optional_int(row["expires_at"]),
            "token_type": parse_str(row["token_type"]),
            "scope": parse_str(row["scope"]),
            "id_token": parse_str(row["id_token"]),
            "session_state": parse_str(row["session_state"]),
        }
        for row in _rows(
            connection,
            "Account",
            "id, userId, type, provider, providerAccountId, refresh_token, "
            "access_token, expires_at, token_type, scope, id_token, session_state",
        )
    ]

    buckets["user_groups"] = []
    for row in _rows(connection, "UserGroup", "userId, groupId, isStarred, isArchived, createdAt"):
        created_at = parse_datetime(row["createdAt"]) or now
        buckets["user_groups"].append(
            {
                "user_id": row["userId"],
                "group_id": row["groupId"],
                "is_starred": parse_bool(row["isStarred"]),
                "is_archived": parse_bool(row["isArchived"]),
                "created_at": created_at,
                "updated_at": created_at,
                "version": 1,
                "deleted_at": None,
            }
        )

    buckets["receipts"] = []
    for row in _rows(
        connection,
        "Receipt",
        "id, groupId, imageUrl, imageWidth, imageHeight, status, rawExtraction, "
        "provider, model, merchant, receiptDate, currencyCode, total, expenseId, "
        "createdAt, updatedAt",
    ):
        created_at = parse_datetime(row["createdAt"]) or now
        buckets["receipts"].append(
            {
                "id": row["id"],
                "group_id": row["groupId"],
                "image_url": row["imageUrl"],
                "image_width": parse_optional_int(row["imageWidth"]),
                "image_height": parse_optional_int(row["imageHeight"]),
                "status": row["status"] or "PENDING",
                "raw_extraction": parse_str(row["rawExtraction"]),
                "provider": parse_str(row["provider"]),
                "model": parse_str(row["model"]),
                "merchant": parse_str(row["merchant"]),
                "receipt_date": parse_datetime(row["receiptDate"]),
                "currency_code": parse_str(row["currencyCode"]),
                "total": parse_optional_int(row["total"]),
                "expense_id": parse_str(row["expenseId"]),
                "created_at": created_at,
                "updated_at": parse_datetime(row["updatedAt"]) or created_at,
                "version": 1,
                "deleted_at": None,
            }
        )

    buckets["receipt_items"] = []
    for row in _rows(
        connection,
        "ReceiptItem",
        "id, receiptId, name, quantityMilli, unitPrice, amount, isShared, "
        "isAdjustment, position, createdAt, updatedAt",
    ):
        created_at = parse_datetime(row["createdAt"]) or now
        buckets["receipt_items"].append(
            {
                "id": row["id"],
                "receipt_id": row["receiptId"],
                "name": row["name"],
                "quantity_milli": parse_required_int(row["quantityMilli"], default=1000),
                "unit_price": parse_optional_int(row["unitPrice"]),
                "amount": parse_required_int(row["amount"]),
                "is_shared": parse_bool(row["isShared"]),
                "is_adjustment": parse_bool(row["isAdjustment"]),
                "position": parse_required_int(row["position"], default=0),
                "created_at": created_at,
                "updated_at": parse_datetime(row["updatedAt"]) or created_at,
                "version": 1,
                "deleted_at": None,
            }
        )

    buckets["receipt_item_portions"] = []
    for row in _rows(
        connection,
        "ReceiptItemPortion",
        "id, itemId, target, participantId, quantityMilli, createdAt, updatedAt",
    ):
        created_at = parse_datetime(row["createdAt"]) or now
        buckets["receipt_item_portions"].append(
            {
                "id": row["id"],
                "item_id": row["itemId"],
                "target": row["target"],
                "participant_id": parse_str(row["participantId"]),
                "quantity_milli": parse_required_int(row["quantityMilli"]),
                "created_at": created_at,
                "updated_at": parse_datetime(row["updatedAt"]) or created_at,
                "version": 1,
                "deleted_at": None,
            }
        )

    buckets["receipt_opt_outs"] = []
    for row in _rows(connection, "ReceiptOptOut", "id, receiptId, participantId, createdAt"):
        created_at = parse_datetime(row["createdAt"]) or now
        buckets["receipt_opt_outs"].append(
            {
                "id": row["id"],
                "receipt_id": row["receiptId"],
                "participant_id": row["participantId"],
                "created_at": created_at,
                "updated_at": created_at,
                "version": 1,
                "deleted_at": None,
            }
        )

    return buckets, seeded


def import_database(
    source: Path,
    target: Path,
    *,
    reset: bool = False,
) -> dict[str, Any]:
    """Import ``source`` into ``target`` atomically and idempotently.

    Returns a result dictionary with ``status`` (``imported`` or ``skipped``),
    counts, the source checksum and the ImportRun id.
    """
    source = source.resolve()
    target = target.resolve()
    if source == target:
        raise ImportErrorBase("source and target must be different files")
    if not source.exists() or not source.is_file():
        raise SourceUnreadableError(f"source database not found: {source}")

    checksum = file_checksum(source)

    # Refuse or short-circuit before opening the source for writing (it is
    # always read-only, but this makes the intent explicit).
    if target.exists() and not reset:
        existing = find_completed_run(target, checksum)
        if existing:
            return {
                "status": "skipped",
                "reason": "already imported (matching checksum)",
                "source": str(source),
                "target": str(target),
                "checksum": checksum,
                "import_run_id": existing["id"],
                "counts": {},
            }
        if target_row_count(target) > 0:
            raise TargetNotEmptyError(
                f"target database is not empty: {target}\nRe-run with --reset to replace it."
            )

    if reset:
        remove_target(target)

    target.parent.mkdir(parents=True, exist_ok=True)

    started_at = utc_now()
    source_connection = connect_read_only(source)
    try:
        ensure_source_tables(source_connection)
        source_counts = read_source_counts(source_connection)
        buckets, seeded_categories = _build_rows(source_connection, started_at)
    finally:
        source_connection.close()

    engine = make_target_engine(target)
    try:
        SQLModel.metadata.create_all(engine)
        import_run_id = str(uuid.uuid4())
        counts = {name: len(rows) for name, rows in buckets.items()}

        with engine.begin() as connection:
            # Parents first; the order is the same as TABLE_MAP insertion.
            for table_name in (
                "categories",
                "groups",
                "participants",
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
            ):
                rows = buckets[table_name]
                if rows:
                    connection.execute(SQLModel.metadata.tables[table_name].insert(), rows)

            finished_at = utc_now()
            duration_ms = int((finished_at - started_at).total_seconds() * 1000)
            counts_payload = {
                "source": source_counts,
                "imported": counts,
                "seeded_categories": seeded_categories,
                "skipped_tables": list(SKIPPED_TABLES),
            }
            import_run = {
                "id": import_run_id,
                "source_path": str(source),
                "source_checksum": checksum,
                "target_path": str(target),
                "status": "completed",
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "counts_json": json.dumps(counts_payload, sort_keys=True),
                "error": None,
            }
            connection.execute(SQLModel.metadata.tables["import_runs"].insert(), [import_run])
    finally:
        engine.dispose()

    return {
        "status": "imported",
        "source": str(source),
        "target": str(target),
        "checksum": checksum,
        "import_run_id": import_run_id,
        "duration_ms": duration_ms,
        "source_counts": source_counts,
        "counts": counts,
        "seeded_categories": seeded_categories,
    }
