#!/usr/bin/env python3
"""Measure the Stage 12 backend performance targets on a temporary database.

Usage:
    cd backend
    PYTHONPATH=. .venv/bin/python scripts/performance_check.py

Targets (plan Stage 12):
  * first expense page p95 < 300 ms with 10,000 expenses;
  * a 50-operation synchronization push < 500 ms;
  * bootstrap of a 1,000-expense group < 1 s.

The script seeds only disposable data. It exits nonzero when a target is
missed, so it can run in staging as a smoke check. The numbers include HTTP
serialization through TestClient but not network latency.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=25, help="expense-list samples")
    parser.add_argument("--page-budget-ms", type=float, default=300.0)
    parser.add_argument("--sync-budget-ms", type=float, default=500.0)
    parser.add_argument("--bootstrap-budget-ms", type=float, default=1000.0)
    parser.add_argument(
        "--database",
        type=Path,
        help="optional disposable database path (default: a temporary file)",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args(argv)


def _configure_environment(database: Path) -> None:
    os.environ["ENVIRONMENT"] = "development"
    os.environ["DATABASE_URL"] = f"sqlite:///{database}"
    os.environ["UPLOAD_DIR"] = str(database.parent / "uploads")
    os.environ["ENABLE_MOCK_LOGIN"] = "false"
    # The benchmark is intentionally noisy for the limiter.
    os.environ["SYNC_RATE_LIMIT_PER_MINUTE"] = "100000"
    os.environ["AUTH_RATE_LIMIT_PER_MINUTE"] = "100000"
    os.environ["AUTH_ACCOUNT_RATE_LIMIT_PER_MINUTE"] = "100000"


def _seed(session, *, group_size: int, bootstrap_size: int):
    from app.core.ids import new_id
    from app.models.expense import Expense
    from app.models.expense_paid_for import ExpensePaidFor
    from app.models.group import Group
    from app.models.participant import Participant
    from app.services.categories import ensure_default_categories
    from app.utils.dates import date_to_datetime

    now = datetime.now(UTC)
    ensure_default_categories(session, commit=False)

    def build_group(name: str, size: int):
        group = Group(
            id=new_id("grp"),
            name=name,
            currency="$",
            currency_code="USD",
            created_at=now,
            updated_at=now,
            version=1,
        )
        session.add(group)
        session.flush()
        alice = Participant(
            id=new_id("par"),
            name="Alice",
            group_id=group.id,
            updated_at=now,
            version=1,
        )
        bob = Participant(
            id=new_id("par"),
            name="Bob",
            group_id=group.id,
            updated_at=now,
            version=1,
        )
        session.add_all([alice, bob])
        session.flush()

        expenses = []
        paid_for = []
        base_date = date_to_datetime(datetime(2026, 1, 1, tzinfo=UTC).date())
        for index in range(size):
            expense_id = new_id("exp")
            moment = base_date + timedelta(minutes=index)
            expenses.append(
                Expense(
                    id=expense_id,
                    group_id=group.id,
                    expense_date=moment,
                    title=f"{name} expense {index}",
                    category_id=index % 44,
                    amount=1000 + (index % 5000),
                    paid_by_id=alice.id,
                    split_mode="EVENLY",
                    recurrence_rule="NONE",
                    created_at=moment,
                    updated_at=now,
                    version=1,
                )
            )
            for participant in (alice, bob):
                paid_for.append(
                    ExpensePaidFor(
                        expense_id=expense_id,
                        participant_id=participant.id,
                        shares=1,
                        updated_at=now,
                        version=1,
                    )
                )
        session.add_all(expenses)
        session.add_all(paid_for)
        session.commit()
        return group, alice, bob

    large, _, _ = build_group("Large", group_size)
    bootstrap, _, _ = build_group("Bootstrap", bootstrap_size)
    return large, bootstrap


def _percentile(values: list[float], fraction: float = 0.95) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.database is None:
        temporary = tempfile.TemporaryDirectory(prefix="pysplit-perf-")
        database = Path(temporary.name) / "perf.db"
    else:
        database = args.database.resolve()
        database.parent.mkdir(parents=True, exist_ok=True)
        database.unlink(missing_ok=True)

    _configure_environment(database)

    # Import after the environment is set: the engine and settings are built
    # once at import time.
    from fastapi.testclient import TestClient
    from sqlmodel import Session

    from app.core.database import create_db_and_tables, engine
    from app.main import create_app

    create_db_and_tables()
    with Session(engine) as session:
        large, bootstrap = _seed(session, group_size=10_000, bootstrap_size=1_000)
        large_group_id = large.id
        bootstrap_group_id = bootstrap.id

    results: dict[str, object] = {
        "database": str(database),
        "samples": args.samples,
        "expenses_page": {},
        "sync_push": {},
        "bootstrap": {},
    }
    failures: list[str] = []

    with TestClient(create_app()) as client:
        # Warm the route before measuring so import-time work is not included.
        url = f"/api/groups/{large_group_id}/expenses?limit=50"
        for _ in range(3):
            response = client.get(url)
            response.raise_for_status()

        timings: list[float] = []
        for _ in range(args.samples):
            started = time.perf_counter()
            response = client.get(url)
            elapsed_ms = (time.perf_counter() - started) * 1000
            response.raise_for_status()
            assert len(response.json()["items"]) <= 50
            timings.append(elapsed_ms)
        page_p95 = _percentile(timings)
        results["expenses_page"] = {
            "p95_ms": round(page_p95, 2),
            "min_ms": round(min(timings), 2),
            "max_ms": round(max(timings), 2),
            "budget_ms": args.page_budget_ms,
            "items": len(response.json()["items"]),
        }
        if page_p95 >= args.page_budget_ms:
            failures.append(f"expense page p95 {page_p95:.1f} ms >= {args.page_budget_ms} ms")

        # 50 updates to distinct seeded expenses, each with the current base
        # version. This is the maximum outbox batch size.
        with Session(engine) as session:
            from sqlmodel import select

            from app.models.expense import Expense

            ids = list(
                session.exec(
                    select(Expense.id)
                    .where(Expense.group_id == large_group_id)
                    .order_by(Expense.id)
                    .limit(50)
                ).all()
            )
        operations = [
            {
                "op_id": f"perf-op-{index}",
                "group_id": large_group_id,
                "entity_type": "expense",
                "entity_id": expense_id,
                "op_type": "update",
                "base_version": 1,
                "payload": {"title": f"Performance update {index}"},
                "client_time": "2026-10-24T12:00:00Z",
            }
            for index, expense_id in enumerate(ids)
        ]
        started = time.perf_counter()
        response = client.post("/api/sync/push", json={"operations": operations})
        sync_ms = (time.perf_counter() - started) * 1000
        response.raise_for_status()
        body = response.json()
        applied = sum(1 for item in body["results"] if item["status"] == "applied")
        results["sync_push"] = {
            "operations": len(operations),
            "applied": applied,
            "duration_ms": round(sync_ms, 2),
            "budget_ms": args.sync_budget_ms,
        }
        if applied != len(operations):
            failures.append(f"only {applied}/{len(operations)} sync operations applied")
        if sync_ms >= args.sync_budget_ms:
            failures.append(f"sync push {sync_ms:.1f} ms >= {args.sync_budget_ms} ms")

        started = time.perf_counter()
        response = client.get("/api/sync/bootstrap", params={"group_id": bootstrap_group_id})
        bootstrap_ms = (time.perf_counter() - started) * 1000
        response.raise_for_status()
        expense_count = len(response.json()["expenses"])
        results["bootstrap"] = {
            "expenses": expense_count,
            "duration_ms": round(bootstrap_ms, 2),
            "budget_ms": args.bootstrap_budget_ms,
        }
        if expense_count != 1_000:
            failures.append(f"bootstrap returned {expense_count} expenses, expected 1000")
        if bootstrap_ms >= args.bootstrap_budget_ms:
            failures.append(f"bootstrap {bootstrap_ms:.1f} ms >= {args.bootstrap_budget_ms} ms")

    results["passed"] = not failures
    results["failures"] = failures
    engine.dispose()
    if temporary is not None:
        temporary.cleanup()

    if args.as_json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        page = results["expenses_page"]
        sync = results["sync_push"]
        boot = results["bootstrap"]
        print(f"Expense page p95: {page['p95_ms']} ms (budget {page['budget_ms']} ms)")
        print(f"50-op sync push:  {sync['duration_ms']} ms (budget {sync['budget_ms']} ms)")
        print(f"Bootstrap 1,000:  {boot['duration_ms']} ms (budget {boot['budget_ms']} ms)")
        if failures:
            print("\nFAILED:")
            for failure in failures:
                print(f"  - {failure}")
        else:
            print("\nOK: all Stage 12 performance targets passed.")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
