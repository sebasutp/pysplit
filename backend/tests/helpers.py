"""Small helpers shared by Stage 4 test modules."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import Settings, get_settings
from app.core.enums import UserTier
from app.core.ids import new_id
from app.core.security import create_access_token
from app.models.expense import Expense
from app.models.expense_paid_for import ExpensePaidFor
from app.models.group import Group
from app.models.participant import Participant
from app.models.receipt import Receipt
from app.models.receipt_item import ReceiptItem
from app.models.receipt_item_portion import ReceiptItemPortion
from app.models.receipt_opt_out import ReceiptOptOut
from app.models.user import User
from app.services.categories import ensure_default_categories
from app.utils.dates import date_to_datetime


def make_user(
    session: Session,
    *,
    email: str | None = None,
    name: str = "Test User",
    tier: UserTier = UserTier.SYNC_USERS,
    image: str | None = None,
) -> User:
    user = User(
        id=new_id("usr"),
        email=email or f"user-{uuid4().hex}@example.com",
        name=name,
        image=image,
        tier=tier.value,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def access_headers(
    user: User,
    *,
    settings: Settings | None = None,
    ttl_seconds: int = 900,
) -> dict[str, str]:
    active = settings or get_settings()
    token = create_access_token(
        user.id,
        secret=active.jwt_secret,
        ttl_seconds=ttl_seconds,
    )
    return {"Authorization": f"Bearer {token}"}


def csrf_headers(
    client: TestClient,
    *,
    origin: str = "http://testserver",
) -> dict[str, str]:
    token = client.cookies.get("pysplit_csrf") or ""
    return {"Origin": origin, "X-CSRF-Token": token}


def mock_login(
    client: TestClient,
    *,
    email: str,
    name: str = "Test User",
    tier: UserTier | None = None,
    origin: str = "http://testserver",
):
    body: dict[str, str] = {"email": email, "name": name}
    if tier is not None:
        body["tier"] = tier.value
    return client.post(
        "/api/auth/mock-login",
        json=body,
        headers={"Origin": origin},
    )


def make_group(
    session: Session,
    *,
    group_id: str | None = None,
    name: str = "Test Group",
    currency: str = "$",
    currency_code: str | None = "USD",
    participants: tuple[str, ...] = ("Alice", "Bob"),
    information: str | None = None,
) -> tuple[Group, dict[str, Participant]]:
    """Create a group directly, returning it and participants by name."""
    now = datetime.now(UTC)
    group = Group(
        id=group_id or new_id("grp"),
        name=name,
        information=information,
        currency=currency,
        currency_code=currency_code,
        created_at=now,
        updated_at=now,
        version=1,
    )
    session.add(group)
    session.flush()
    by_name: dict[str, Participant] = {}
    for participant_name in participants:
        participant = Participant(
            id=new_id("par"),
            name=participant_name,
            group_id=group.id,
            updated_at=now,
            version=1,
        )
        session.add(participant)
        by_name[participant_name] = participant
    session.commit()
    session.refresh(group)
    return group, by_name


def make_expense(
    session: Session,
    *,
    group: Group,
    paid_by: Participant,
    paid_for: list[tuple[Participant, int]],
    amount: int,
    expense_date: date | None = None,
    title: str = "Expense",
    category_id: int = 0,
    split_mode: str = "EVENLY",
    is_reimbursement: bool = False,
    recurrence_rule: str = "NONE",
    original_amount: int | None = None,
    original_currency: str | None = None,
    conversion_rate=None,
    notes: str | None = None,
    expense_id: str | None = None,
) -> Expense:
    ensure_default_categories(session)
    now = datetime.now(UTC)
    moment = date_to_datetime(expense_date or date(2026, 1, 1))
    expense = Expense(
        id=expense_id or new_id("exp"),
        group_id=group.id,
        expense_date=moment,
        title=title,
        category_id=category_id,
        amount=amount,
        original_amount=original_amount,
        original_currency=original_currency,
        conversion_rate=conversion_rate,
        paid_by_id=paid_by.id,
        is_reimbursement=is_reimbursement,
        split_mode=split_mode,
        notes=notes,
        recurrence_rule=recurrence_rule,
        created_at=moment,
        updated_at=now,
        version=1,
    )
    session.add(expense)
    session.flush()
    for participant, shares in paid_for:
        session.add(
            ExpensePaidFor(
                expense_id=expense.id,
                participant_id=participant.id,
                shares=shares,
                updated_at=now,
                version=1,
            )
        )
    session.commit()
    session.refresh(expense)
    return expense


def make_receipt(
    session: Session,
    *,
    group: Group,
    items: list[dict],
    opt_outs: tuple[str, ...] = (),
    status: str = "EXTRACTED",
    image_url: str | None = None,
    total: int | None = None,
    expense_id: str | None = None,
) -> Receipt:
    """Insert a receipt with ordered items, portions and opt-outs.

    This bypasses the AI path so receipt/apply tests are deterministic and
    never touch the network.
    """
    now = datetime.now(UTC)
    receipt = Receipt(
        id=new_id("rcpt"),
        group_id=group.id,
        image_url=image_url or f"https://uploads.example.com/{uuid4().hex}.png",
        status=status,
        total=total,
        expense_id=expense_id,
        created_at=now,
        updated_at=now,
        version=1,
    )
    session.add(receipt)
    session.flush()
    for index, item in enumerate(items):
        item_id = new_id("ritem")
        session.add(
            ReceiptItem(
                id=item_id,
                receipt_id=receipt.id,
                name=item.get("name", f"Item {index}"),
                quantity_milli=int(item.get("quantity_milli", 1000)),
                unit_price=item.get("unit_price"),
                amount=int(item["amount"]),
                is_shared=bool(item.get("is_shared", False)),
                is_adjustment=bool(item.get("is_adjustment", False)),
                position=int(item.get("position", index)),
                created_at=now,
                updated_at=now,
                version=1,
            )
        )
        for portion in item.get("portions", []):
            target = portion.get("target", "PARTICIPANT")
            session.add(
                ReceiptItemPortion(
                    id=new_id("rport"),
                    item_id=item_id,
                    target=target,
                    participant_id=(
                        None
                        if target == "SHARED"
                        else (portion.get("participant_id") or portion.get("participant"))
                    ),
                    quantity_milli=int(portion.get("quantity_milli", 1000)),
                    created_at=now,
                    updated_at=now,
                    version=1,
                )
            )
    for participant_id in opt_outs:
        session.add(
            ReceiptOptOut(
                id=new_id("ropt"),
                receipt_id=receipt.id,
                participant_id=participant_id,
                created_at=now,
                updated_at=now,
                version=1,
            )
        )
    if total is None:
        receipt.total = sum(int(item["amount"]) for item in items)
        session.add(receipt)
    session.commit()
    session.refresh(receipt)
    return receipt
