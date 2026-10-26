"""Generate the deterministic domain fixtures shared by Python and Vitest.

The fixtures are captured from the Stage 3 Python mirrors, which were verified
against the reference TypeScript implementation. Stage 9C replays the same JSON
in JavaScript so the offline calculations cannot drift.

Run from the repository root:

    PYTHONPATH=backend python backend/scripts/generate_domain_fixtures.py
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.utils.balances import (
    get_balances,
    get_public_balances,
    get_suggested_reimbursements,
)
from app.utils.currency import format_amount_as_decimal, format_amount_for_csv
from app.utils.receipt_split import compute_receipt_split
from app.utils.recurrence import calculate_next_date
from app.utils.shares import get_expense_shares
from app.utils.totals import (
    filter_expenses_by_date_range,
    get_expenses_by_category,
    get_expenses_by_month,
    get_recurring_spending,
    get_spending_by_category,
    get_spending_by_participant,
    get_spending_over_time,
    get_spending_summary,
    get_total_active_user_paid_for,
    get_total_active_user_share,
    get_total_group_spending,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "shared" / "fixtures" / "domain"


def share_case(name: str, expense: dict) -> dict:
    shares = get_expense_shares(expense)
    return {
        "name": name,
        "expense": expense,
        "expected": {key: shares[key] for key in sorted(shares)},
    }


def balance_case(name: str, expenses: list[dict]) -> dict:
    balances = get_balances(expenses)
    reimbursements = get_suggested_reimbursements(balances)
    public = get_public_balances(reimbursements)
    return {
        "name": name,
        "expenses": expenses,
        "expected": {
            "balances": {
                participant_id: {
                    "paid": values["paid"],
                    "paidFor": values["paidFor"],
                    "total": values["total"],
                }
                for participant_id, values in sorted(balances.items())
            },
            "reimbursements": reimbursements,
            "public": {
                participant_id: {
                    "paid": values["paid"],
                    "paidFor": values["paidFor"],
                    "total": values["total"],
                }
                for participant_id, values in sorted(public.items())
            },
        },
    }


def expense(
    expense_id: str,
    amount: int,
    *,
    paid_by_id: str,
    paid_for: list[tuple[str, int]],
    split_mode: str = "EVENLY",
    expense_date: str = "2026-03-01",
    category_id: int = 0,
    title: str = "Expense",
    is_reimbursement: bool = False,
    recurrence_rule: str = "NONE",
) -> dict:
    return {
        "id": expense_id,
        "expense_date": expense_date,
        "title": title,
        "amount": amount,
        "category_id": category_id,
        "paid_by_id": paid_by_id,
        "paid_for": [
            {"participant_id": participant_id, "shares": shares}
            for participant_id, shares in paid_for
        ],
        "split_mode": split_mode,
        "is_reimbursement": is_reimbursement,
        "recurrence_rule": recurrence_rule,
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    share_cases = [
        share_case(
            "even-two-of-three",
            expense("e-even", 100, paid_by_id="a", paid_for=[("a", 1), ("b", 1)]),
        ),
        share_case(
            "one-third",
            expense("e-third", 100, paid_by_id="a", paid_for=[("a", 1), ("b", 1), ("c", 1)]),
        ),
        share_case(
            "half-of-odd",
            expense("e-half", 101, paid_by_id="a", paid_for=[("a", 1), ("b", 1)]),
        ),
        share_case(
            "by-shares",
            expense(
                "e-shares",
                101,
                paid_by_id="a",
                paid_for=[("a", 2), ("b", 1), ("c", 1)],
                split_mode="BY_SHARES",
            ),
        ),
        share_case(
            "by-percentage",
            expense(
                "e-percentage",
                1000,
                paid_by_id="a",
                paid_for=[("a", 3333), ("b", 3333), ("c", 3334)],
                split_mode="BY_PERCENTAGE",
            ),
        ),
        share_case(
            "negative-income",
            expense("e-income", -100, paid_by_id="a", paid_for=[("a", 1), ("b", 1), ("c", 1)]),
        ),
        share_case(
            "zero-shares",
            expense(
                "e-zero",
                100,
                paid_by_id="a",
                paid_for=[("a", 0), ("b", 0)],
                split_mode="BY_SHARES",
            ),
        ),
    ]
    (OUTPUT / "shares.json").write_text(json.dumps(share_cases, indent=2) + "\n")

    balance_expenses = [
        expense("b1", 9000, paid_by_id="alice", paid_for=[("alice", 1), ("bob", 1), ("carol", 1)]),
        expense("b2", 3000, paid_by_id="bob", paid_for=[("alice", 1), ("bob", 1), ("carol", 1)]),
        expense(
            "b3",
            1550,
            paid_by_id="carol",
            paid_for=[("alice", 1), ("carol", 1)],
            split_mode="BY_SHARES",
        ),
        expense(
            "b4",
            -1200,
            paid_by_id="alice",
            paid_for=[("alice", 1), ("bob", 1)],
            is_reimbursement=True,
        ),
    ]
    balance_cases = [
        balance_case("three-participants", balance_expenses),
        balance_case(
            "reimbursement",
            [expense("r1", 1000, paid_by_id="a", paid_for=[("a", 1), ("b", 1)])],
        ),
        balance_case(
            "zero-total",
            [expense("z1", 0, paid_by_id="a", paid_for=[("a", 1), ("b", 1)])],
        ),
    ]
    (OUTPUT / "balances.json").write_text(json.dumps(balance_cases, indent=2) + "\n")

    totals_expenses = balance_expenses + [
        expense(
            "t1",
            2500,
            paid_by_id="alice",
            paid_for=[("alice", 1), ("bob", 1)],
            expense_date="2026-01-31",
            category_id=9,
            title="Groceries",
            recurrence_rule="MONTHLY",
        ),
        expense(
            "t2",
            800,
            paid_by_id="bob",
            paid_for=[("bob", 1), ("carol", 1)],
            expense_date="2026-02-28",
            category_id=9,
            title="Bread",
        ),
        expense(
            "t3",
            1200,
            paid_by_id="carol",
            paid_for=[("alice", 1), ("carol", 1)],
            expense_date="2026-04-02",
            category_id=27,
            title="Train",
            recurrence_rule="WEEKLY",
        ),
    ]
    categories = {
        0: {"id": 0, "grouping": "Uncategorized", "name": "General"},
        9: {"id": 9, "grouping": "Food and Drink", "name": "Groceries"},
        27: {"id": 27, "grouping": "Transportation", "name": "Transportation"},
    }
    decorated = [
        {**row, "category": categories.get(int(row["category_id"]), categories[0])}
        for row in totals_expenses
    ]
    participants = [
        {"id": "alice", "name": "Alice"},
        {"id": "bob", "name": "Bob"},
        {"id": "carol", "name": "Carol"},
    ]
    totals_cases = {
        "expenses": decorated,
        "participants": participants,
        "expected": {
            "total_group_spending": get_total_group_spending(decorated),
            "total_active_user_paid_for": get_total_active_user_paid_for("alice", decorated),
            "total_active_user_share": get_total_active_user_share("alice", decorated),
            "spending_by_category": get_spending_by_category(decorated),
            "spending_by_participant": get_spending_by_participant(participants, decorated),
            "spending_over_time": get_spending_over_time(decorated),
            "summary": get_spending_summary(decorated),
            "recurring": get_recurring_spending(decorated),
            "range_2026_02": [
                row["id"]
                for row in filter_expenses_by_date_range(decorated, "2026-02-01", "2026-02-28")
            ],
            "category_9": [
                row["id"] for row in get_expenses_by_category(decorated, 9)
            ],
            "month_2026_01": [
                row["id"] for row in get_expenses_by_month(decorated, "2026-01")
            ],
        },
    }
    (OUTPUT / "totals.json").write_text(json.dumps(totals_cases, indent=2) + "\n")

    receipt_cases = [
        {
            "name": "direct-and-shared",
            "participants": ["a", "b", "c"],
            "opt_outs": [],
            "items": [
                {
                    "name": "Pizza",
                    "amount": 1000,
                    "quantity_milli": 1000,
                    "portions": [
                        {"target": "PARTICIPANT", "participant_id": "a", "quantity_milli": 1000}
                    ],
                },
                {
                    "name": "Service",
                    "amount": 999,
                    "quantity_milli": 1000,
                    "portions": [
                        {"target": "SHARED", "participant_id": None, "quantity_milli": 1000}
                    ],
                },
                {
                    "name": "Unassigned",
                    "amount": 100,
                    "quantity_milli": 1000,
                    "portions": [],
                },
            ],
            "expected": asdict(compute_receipt_split(
                ["a", "b", "c"],
                [],
                [
                    {
                        "amount": 1000,
                        "quantity_milli": 1000,
                        "portions": [
                            {"target": "PARTICIPANT", "participant_id": "a", "quantity_milli": 1000}
                        ],
                    },
                    {
                        "amount": 999,
                        "quantity_milli": 1000,
                        "portions": [
                            {"target": "SHARED", "participant_id": None, "quantity_milli": 1000}
                        ],
                    },
                    {"amount": 100, "quantity_milli": 1000, "portions": []},
                ],
            )),
        },
        {
            "name": "fractional-and-opt-out",
            "participants": ["a", "b", "c"],
            "opt_outs": ["c"],
            "items": [
                {
                    "name": "Shared starter",
                    "amount": 1001,
                    "quantity_milli": 1000,
                    "portions": [
                        {"target": "SHARED", "participant_id": None, "quantity_milli": 1000}
                    ],
                },
                {
                    "name": "Repeated",
                    "amount": 501,
                    "quantity_milli": 2000,
                    "portions": [
                        {"target": "PARTICIPANT", "participant_id": "a", "quantity_milli": 1000},
                        {"target": "PARTICIPANT", "participant_id": "b", "quantity_milli": 500},
                    ],
                },
            ],
            "expected": asdict(compute_receipt_split(
                ["a", "b", "c"],
                ["c"],
                [
                    {
                        "amount": 1001,
                        "quantity_milli": 1000,
                        "portions": [
                            {"target": "SHARED", "participant_id": None, "quantity_milli": 1000}
                        ],
                    },
                    {
                        "amount": 501,
                        "quantity_milli": 2000,
                        "portions": [
                            {"target": "PARTICIPANT", "participant_id": "a", "quantity_milli": 1000},
                            {"target": "PARTICIPANT", "participant_id": "b", "quantity_milli": 500},
                        ],
                    },
                ],
            )),
        },
        {
            "name": "all-opted-out",
            "participants": ["a"],
            "opt_outs": ["a"],
            "items": [
                {"amount": 250, "quantity_milli": 1000, "portions": []},
            ],
            "expected": asdict(compute_receipt_split(
                ["a"], ["a"], [{"amount": 250, "quantity_milli": 1000, "portions": []}]
            )),
        },
    ]
    (OUTPUT / "receipt-split.json").write_text(json.dumps(receipt_cases, indent=2) + "\n")

    recurrence_cases = []
    for rule, prior in [
        ("DAILY", datetime(2026, 3, 1, 12, 30, tzinfo=UTC)),
        ("WEEKLY", datetime(2026, 3, 1, 12, 30, tzinfo=UTC)),
        ("MONTHLY", datetime(2026, 1, 31, 9, 0, tzinfo=UTC)),
        ("MONTHLY", datetime(2026, 2, 28, 9, 0, tzinfo=UTC)),
        ("MONTHLY", datetime(2026, 12, 31, 23, 59, tzinfo=UTC)),
        ("NONE", datetime(2026, 3, 1, tzinfo=UTC)),
    ]:
        recurrence_cases.append(
            {
                "rule": rule,
                "prior": prior.isoformat().replace("+00:00", "Z"),
                "expected": calculate_next_date(rule, prior).isoformat().replace("+00:00", "Z"),
            }
        )
    (OUTPUT / "recurrence.json").write_text(json.dumps(recurrence_cases, indent=2) + "\n")

    currency_cases = [
        {
            "amount": amount,
            "currency_code": code,
            "decimal": format_amount_as_decimal(amount, code),
            "csv": format_amount_for_csv(amount, code),
        }
        for amount, code in [
            (1234, "USD"),
            (-5, "USD"),
            (1000, "JPY"),
            (0, "EUR"),
            (-1234, "JPY"),
            (999, None),
        ]
    ]
    (OUTPUT / "currency.json").write_text(json.dumps(currency_cases, indent=2) + "\n")

    print(f"Wrote fixtures to {OUTPUT}")


if __name__ == "__main__":
    main()
