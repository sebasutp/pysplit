"""Stage 5C tests: activity feed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from app.models.activity import Activity
from tests.helpers import make_expense, make_group


def test_list_activities(client, session: Session):
    group, people = make_group(session)
    expense = make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1)],
        amount=1000,
        title="Dinner",
    )
    base = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    session.add_all(
        [
            Activity(
                id="activity-1",
                group_id=group.id,
                time=base,
                activity_type="CREATE_EXPENSE",
                participant_id=people["Alice"].id,
                expense_id=expense.id,
                data="Dinner",
            ),
            Activity(
                id="activity-2",
                group_id=group.id,
                time=base + timedelta(minutes=1),
                activity_type="UPDATE_EXPENSE",
                expense_id=expense.id,
                data="Dinner edited",
            ),
            Activity(
                id="activity-3",
                group_id=group.id,
                time=base + timedelta(minutes=2),
                activity_type="DELETE_EXPENSE",
                expense_id="orphan-expense",
                data="Gone",
            ),
        ]
    )
    session.commit()

    first = client.get(f"/api/groups/{group.id}/activities", params={"limit": 2})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["total"] == 3
    assert body["has_more"] is True
    assert body["next_cursor"] == "2"
    assert [item["id"] for item in body["items"]] == ["activity-3", "activity-2"]
    assert body["items"][0]["expense"] is None
    assert body["items"][1]["expense"]["title"] == "Dinner"

    second = client.get(
        f"/api/groups/{group.id}/activities",
        params={"cursor": 2, "limit": 2},
    ).json()
    assert second["has_more"] is False
    assert [item["id"] for item in second["items"]] == ["activity-1"]
    assert second["items"][0]["expense"]["id"] == expense.id
    assert second["items"][0]["data"] == "Dinner"

    assert client.get("/api/groups/missing/activities").status_code == 404
    assert (
        client.get(f"/api/groups/{group.id}/activities", params={"cursor": -1}).status_code == 422
    )
