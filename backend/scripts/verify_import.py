#!/usr/bin/env python3
"""Verify that a legacy database was imported without loss.

Usage:
    python scripts/verify_import.py --old old.db --new new.db
    python scripts/verify_import.py --old old.db --new new.db --golden-dir ../shared/fixtures/legacy

Checks:
  * every migrated row is present and equal (including timestamps, booleans
    and decimal conversion rates);
  * missing default categories were seeded and no source category was lost;
  * per-group participant counts, expense counts and amount sums match;
  * SQLite ``integrity_check`` and ``foreign_key_check`` pass;
  * balances match a reference-generated golden fixture when one is available
    (otherwise the old database is used as the reference).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.categories import DEFAULT_CATEGORIES
from scripts.legacy_balances import (
    datetime_to_iso,
    json_safe_balances,
    source_balances,
    target_balances,
)
from scripts.legacy_importer import (
    connect_read_only,
    file_checksum,
    find_completed_run,
    parse_bool,
    parse_datetime,
    parse_decimal,
    parse_optional_int,
)

# (source table, target table, source key columns, target key columns,
#  [(source column, target column, kind), ...])
RowSpec = tuple[str, str, list[str], list[str], list[tuple[str, str, str]]]

ROW_SPECS: list[RowSpec] = [
    (
        "Group",
        "groups",
        ["id"],
        ["id"],
        [
            ("id", "id", "str"),
            ("name", "name", "str"),
            ("information", "information", "str"),
            ("currency", "currency", "str"),
            ("currencyCode", "currency_code", "str"),
            ("createdAt", "created_at", "datetime"),
        ],
    ),
    (
        "Participant",
        "participants",
        ["id"],
        ["id"],
        [
            ("id", "id", "str"),
            ("name", "name", "str"),
            ("groupId", "group_id", "str"),
        ],
    ),
    (
        "Category",
        "categories",
        ["id"],
        ["id"],
        [
            ("id", "id", "int"),
            ("grouping", "grouping", "str"),
            ("name", "name", "str"),
        ],
    ),
    (
        "Expense",
        "expenses",
        ["id"],
        ["id"],
        [
            ("id", "id", "str"),
            ("groupId", "group_id", "str"),
            ("expenseDate", "expense_date", "datetime"),
            ("title", "title", "str"),
            ("categoryId", "category_id", "int"),
            ("amount", "amount", "int"),
            ("originalAmount", "original_amount", "int"),
            ("originalCurrency", "original_currency", "str"),
            ("conversionRate", "conversion_rate", "decimal"),
            ("paidById", "paid_by_id", "str"),
            ("isReimbursement", "is_reimbursement", "bool"),
            ("splitMode", "split_mode", "str"),
            ("createdAt", "created_at", "datetime"),
            ("notes", "notes", "str"),
            ("recurrenceRule", "recurrence_rule", "str"),
            ("recurringExpenseLinkId", "recurring_expense_link_id", "str"),
        ],
    ),
    (
        "ExpensePaidFor",
        "expense_paid_for",
        ["expenseId", "participantId"],
        ["expense_id", "participant_id"],
        [
            ("expenseId", "expense_id", "str"),
            ("participantId", "participant_id", "str"),
            ("shares", "shares", "int"),
        ],
    ),
    (
        "ExpenseDocument",
        "expense_documents",
        ["id"],
        ["id"],
        [
            ("id", "id", "str"),
            ("url", "url", "str"),
            ("width", "width", "int"),
            ("height", "height", "int"),
            ("expenseId", "expense_id", "str"),
        ],
    ),
    (
        "Activity",
        "activities",
        ["id"],
        ["id"],
        [
            ("id", "id", "str"),
            ("groupId", "group_id", "str"),
            ("time", "time", "datetime"),
            ("activityType", "activity_type", "str"),
            ("participantId", "participant_id", "str"),
            ("expenseId", "expense_id", "str"),
            ("data", "data", "str"),
        ],
    ),
    (
        "RecurringExpenseLink",
        "recurring_expense_links",
        ["id"],
        ["id"],
        [
            ("id", "id", "str"),
            ("groupId", "group_id", "str"),
            ("currentFrameExpenseId", "current_frame_expense_id", "str"),
            ("nextExpenseCreatedAt", "next_expense_created_at", "datetime"),
            ("nextExpenseDate", "next_expense_date", "datetime"),
        ],
    ),
    (
        "User",
        "users",
        ["id"],
        ["id"],
        [
            ("id", "id", "str"),
            ("name", "name", "str"),
            ("email", "email", "str"),
            ("emailVerified", "email_verified", "datetime"),
            ("image", "image", "str"),
            ("tier", "tier", "str"),
            ("createdAt", "created_at", "datetime"),
            ("updatedAt", "updated_at", "datetime"),
        ],
    ),
    (
        "Account",
        "accounts",
        ["id"],
        ["id"],
        [
            ("id", "id", "str"),
            ("userId", "user_id", "str"),
            ("type", "type", "str"),
            ("provider", "provider", "str"),
            ("providerAccountId", "provider_account_id", "str"),
            ("refresh_token", "refresh_token", "str"),
            ("access_token", "access_token", "str"),
            ("expires_at", "expires_at", "int"),
            ("token_type", "token_type", "str"),
            ("scope", "scope", "str"),
            ("id_token", "id_token", "str"),
            ("session_state", "session_state", "str"),
        ],
    ),
    (
        "UserGroup",
        "user_groups",
        ["userId", "groupId"],
        ["user_id", "group_id"],
        [
            ("userId", "user_id", "str"),
            ("groupId", "group_id", "str"),
            ("isStarred", "is_starred", "bool"),
            ("isArchived", "is_archived", "bool"),
            ("createdAt", "created_at", "datetime"),
        ],
    ),
    (
        "Receipt",
        "receipts",
        ["id"],
        ["id"],
        [
            ("id", "id", "str"),
            ("groupId", "group_id", "str"),
            ("imageUrl", "image_url", "str"),
            ("imageWidth", "image_width", "int"),
            ("imageHeight", "image_height", "int"),
            ("status", "status", "str"),
            ("rawExtraction", "raw_extraction", "str"),
            ("provider", "provider", "str"),
            ("model", "model", "str"),
            ("merchant", "merchant", "str"),
            ("receiptDate", "receipt_date", "datetime"),
            ("currencyCode", "currency_code", "str"),
            ("total", "total", "int"),
            ("expenseId", "expense_id", "str"),
            ("createdAt", "created_at", "datetime"),
            ("updatedAt", "updated_at", "datetime"),
        ],
    ),
    (
        "ReceiptItem",
        "receipt_items",
        ["id"],
        ["id"],
        [
            ("id", "id", "str"),
            ("receiptId", "receipt_id", "str"),
            ("name", "name", "str"),
            ("quantityMilli", "quantity_milli", "int"),
            ("unitPrice", "unit_price", "int"),
            ("amount", "amount", "int"),
            ("isShared", "is_shared", "bool"),
            ("isAdjustment", "is_adjustment", "bool"),
            ("position", "position", "int"),
            ("createdAt", "created_at", "datetime"),
            ("updatedAt", "updated_at", "datetime"),
        ],
    ),
    (
        "ReceiptItemPortion",
        "receipt_item_portions",
        ["id"],
        ["id"],
        [
            ("id", "id", "str"),
            ("itemId", "item_id", "str"),
            ("target", "target", "str"),
            ("participantId", "participant_id", "str"),
            ("quantityMilli", "quantity_milli", "int"),
            ("createdAt", "created_at", "datetime"),
            ("updatedAt", "updated_at", "datetime"),
        ],
    ),
    (
        "ReceiptOptOut",
        "receipt_opt_outs",
        ["id"],
        ["id"],
        [
            ("id", "id", "str"),
            ("receiptId", "receipt_id", "str"),
            ("participantId", "participant_id", "str"),
            ("createdAt", "created_at", "datetime"),
        ],
    ),
]


def normalise(value: Any, kind: str) -> Any:
    if kind == "int":
        return parse_optional_int(value)
    if kind == "bool":
        return None if value is None else parse_bool(value)
    if kind == "datetime":
        parsed = parse_datetime(value)
        return datetime_to_iso(parsed)
    if kind == "decimal":
        parsed = parse_decimal(value)
        return None if parsed is None else format(parsed, "f")
    if kind == "str":
        return None if value is None else str(value)
    raise AssertionError(f"unknown kind: {kind}")


def load_source_rows(
    connection: sqlite3.Connection,
    spec: RowSpec,
) -> dict[tuple[Any, ...], tuple[Any, ...]]:
    source_table, _, source_keys, _, fields = spec
    columns = [field[0] for field in fields]
    selected = ", ".join(f'"{column}"' for column in columns)
    rows = connection.execute(f'SELECT {selected} FROM "{source_table}"').fetchall()
    key_indexes = [columns.index(key) for key in source_keys]
    key_kinds = [
        next(kind for source_col, _, kind in fields if source_col == key) for key in source_keys
    ]
    return {
        tuple(
            normalise(row[index], kind) for index, kind in zip(key_indexes, key_kinds, strict=True)
        ): tuple(normalise(row[index], kind) for index, (_, _, kind) in enumerate(fields))
        for row in rows
    }


def load_target_rows(
    connection: sqlite3.Connection,
    spec: RowSpec,
) -> dict[tuple[Any, ...], tuple[Any, ...]]:
    _, target_table, _, target_keys, fields = spec
    columns = [field[1] for field in fields]
    selected = ", ".join(f'"{column}"' for column in columns)
    rows = connection.execute(f'SELECT {selected} FROM "{target_table}"').fetchall()
    key_indexes = [columns.index(key) for key in target_keys]
    key_kinds = [
        next(kind for _, target_col, kind in fields if target_col == key) for key in target_keys
    ]
    return {
        tuple(
            normalise(row[index], kind) for index, kind in zip(key_indexes, key_kinds, strict=True)
        ): tuple(normalise(row[index], kind) for index, (_, _, kind) in enumerate(fields))
        for row in rows
    }


def compare_rows(old: sqlite3.Connection, new: sqlite3.Connection) -> list[str]:
    problems: list[str] = []
    for spec in ROW_SPECS:
        source_table, target_table, _, _, _ = spec
        source_rows = load_source_rows(old, spec)
        target_rows = load_target_rows(new, spec)
        missing = sorted(set(source_rows) - set(target_rows))
        extra = sorted(set(target_rows) - set(source_rows))
        if source_table == "Category":
            default_ids = {category_id for category_id, _, _ in DEFAULT_CATEGORIES}
            extra = [key for key in extra if key[0] not in default_ids]
        if missing:
            problems.append(f"{target_table}: {len(missing)} missing rows (sample {missing[:3]})")
        if extra:
            problems.append(f"{target_table}: {len(extra)} unexpected rows (sample {extra[:3]})")
        for key in sorted(set(source_rows) & set(target_rows)):
            if source_rows[key] != target_rows[key]:
                problems.append(
                    f"{target_table}: row {key!r} differs "
                    f"(source={source_rows[key]!r}, target={target_rows[key]!r})"
                )
        if source_table == "Category":
            # Seeded categories are expected on top of the source rows.
            expected_defaults = {category_id for category_id, _, _ in DEFAULT_CATEGORIES}
            missing_defaults = expected_defaults - {key[0] for key in target_rows}
            if missing_defaults:
                problems.append(
                    "categories: missing default ids "
                    + ", ".join(str(item) for item in sorted(missing_defaults))
                )
    return problems


def compare_group_aggregates(old: sqlite3.Connection, new: sqlite3.Connection) -> list[str]:
    problems: list[str] = []

    old_participants = {
        str(row[0]): int(row[1])
        for row in old.execute('SELECT "groupId", COUNT(*) FROM "Participant" GROUP BY "groupId"')
    }
    new_participants = {
        str(row[0]): int(row[1])
        for row in new.execute("SELECT group_id, COUNT(*) FROM participants GROUP BY group_id")
    }
    old_expenses = {
        str(row[0]): (int(row[1]), int(row[2]))
        for row in old.execute(
            'SELECT "groupId", COUNT(*), COALESCE(SUM(amount), 0) FROM "Expense" GROUP BY "groupId"'
        )
    }
    new_expenses = {
        str(row[0]): (int(row[1]), int(row[2]))
        for row in new.execute(
            "SELECT group_id, COUNT(*), COALESCE(SUM(amount), 0) FROM expenses GROUP BY group_id"
        )
    }

    for group_id in sorted(set(old_participants) | set(new_participants)):
        if old_participants.get(group_id, 0) != new_participants.get(group_id, 0):
            problems.append(
                f"group {group_id}: participant count "
                f"{new_participants.get(group_id, 0)} != "
                f"{old_participants.get(group_id, 0)}"
            )
    for group_id in sorted(set(old_expenses) | set(new_expenses)):
        if old_expenses.get(group_id, (0, 0)) != new_expenses.get(group_id, (0, 0)):
            problems.append(
                f"group {group_id}: expense count/sum "
                f"{new_expenses.get(group_id, (0, 0))} != "
                f"{old_expenses.get(group_id, (0, 0))}"
            )
    return problems


def pragma_problems(connection: sqlite3.Connection, label: str) -> list[str]:
    problems: list[str] = []
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        problems.append(f"{label}: integrity_check returned {integrity!r}")
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        problems.append(f"{label}: {len(violations)} foreign key violation(s)")
    return problems


def find_golden(directory: Path, checksum: str) -> tuple[Path | None, dict[str, Any] | None]:
    if not directory.exists():
        return None, None
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("source_checksum") == checksum:
            return path, payload
    return None, None


def diff_balances(
    expected: dict[str, dict[str, dict[str, int]]],
    actual: dict[str, dict[str, dict[str, int]]],
    label: str,
) -> list[str]:
    problems: list[str] = []
    for group_id in sorted(set(expected) | set(actual)):
        expected_group = expected.get(group_id, {})
        actual_group = actual.get(group_id, {})
        for participant_id in sorted(set(expected_group) | set(actual_group)):
            if expected_group.get(participant_id) != actual_group.get(participant_id):
                problems.append(
                    f"{label} group {group_id} participant {participant_id}: "
                    f"{actual_group.get(participant_id)} != "
                    f"{expected_group.get(participant_id)}"
                )
    return problems


def verify(
    old_path: Path,
    new_path: Path,
    golden_dir: Path,
    *,
    require_golden: bool = False,
) -> dict[str, Any]:
    if not new_path.exists():
        raise FileNotFoundError(f"target database not found: {new_path}")

    old = connect_read_only(old_path)
    new = sqlite3.connect(new_path)
    new.row_factory = sqlite3.Row
    problems: list[str] = []
    checks: list[str] = []
    try:
        checksum = file_checksum(old_path)
        checks.append(f"source checksum: {checksum}")

        # Import run audit row.
        run = find_completed_run(new_path, checksum)
        if run is None:
            problems.append("import_runs: no completed run for this source checksum")
        else:
            checks.append(f"import run: {run['id']} ({run['duration_ms']} ms)")

        row_problems = compare_rows(old, new)
        problems.extend(row_problems)
        checks.append(f"row equality: {len(ROW_SPECS)} table(s) compared")

        aggregate_problems = compare_group_aggregates(old, new)
        problems.extend(aggregate_problems)
        checks.append("per-group participant/expense aggregates compared")

        problems.extend(pragma_problems(old, "source"))
        problems.extend(pragma_problems(new, "target"))
        checks.append("integrity_check and foreign_key_check")

        old_balances = json_safe_balances(source_balances(old))
        new_balances = json_safe_balances(target_balances(new))

        golden_path, golden = find_golden(golden_dir, checksum)
        if golden is not None:
            expected_balances = golden.get("groups", {})
            problems.extend(diff_balances(expected_balances, old_balances, "source/golden"))
            problems.extend(diff_balances(expected_balances, new_balances, "target/golden"))
            checks.append(f"balances vs golden: {golden_path}")
        else:
            message = f"no reference golden fixture for checksum {checksum}"
            if require_golden:
                problems.append(message)
            else:
                problems.extend(diff_balances(old_balances, new_balances, "target/source"))
                checks.append(message + "; compared target to source instead")

        summary = {
            "ok": not problems,
            "old": str(old_path),
            "new": str(new_path),
            "checksum": checksum,
            "checks": checks,
            "problems": problems,
            "group_count": len(new_balances),
        }
        return summary
    finally:
        old.close()
        new.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", required=True, type=Path, help="legacy source database")
    parser.add_argument("--new", required=True, type=Path, help="imported target database")
    parser.add_argument(
        "--golden-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "shared" / "fixtures" / "legacy",
        help="directory containing reference balance fixtures",
    )
    parser.add_argument(
        "--require-golden",
        action="store_true",
        help="fail when no reference golden fixture matches the source checksum",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = verify(
            args.old,
            args.new,
            args.golden_dir,
            require_golden=args.require_golden,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(summary, indent=2))
    else:
        for check in summary["checks"]:
            print(f"  ok: {check}")
        if summary["problems"]:
            print("FAIL:")
            for problem in summary["problems"]:
                print(f"  - {problem}")
        else:
            print(f"PASS: import verified ({summary['group_count']} group(s))")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
