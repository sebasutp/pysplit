"""Expense, recurrence, document and activity business logic."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, func, update
from sqlmodel import Session, select

from app.core.enums import ActivityType, RecurrenceRule, SplitMode
from app.core.ids import new_id
from app.models.activity import Activity
from app.models.base import utc_now
from app.models.category import Category
from app.models.expense import Expense
from app.models.expense_document import ExpenseDocument
from app.models.expense_paid_for import ExpensePaidFor
from app.models.participant import Participant
from app.models.receipt import Receipt
from app.models.recurring_expense_link import RecurringExpenseLink
from app.models.sync_change import SyncChange
from app.schemas.categories import CategoryRead
from app.schemas.expenses import (
    DocumentInput,
    ExpenseCreate,
    ExpenseDocumentRead,
    ExpenseList,
    ExpensePaidForInput,
    ExpensePaidForRead,
    ExpenseRead,
    ExpenseUpdate,
    ReceiptSummary,
)
from app.services.categories import ensure_default_categories
from app.services.common import finish, require_group
from app.services.errors import ConflictError, InvalidInputError, NotFoundError
from app.utils.dates import date_to_datetime, datetime_to_date, end_of_day_exclusive, start_of_day
from app.utils.recurrence import calculate_next_date

# Write-on-read materialization is bounded so one request cannot loop over an
# arbitrarily large backlog. Remaining due frames are picked up by the next call.
MAX_RECURRENCE_FRAMES_PER_REQUEST = 100


# ---------------------------------------------------------------------------
# Validation and normalization
# ---------------------------------------------------------------------------


def _require_category(session: Session, category_id: int, *, commit: bool = True) -> Category:
    category = session.get(Category, category_id)
    if category is None:
        ensure_default_categories(session, commit=commit)
        category = session.get(Category, category_id)
    if category is None:
        raise InvalidInputError(f"Unknown category id: {category_id}", field="category_id")
    return category


def _group_participant_ids(session: Session, group_id: str) -> set[str]:
    return {
        participant_id
        for participant_id in session.exec(
            select(Participant.id).where(
                Participant.group_id == group_id,
                Participant.deleted_at.is_(None),
            )
        ).all()
    }


def _validate_participants(
    session: Session,
    group_id: str,
    paid_by_id: str,
    paid_for: list[ExpensePaidForInput],
) -> None:
    valid = _group_participant_ids(session, group_id)
    if paid_by_id not in valid:
        raise InvalidInputError("paid_by_id must belong to the group", field="paid_by_id")
    seen: set[str] = set()
    for row in paid_for:
        if row.participant_id not in valid:
            raise InvalidInputError(
                f"Participant {row.participant_id} does not belong to the group.",
                field="paid_for",
            )
        if row.participant_id in seen:
            raise InvalidInputError(
                f"Duplicate participant in paid_for: {row.participant_id}",
                field="paid_for",
            )
        seen.add(row.participant_id)


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def normalize_paid_for(
    rows: list[ExpensePaidForInput],
    split_mode: SplitMode | str,
    amount: int,
) -> list[tuple[str, int]]:
    """Normalize API input into stored integer shares.

    ``BY_AMOUNT`` accepts either ``amount`` or ``shares``. ``BY_PERCENTAGE``
    accepts ``percentage`` (0 to 100), stored basis points, or integer percentage
    ``shares``. Plain share weights are used for ``BY_SHARES``.
    """
    mode = SplitMode(str(split_mode))
    if not rows:
        raise InvalidInputError("paid_for must contain at least one participant", field="paid_for")

    if mode == SplitMode.EVENLY:
        return [(row.participant_id, 1) for row in rows]

    if mode == SplitMode.BY_AMOUNT:
        values: list[tuple[str, int]] = []
        for row in rows:
            raw: Any = row.amount if row.amount is not None else row.shares
            value = _as_decimal(raw)
            if value is None or value != value.to_integral_value():
                raise InvalidInputError("BY_AMOUNT requires integer amounts", field="paid_for")
            integer = int(value)
            if integer <= 0:
                raise InvalidInputError("noZeroShares", field="paid_for")
            values.append((row.participant_id, integer))
        if sum(value for _, value in values) != amount:
            raise InvalidInputError("amountSum", field="paid_for")
        return values

    if mode == SplitMode.BY_PERCENTAGE:
        provided = {
            row.participant_id: row.percentage for row in rows if row.percentage is not None
        }
        plain = [row for row in rows if row.percentage is None]
        plain_values = [_as_decimal(row.shares) for row in plain]
        treat_plain_as_percent = bool(plain) and all(
            value is not None and abs(value) <= 100 for value in plain_values
        )
        if treat_plain_as_percent:
            total_plain = sum(value for value in plain_values if value is not None)
            treat_plain_as_percent = total_plain <= 100

        values = []
        for row in rows:
            if row.participant_id in provided:
                value = provided[row.participant_id]
                if value is None or value <= 0:
                    raise InvalidInputError("noZeroShares", field="paid_for")
                basis_points = int((value * 100).to_integral_value())
            else:
                value = _as_decimal(row.shares)
                if value is None or value <= 0:
                    raise InvalidInputError("noZeroShares", field="paid_for")
                if treat_plain_as_percent:
                    basis_points = int((value * 100).to_integral_value())
                else:
                    if value != value.to_integral_value():
                        raise InvalidInputError(
                            "BY_PERCENTAGE shares must be percentages or basis points",
                            field="paid_for",
                        )
                    basis_points = int(value)
            values.append((row.participant_id, basis_points))
        if sum(value for _, value in values) != 10_000:
            raise InvalidInputError("percentageSum", field="paid_for")
        return values

    # BY_SHARES
    values = []
    for row in rows:
        value = _as_decimal(row.shares if row.shares is not None else 1)
        if value is None or value <= 0 or value != value.to_integral_value():
            raise InvalidInputError("noZeroShares", field="paid_for")
        values.append((row.participant_id, int(value)))
    return values


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def _document_rows(session: Session, expense_id: str) -> list[ExpenseDocument]:
    return list(
        session.exec(
            select(ExpenseDocument)
            .where(ExpenseDocument.expense_id == expense_id)
            .order_by(ExpenseDocument.created_at.asc(), ExpenseDocument.id.asc())
        ).all()
    )


def _expense_read(
    expense: Expense,
    *,
    categories: dict[int, Category],
    participants: dict[str, Participant],
    paid_for_by_expense: dict[str, list[tuple[ExpensePaidFor, Participant]]],
    documents_by_expense: dict[str, list[ExpenseDocument]],
    receipts: dict[str, Receipt],
    recurring_heads: set[str] | None = None,
) -> ExpenseRead:
    category = categories.get(expense.category_id)
    paid_by = participants.get(expense.paid_by_id)
    receipt = receipts.get(expense.id)
    return ExpenseRead(
        id=expense.id,
        group_id=expense.group_id,
        expense_date=datetime_to_date(expense.expense_date),
        title=expense.title,
        category_id=expense.category_id,
        category=(
            CategoryRead(id=int(category.id or 0), grouping=category.grouping, name=category.name)
            if category is not None
            else None
        ),
        amount=expense.amount,
        original_amount=expense.original_amount,
        original_currency=expense.original_currency,
        conversion_rate=(
            format(expense.conversion_rate, "f") if expense.conversion_rate is not None else None
        ),
        paid_by_id=expense.paid_by_id,
        paid_by_name=paid_by.name if paid_by is not None else None,
        is_reimbursement=expense.is_reimbursement,
        split_mode=SplitMode(expense.split_mode),
        notes=expense.notes,
        recurrence_rule=RecurrenceRule(expense.recurrence_rule or "NONE"),
        is_recurring_head=expense.id in (recurring_heads or set()),
        created_at=expense.created_at,
        updated_at=expense.updated_at,
        version=expense.version,
        deleted_at=expense.deleted_at,
        paid_for=[
            ExpensePaidForRead(
                participant_id=row.participant_id,
                shares=row.shares,
                participant_name=participant.name if participant is not None else None,
            )
            for row, participant in paid_for_by_expense.get(expense.id, [])
        ],
        documents=[
            ExpenseDocumentRead(
                id=document.id,
                url=document.url,
                width=document.width,
                height=document.height,
            )
            for document in documents_by_expense.get(expense.id, [])
        ],
        receipt=ReceiptSummary(id=receipt.id, status=receipt.status) if receipt else None,
    )


def expenses_to_read(session: Session, expenses: list[Expense]) -> list[ExpenseRead]:
    """Serialize many expenses with a constant number of batched queries."""
    if not expenses:
        return []

    expense_ids = [expense.id for expense in expenses]

    categories: dict[int, Category] = {}
    category_ids = {expense.category_id for expense in expenses}
    if category_ids:
        categories = {
            int(category.id or 0): category
            for category in session.exec(
                select(Category).where(Category.id.in_(category_ids))
            ).all()
        }

    paid_for_rows = session.exec(
        select(ExpensePaidFor, Participant)
        .join(Participant, Participant.id == ExpensePaidFor.participant_id)
        .where(ExpensePaidFor.expense_id.in_(expense_ids))
        .order_by(ExpensePaidFor.expense_id.asc(), ExpensePaidFor.participant_id.asc())
    ).all()
    paid_for_by_expense: dict[str, list[tuple[ExpensePaidFor, Participant]]] = {}
    participant_ids = {expense.paid_by_id for expense in expenses}
    for row, participant in paid_for_rows:
        paid_for_by_expense.setdefault(row.expense_id, []).append((row, participant))
        participant_ids.add(row.participant_id)

    participants: dict[str, Participant] = {}
    if participant_ids:
        participants = {
            participant.id: participant
            for participant in session.exec(
                select(Participant).where(Participant.id.in_(participant_ids))
            ).all()
        }

    documents_by_expense: dict[str, list[ExpenseDocument]] = {}
    for document in session.exec(
        select(ExpenseDocument)
        .where(ExpenseDocument.expense_id.in_(expense_ids))
        .order_by(ExpenseDocument.created_at.asc(), ExpenseDocument.id.asc())
    ).all():
        if document.expense_id is not None:
            documents_by_expense.setdefault(document.expense_id, []).append(document)

    receipts: dict[str, Receipt] = {}
    for receipt in session.exec(select(Receipt).where(Receipt.expense_id.in_(expense_ids))).all():
        if receipt.expense_id is not None:
            receipts.setdefault(receipt.expense_id, receipt)

    recurring_heads = {
        link.current_frame_expense_id
        for link in session.exec(
            select(RecurringExpenseLink).where(
                RecurringExpenseLink.current_frame_expense_id.in_(expense_ids),
                RecurringExpenseLink.next_expense_created_at.is_(None),
            )
        ).all()
    }

    return [
        _expense_read(
            expense,
            categories=categories,
            participants=participants,
            paid_for_by_expense=paid_for_by_expense,
            documents_by_expense=documents_by_expense,
            receipts=receipts,
            recurring_heads=recurring_heads,
        )
        for expense in expenses
    ]


def expense_to_read(session: Session, expense: Expense) -> ExpenseRead:
    """Serialize a single expense; prefer ``expenses_to_read`` in loops."""
    return expenses_to_read(session, [expense])[0]


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def _title_filter(query: str) -> Any:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return Expense.title.ilike(f"%{escaped}%", escape="\\")


def list_expenses(
    session: Session,
    group_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
    date_from: date | None = None,
    date_to: date | None = None,
    query: str | None = None,
) -> ExpenseList:
    require_group(session, group_id)
    materialize_due_recurring_expenses(session, group_id=group_id)

    conditions: list[Any] = [
        Expense.group_id == group_id,
        Expense.deleted_at.is_(None),
    ]
    if date_from is not None:
        conditions.append(Expense.expense_date >= start_of_day(date_from))
    if date_to is not None:
        conditions.append(Expense.expense_date < end_of_day_exclusive(date_to))
    if query and query.strip():
        conditions.append(_title_filter(query.strip()))

    total = int(session.exec(select(func.count()).select_from(Expense).where(*conditions)).one())
    expenses = list(
        session.exec(
            select(Expense)
            .where(*conditions)
            .order_by(Expense.expense_date.desc(), Expense.created_at.desc(), Expense.id.asc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return ExpenseList(
        items=expenses_to_read(session, expenses),
        total=total,
        limit=limit,
        offset=offset,
    )


def get_expense(session: Session, group_id: str, expense_id: str) -> ExpenseRead:
    require_group(session, group_id)
    materialize_due_recurring_expenses(session, group_id=group_id)
    expense = session.get(Expense, expense_id)
    if expense is None or expense.group_id != group_id or expense.deleted_at is not None:
        raise NotFoundError("expense not found")
    return expense_to_read(session, expense)


def group_expense_snapshot(session: Session, group_id: str) -> list[dict[str, Any]]:
    """Return the flat expense shape used by balances, stats and exports."""
    expenses = list(
        session.exec(
            select(Expense)
            .where(Expense.group_id == group_id, Expense.deleted_at.is_(None))
            .order_by(Expense.expense_date.desc(), Expense.created_at.desc(), Expense.id.asc())
        ).all()
    )
    if not expenses:
        return []

    expense_ids = [expense.id for expense in expenses]
    paid_for_rows = session.exec(
        select(ExpensePaidFor).where(ExpensePaidFor.expense_id.in_(expense_ids))
    ).all()
    paid_for_by_expense: dict[str, list[dict[str, Any]]] = {}
    for row in paid_for_rows:
        paid_for_by_expense.setdefault(row.expense_id, []).append(
            {"participant_id": row.participant_id, "shares": row.shares}
        )

    categories = {
        int(category.id or 0): category for category in session.exec(select(Category)).all()
    }
    return [
        {
            "id": expense.id,
            "group_id": expense.group_id,
            "expense_date": expense.expense_date,
            "title": expense.title,
            "amount": expense.amount,
            "original_amount": expense.original_amount,
            "original_currency": expense.original_currency,
            "conversion_rate": (
                format(expense.conversion_rate, "f")
                if expense.conversion_rate is not None
                else None
            ),
            "category_id": expense.category_id,
            "category": (
                {
                    "id": int(categories[expense.category_id].id or 0),
                    "grouping": categories[expense.category_id].grouping,
                    "name": categories[expense.category_id].name,
                }
                if expense.category_id in categories
                else None
            ),
            "paid_by_id": expense.paid_by_id,
            "paid_for": paid_for_by_expense.get(expense.id, []),
            "is_reimbursement": expense.is_reimbursement,
            "split_mode": expense.split_mode,
            "recurrence_rule": expense.recurrence_rule or "NONE",
            "created_at": expense.created_at,
            "notes": expense.notes,
        }
        for expense in expenses
    ]


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


def _attach_documents(
    session: Session,
    expense_id: str,
    documents: list[DocumentInput],
    *,
    replace: bool,
    now: datetime,
) -> None:
    existing = {document.id: document for document in _document_rows(session, expense_id)}
    desired: list[tuple[str, DocumentInput]] = []
    seen: set[str] = set()
    for document in documents:
        document_id = document.id or new_id("doc")
        if document_id in seen:
            raise InvalidInputError(f"Duplicate document id: {document_id}", field="documents")
        seen.add(document_id)
        desired.append((document_id, document))

    if replace:
        for document_id, document in existing.items():
            if document_id not in seen:
                session.delete(document)

    for document_id, document in desired:
        current = existing.get(document_id) or session.get(ExpenseDocument, document_id)
        if current is None:
            current = ExpenseDocument(
                id=document_id,
                url=document.url,
                width=document.width,
                height=document.height,
                expense_id=expense_id,
                created_at=now,
                updated_at=now,
                version=1,
            )
            session.add(current)
            continue
        if current.expense_id not in (None, expense_id):
            raise ConflictError(f"Document {document_id} belongs to another expense")
        current.expense_id = expense_id
        current.url = document.url
        current.width = document.width
        current.height = document.height
        current.updated_at = now
        current.version += 1
        session.add(current)


def _create_recurring_link(
    session: Session,
    expense: Expense,
    rule: RecurrenceRule | str,
    *,
    now: datetime,
) -> RecurringExpenseLink:
    link = RecurringExpenseLink(
        id=new_id("rec"),
        group_id=expense.group_id,
        current_frame_expense_id=expense.id,
        next_expense_created_at=None,
        next_expense_date=calculate_next_date(str(rule), expense.expense_date),
        updated_at=now,
        version=1,
    )
    session.add(link)
    expense.recurring_expense_link_id = link.id
    session.add(expense)
    return link


def create_expense(
    session: Session,
    group_id: str,
    payload: ExpenseCreate,
    *,
    now: datetime | None = None,
    commit: bool = True,
) -> ExpenseRead:
    moment = now or utc_now()
    require_group(session, group_id)

    if payload.id:
        existing = session.get(Expense, payload.id)
        if existing is not None:
            if existing.group_id != group_id or existing.deleted_at is not None:
                raise ConflictError("expense id already exists")
            return expense_to_read(session, existing)

    _require_category(session, payload.category_id, commit=commit)
    _validate_participants(session, group_id, payload.paid_by_id, payload.paid_for)
    normalized = normalize_paid_for(payload.paid_for, payload.split_mode, payload.amount)

    expense = Expense(
        id=payload.id or new_id("exp"),
        group_id=group_id,
        expense_date=date_to_datetime(payload.expense_date),
        title=payload.title,
        category_id=payload.category_id,
        amount=payload.amount,
        original_amount=payload.original_amount,
        original_currency=payload.original_currency,
        conversion_rate=payload.conversion_rate,
        paid_by_id=payload.paid_by_id,
        is_reimbursement=payload.is_reimbursement,
        split_mode=str(payload.split_mode),
        notes=payload.notes,
        recurrence_rule=str(payload.recurrence_rule),
        created_at=moment,
        updated_at=moment,
        version=1,
    )
    session.add(expense)
    session.flush()

    for participant_id, shares in normalized:
        session.add(
            ExpensePaidFor(
                expense_id=expense.id,
                participant_id=participant_id,
                shares=shares,
                updated_at=moment,
                version=1,
            )
        )

    _attach_documents(session, expense.id, payload.documents, replace=False, now=moment)

    if payload.recurrence_rule != RecurrenceRule.NONE:
        _create_recurring_link(session, expense, payload.recurrence_rule, now=moment)

    session.add(
        Activity(
            id=new_id("act"),
            group_id=group_id,
            time=moment,
            activity_type=ActivityType.CREATE_EXPENSE.value,
            participant_id=payload.participant_id,
            expense_id=expense.id,
            data=payload.title,
        )
    )
    finish(session, commit)
    if commit:
        session.refresh(expense)
    return expense_to_read(session, expense)


def update_expense(
    session: Session,
    group_id: str,
    expense_id: str,
    payload: ExpenseUpdate,
    *,
    now: datetime | None = None,
    commit: bool = True,
) -> ExpenseRead:
    moment = now or utc_now()
    require_group(session, group_id)
    expense = session.get(Expense, expense_id)
    if expense is None or expense.group_id != group_id or expense.deleted_at is not None:
        raise NotFoundError("expense not found")

    if payload.base_version is not None and payload.base_version != expense.version:
        raise ConflictError("expense version conflict")

    fields = payload.model_dump(exclude_unset=True)
    non_nullable = {
        "expense_date",
        "title",
        "category_id",
        "amount",
        "paid_by_id",
        "is_reimbursement",
        "split_mode",
        "recurrence_rule",
        "paid_for",
        "documents",
    }
    for field in non_nullable:
        if field in fields and fields[field] is None:
            raise InvalidInputError(f"{field} cannot be null", field=field)

    prior_expense_date = expense.expense_date
    new_split_mode = fields.get("split_mode", expense.split_mode)
    if "split_mode" in fields and "paid_for" not in fields:
        raise InvalidInputError("paid_for is required when changing split_mode", field="paid_for")

    if "paid_for" in fields:
        # Pydantic has already replaced the list with ExpensePaidForInput rows.
        paid_for_payload = payload.paid_for or []
        paid_by_id = payload.paid_by_id or expense.paid_by_id
        _validate_participants(session, group_id, paid_by_id, paid_for_payload)
        normalized = normalize_paid_for(
            paid_for_payload,
            new_split_mode,
            int(fields.get("amount", expense.amount)),
        )
    else:
        normalized = None

    if (
        normalized is None
        and "amount" in fields
        and str(expense.split_mode) == SplitMode.BY_AMOUNT.value
    ):
        stored_total = sum(
            row.shares
            for row in session.exec(
                select(ExpensePaidFor).where(ExpensePaidFor.expense_id == expense.id)
            ).all()
        )
        if stored_total != int(fields["amount"]):
            raise InvalidInputError(
                "amountSum: paid_for must be supplied when changing a BY_AMOUNT amount",
                field="paid_for",
            )

    if "paid_by_id" in fields:
        _validate_participants(
            session,
            group_id,
            str(fields["paid_by_id"]),
            payload.paid_for or [],
        )
    if "category_id" in fields:
        _require_category(session, int(fields["category_id"]), commit=commit)

    if "expense_date" in fields:
        expense.expense_date = date_to_datetime(payload.expense_date)  # type: ignore[arg-type]
    for field in (
        "title",
        "category_id",
        "amount",
        "original_amount",
        "original_currency",
        "conversion_rate",
        "paid_by_id",
        "is_reimbursement",
        "split_mode",
        "notes",
    ):
        if field in fields:
            value = fields[field]
            setattr(expense, field, str(value) if field == "split_mode" else value)

    if normalized is not None:
        session.execute(delete(ExpensePaidFor).where(ExpensePaidFor.expense_id == expense.id))
        for participant_id, shares in normalized:
            session.add(
                ExpensePaidFor(
                    expense_id=expense.id,
                    participant_id=participant_id,
                    shares=shares,
                    updated_at=moment,
                    version=1,
                )
            )

    if payload.documents is not None:
        _attach_documents(session, expense.id, payload.documents, replace=True, now=moment)

    if "recurrence_rule" in fields:
        new_rule = str(fields["recurrence_rule"])
        existing_rule = expense.recurrence_rule or RecurrenceRule.NONE.value
        if new_rule != existing_rule:
            link = session.exec(
                select(RecurringExpenseLink).where(
                    RecurringExpenseLink.current_frame_expense_id == expense.id
                )
            ).first()
            if link is not None and link.next_expense_created_at is not None:
                raise ConflictError("recurring expense rule cannot change after materialization")
            if new_rule != RecurrenceRule.NONE.value:
                if link is None:
                    _create_recurring_link(session, expense, new_rule, now=moment)
                else:
                    link.next_expense_date = calculate_next_date(new_rule, prior_expense_date)
                    link.updated_at = moment
                    link.version += 1
                    session.add(link)
            elif existing_rule != RecurrenceRule.NONE.value and link is not None:
                session.delete(link)
                expense.recurring_expense_link_id = None
        expense.recurrence_rule = new_rule

    expense.updated_at = moment
    expense.version += 1
    session.add(expense)
    session.add(
        Activity(
            id=new_id("act"),
            group_id=group_id,
            time=moment,
            activity_type=ActivityType.UPDATE_EXPENSE.value,
            participant_id=payload.participant_id,
            expense_id=expense.id,
            data=expense.title,
        )
    )
    finish(session, commit)
    if commit:
        session.refresh(expense)
    return expense_to_read(session, expense)


def delete_expense(
    session: Session,
    group_id: str,
    expense_id: str,
    *,
    participant_id: str | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> None:
    moment = now or utc_now()
    require_group(session, group_id)
    expense = session.get(Expense, expense_id)
    if expense is None or expense.group_id != group_id or expense.deleted_at is not None:
        raise NotFoundError("expense not found")

    expense.deleted_at = moment
    expense.updated_at = moment
    expense.version += 1
    expense.recurring_expense_link_id = None
    session.add(expense)

    session.execute(
        update(ExpenseDocument)
        .where(ExpenseDocument.expense_id == expense.id)
        .values(expense_id=None, updated_at=moment, version=ExpenseDocument.version + 1)
    )
    session.execute(
        update(Receipt)
        .where(Receipt.expense_id == expense.id)
        .values(expense_id=None, updated_at=moment, version=Receipt.version + 1)
    )
    session.execute(
        delete(RecurringExpenseLink).where(
            RecurringExpenseLink.current_frame_expense_id == expense.id
        )
    )
    session.add(
        Activity(
            id=new_id("act"),
            group_id=group_id,
            time=moment,
            activity_type=ActivityType.DELETE_EXPENSE.value,
            participant_id=participant_id,
            expense_id=expense.id,
            data=expense.title,
        )
    )
    finish(session, commit)


# ---------------------------------------------------------------------------
# Recurrence materialization
# ---------------------------------------------------------------------------


def materialize_due_recurring_expenses(
    session: Session,
    *,
    group_id: str | None = None,
    now: datetime | None = None,
) -> int:
    """Create due recurring frames exactly once.

    Returns the number of frames created. The reference materializes at the
    start of expense reads; materialization copies the frame's fields,
    participants and documents, closes the old link and opens a new one. Each
    call creates at most ``MAX_RECURRENCE_FRAMES_PER_REQUEST`` frames and
    commits once; a larger backlog is finished by subsequent calls.
    """
    moment = now or utc_now()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    moment = moment.astimezone(UTC)
    cutoff = moment.replace(second=0, microsecond=0)

    conditions = [
        RecurringExpenseLink.next_expense_created_at.is_(None),
        RecurringExpenseLink.next_expense_date <= cutoff,
    ]
    if group_id is not None:
        conditions.append(RecurringExpenseLink.group_id == group_id)
    due_links = list(
        session.exec(
            select(RecurringExpenseLink)
            .where(*conditions)
            .order_by(
                RecurringExpenseLink.next_expense_date.asc(),
                RecurringExpenseLink.id.asc(),
            )
        ).all()
    )

    created = 0
    for initial_link in due_links:
        if created >= MAX_RECURRENCE_FRAMES_PER_REQUEST:
            break
        link_id = initial_link.id
        for _ in range(MAX_RECURRENCE_FRAMES_PER_REQUEST):
            if created >= MAX_RECURRENCE_FRAMES_PER_REQUEST:
                break
            link = session.get(RecurringExpenseLink, link_id)
            if link is None or link.next_expense_created_at is not None:
                break
            if link.next_expense_date >= cutoff:
                break

            current = session.get(Expense, link.current_frame_expense_id)
            if current is None or current.deleted_at is not None:
                break
            rule = current.recurrence_rule or RecurrenceRule.NONE.value
            if rule == RecurrenceRule.NONE.value:
                break

            new_date = link.next_expense_date
            next_date = calculate_next_date(rule, new_date)
            if next_date <= new_date:
                break

            new_expense = Expense(
                id=new_id("exp"),
                group_id=current.group_id,
                expense_date=new_date,
                title=current.title,
                category_id=current.category_id,
                amount=current.amount,
                original_amount=current.original_amount,
                original_currency=current.original_currency,
                conversion_rate=current.conversion_rate,
                paid_by_id=current.paid_by_id,
                is_reimbursement=current.is_reimbursement,
                split_mode=current.split_mode,
                notes=current.notes,
                recurrence_rule=current.recurrence_rule,
                created_at=current.created_at,
                updated_at=moment,
                version=1,
            )
            session.add(new_expense)
            session.flush()

            new_link = RecurringExpenseLink(
                id=new_id("rec"),
                group_id=current.group_id,
                current_frame_expense_id=new_expense.id,
                next_expense_created_at=None,
                next_expense_date=next_date,
                updated_at=moment,
                version=1,
            )
            new_expense.recurring_expense_link_id = new_link.id
            session.add(new_expense)
            session.add(new_link)

            for row in session.exec(
                select(ExpensePaidFor).where(ExpensePaidFor.expense_id == current.id)
            ).all():
                session.add(
                    ExpensePaidFor(
                        expense_id=new_expense.id,
                        participant_id=row.participant_id,
                        shares=row.shares,
                        updated_at=moment,
                        version=1,
                    )
                )

            session.execute(
                update(ExpenseDocument)
                .where(ExpenseDocument.expense_id == current.id)
                .values(
                    expense_id=new_expense.id,
                    updated_at=moment,
                    version=ExpenseDocument.version + 1,
                )
            )

            # Recurrence is materialized server-side, so the new frame must
            # also be visible to clients that only consume the change feed.
            session.flush()
            snapshot = expense_to_read(session, new_expense).model_dump(mode="json")
            session.add(
                SyncChange(
                    group_id=new_expense.group_id,
                    entity_type="expense",
                    entity_id=new_expense.id,
                    op_type="create",
                    payload_json=json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
                    user_id=None,
                    changed_at=moment,
                )
            )

            result = session.execute(
                update(RecurringExpenseLink)
                .where(
                    RecurringExpenseLink.id == link.id,
                    RecurringExpenseLink.next_expense_created_at.is_(None),
                )
                .values(
                    next_expense_created_at=new_expense.created_at,
                    updated_at=moment,
                    version=RecurringExpenseLink.version + 1,
                )
            )
            if result.rowcount != 1:
                # Another writer closed this link first; discard the whole
                # batch so the next read retries from the current links.
                session.rollback()
                return 0

            created += 1
            link_id = new_link.id
            if new_link.next_expense_date >= cutoff:
                break

    if created:
        session.commit()
    return created


def active_recurring_expenses(session: Session, group_id: str) -> list[Expense]:
    materialize_due_recurring_expenses(session, group_id=group_id)
    return list(
        session.exec(
            select(Expense)
            .join(
                RecurringExpenseLink,
                RecurringExpenseLink.current_frame_expense_id == Expense.id,
            )
            .where(
                Expense.group_id == group_id,
                Expense.deleted_at.is_(None),
                Expense.is_reimbursement.is_(False),
                Expense.recurrence_rule != RecurrenceRule.NONE.value,
                RecurringExpenseLink.next_expense_created_at.is_(None),
            )
            .order_by(Expense.amount.desc())
        ).all()
    )
