"""Stage 5D tests: CSV and JSON exports."""

from __future__ import annotations

import csv
import io
import json
from datetime import date

from sqlmodel import Session

from tests.helpers import make_expense, make_group


def _seed(client, session: Session):
    group, people = make_group(session, name="Trip", participants=("Alice", "+Evil"))
    make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1), (people["+Evil"], 1)],
        amount=5000,
        title="Dinner",
        category_id=9,
        expense_date=date(2026, 1, 6),
    )
    created = client.post(
        f"/api/groups/{group.id}/expenses",
        json={
            "expense_date": "2026-02-07",
            "title": "=SUM(A1)",
            "category_id": 2,
            "amount": 1000,
            "original_amount": 1000,
            "original_currency": "EUR",
            "conversion_rate": "1.5",
            "paid_by_id": people["Alice"].id,
            "split_mode": "BY_AMOUNT",
            "paid_for": [
                {"participant_id": people["Alice"].id, "amount": 400},
                {"participant_id": people["+Evil"].id, "amount": 600},
            ],
        },
    )
    assert created.status_code == 201, created.text
    make_expense(
        session,
        group=group,
        paid_by=people["+Evil"],
        paid_for=[(people["Alice"], 1)],
        amount=1000,
        title="Settlement",
        category_id=0,
        expense_date=date(2026, 3, 1),
        is_reimbursement=True,
    )
    return group, people


def test_csv_export(client, session: Session):
    group, _people = _seed(client, session)
    response = client.get(f"/api/groups/{group.id}/expenses/export.csv")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "filename*=UTF-8''" in response.headers["content-disposition"]

    text = response.text
    assert text.startswith("\ufeff")
    reader = csv.reader(io.StringIO(text.lstrip("\ufeff")))
    rows = list(reader)
    assert rows[0] == [
        "Date",
        "Description",
        "Category",
        "Currency",
        "Cost",
        "Original cost",
        "Original currency",
        "Conversion rate",
        "Is Reimbursement",
        "Split mode",
        "Alice",
        "'+Evil",
    ]
    assert rows[1] == [
        "2026-01-06",
        "Dinner",
        "Groceries",
        "USD",
        "50.00",
        "",
        "",
        "",
        "No",
        "Evenly",
        "25",
        "-25",
    ]
    assert rows[2] == [
        "2026-02-07",
        "'=SUM(A1)",
        "Entertainment",
        "USD",
        "10.00",
        "10.00",
        "EUR",
        "1.5",
        "No",
        "Unevenly \u2013 By amount",
        "4",
        "-6",
    ]
    assert rows[3][0] == "2026-03-01"
    assert rows[3][8] == "Yes"

    ranged = client.get(
        f"/api/groups/{group.id}/expenses/export.csv",
        params={"from": "2026-02-01", "to": "2026-02-28"},
    )
    ranged_rows = list(csv.reader(io.StringIO(ranged.text.lstrip("\ufeff"))))
    assert [row[0] for row in ranged_rows[1:]] == ["2026-02-07"]


def test_json_export(client, session: Session):
    group, _people = _seed(client, session)
    response = client.get(f"/api/groups/{group.id}/expenses/export.json")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers["content-disposition"]
    payload = response.json()

    assert payload["id"] == group.id
    assert payload["name"] == "Trip"
    assert payload["currency"] == "$"
    assert payload["currency_code"] == "USD"
    assert [row["expense_date"] for row in payload["expenses"]] == [
        "2026-01-06",
        "2026-02-07",
        "2026-03-01",
    ]
    second = payload["expenses"][1]
    assert second["title"] == "=SUM(A1)"
    assert second["category"] == {"grouping": "Entertainment", "name": "Entertainment"}
    assert second["conversion_rate"] == "1.5"
    assert second["original_amount"] == 1000
    assert {row["participant_id"]: row["shares"] for row in second["paid_for"]} == {
        _people["Alice"].id: 400,
        _people["+Evil"].id: 600,
    }
    assert second["created_at"].endswith("Z")
    assert payload["participants"] and payload["activities"]
    assert payload["activities"][0]["activity_type"] == "CREATE_EXPENSE"

    # Data survives a JSON round-trip (the export is valid UTF-8 JSON).
    assert json.loads(json.dumps(payload))["expenses"][0]["title"] == "Dinner"


def test_exports_missing_group(client):
    assert client.get("/api/groups/missing/expenses/export.csv").status_code == 404
    assert client.get("/api/groups/missing/expenses/export.json").status_code == 404
