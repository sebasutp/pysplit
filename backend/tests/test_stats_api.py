"""Stage 5C tests: statistics overview and drill-downs."""

from __future__ import annotations

from datetime import date

from sqlmodel import Session

from tests.helpers import make_expense, make_group


def _seed(client, session: Session):
    group, people = make_group(session, participants=("Alice", "Bob", "Carol"))
    make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1), (people["Bob"], 1)],
        amount=1000,
        title="Dinner",
        category_id=1,
        expense_date=date(2026, 1, 15),
    )
    make_expense(
        session,
        group=group,
        paid_by=people["Bob"],
        paid_for=[(people["Bob"], 1), (people["Carol"], 1)],
        amount=2000,
        title="Groceries",
        category_id=9,
        expense_date=date(2026, 2, 10),
    )
    make_expense(
        session,
        group=group,
        paid_by=people["Carol"],
        paid_for=[(people["Alice"], 1)],
        amount=500,
        title="Settlement",
        category_id=0,
        is_reimbursement=True,
        expense_date=date(2026, 2, 15),
    )
    rent = client.post(
        f"/api/groups/{group.id}/expenses",
        json={
            "expense_date": "2026-12-15",
            "title": "Rent",
            "category_id": 18,
            "amount": 3000,
            "paid_by_id": people["Alice"].id,
            "split_mode": "EVENLY",
            "recurrence_rule": "MONTHLY",
            "paid_for": [
                {"participant_id": people["Alice"].id},
                {"participant_id": people["Bob"].id},
            ],
        },
    )
    assert rent.status_code == 201, rent.text
    return group, people


def test_stats_overview(client, session: Session):
    group, people = _seed(client, session)
    response = client.get(
        f"/api/groups/{group.id}/stats",
        params={"participant_id": people["Alice"].id},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["total_group_spending"] == 6000
    assert body["totalGroupSpendings"] == 6000
    assert body["total_active_user_paid_for"] == 1000 + 3000
    assert body["total_active_user_share"] == 500 + 1500
    assert body["totalParticipantSpendings"] == 4000
    assert body["totalParticipantShare"] == 2000
    assert body["range"] == {"from": None, "to": None}

    summary = body["summary"]
    assert summary["expense_count"] == 3
    assert summary["total_spending"] == 6000
    assert summary["average_expense"] == 2000
    assert summary["largest_expense"] == {"title": "Rent", "amount": 3000}
    assert summary["first_date"] == "2026-01-15"
    assert summary["last_date"] == "2026-12-15"

    months = {row["month"]: row["total"] for row in body["spending_over_time"]}
    assert months["2026-01"] == 1000
    assert months["2026-02"] == 2000
    assert months["2026-03"] == 0
    assert months["2026-12"] == 3000
    assert len(months) == 12
    assert body["spending_over_time"][0]["period"] == "2026-01"
    assert body["spending_over_time"][0]["amount"] == 1000
    assert body["months"] == body["spending_over_time"]

    participants = {row["participant_id"]: row for row in body["spending_by_participant"]}
    assert participants[people["Bob"].id]["paid"] == 2000
    assert participants[people["Bob"].id]["paid_count"] == 1
    assert participants[people["Alice"].id]["paid"] == 4000
    assert participants[people["Alice"].id]["share"] == 2000
    assert participants[people["Alice"].id]["amount"] == 4000
    assert [row["participant_id"] for row in body["spending_by_participant"]] == [
        people["Alice"].id,
        people["Bob"].id,
        people["Carol"].id,
    ]

    categories = body["spending_by_category"]
    assert [(row["category_id"], row["amount"]) for row in categories] == [
        (18, 3000),
        (9, 2000),
        (1, 1000),
    ]

    assert body["recurring"]["active_count"] == 1
    assert body["recurring"]["monthly_amount"] == 3000
    assert body["recurring"]["yearly_amount"] == 36000
    assert body["recurring"]["by_period"] == [{"period": "MONTHLY", "count": 1, "total": 3000}]


def test_date_range(client, session: Session):
    group, people = _seed(client, session)
    response = client.get(
        f"/api/groups/{group.id}/stats",
        params={
            "participant_id": people["Alice"].id,
            "from": "2026-02-01",
            "to": "2026-02-28",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["range"] == {"from": "2026-02-01", "to": "2026-02-28"}
    assert body["total_group_spending"] == 2000
    assert body["summary"]["expense_count"] == 1
    assert body["total_active_user_share"] == 0
    assert body["total_active_user_paid_for"] == 0
    assert [row["month"] for row in body["spending_over_time"]] == ["2026-02"]
    assert [row["category_id"] for row in body["spending_by_category"]] == [9]
    assert body["recurring"]["active_count"] == 1

    assert client.get(f"/api/groups/{group.id}/stats", params={"from": "bad"}).status_code == 422
    assert client.get("/api/groups/missing/stats").status_code == 404


def test_category_drilldown(client, session: Session):
    group, _people = _seed(client, session)
    response = client.get(f"/api/groups/{group.id}/stats/categories/1/expenses")
    assert response.status_code == 200
    assert response.json()["expenses"] == [
        {
            "id": response.json()["expenses"][0]["id"],
            "title": "Dinner",
            "amount": 1000,
            "expense_date": "2026-01-15",
            "created_at": response.json()["expenses"][0]["created_at"],
        }
    ]

    ranged = client.get(
        f"/api/groups/{group.id}/stats/categories/9/expenses",
        params={"from": "2026-03-01", "to": "2026-12-31"},
    )
    assert ranged.json()["expenses"] == []
    assert (
        client.get(f"/api/groups/{group.id}/stats/categories/999/expenses").json()["expenses"] == []
    )


def test_summary_average_uses_javascript_rounding(client, session: Session):
    group, people = make_group(session)
    make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1)],
        amount=2,
        title="Two",
        expense_date=date(2026, 1, 1),
    )
    make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1)],
        amount=3,
        title="Three",
        expense_date=date(2026, 1, 2),
    )
    body = client.get(f"/api/groups/{group.id}/stats").json()
    assert body["summary"]["total_spending"] == 5
    assert body["summary"]["average_expense"] == 3


def test_month_drilldown(client, session: Session):
    group, _people = _seed(client, session)
    response = client.get(f"/api/groups/{group.id}/stats/months/2026-02/expenses")
    assert response.status_code == 200
    expenses = response.json()["expenses"]
    assert [row["title"] for row in expenses] == ["Groceries"]

    ranged = client.get(
        f"/api/groups/{group.id}/stats/months/2026-02/expenses",
        params={"from": "2026-02-11"},
    )
    assert ranged.json()["expenses"] == []
    assert (
        client.get(f"/api/groups/{group.id}/stats/months/not-a-month/expenses").status_code == 422
    )
