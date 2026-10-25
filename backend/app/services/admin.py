"""Admin dashboard queries and mutations.

Only administrators reach these functions (enforced by the router dependency).
Group/user deletion relies on SQLite foreign keys with ``ON DELETE CASCADE``.
"""

from __future__ import annotations

from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.core.enums import USER_TIERS, UserTier, normalize_user_tier
from app.core.ids import new_id
from app.core.validation import normalize_email
from app.models.account import Account
from app.models.base import utc_now
from app.models.expense import Expense
from app.models.group import Group
from app.models.participant import Participant
from app.models.user import User
from app.models.user_group import UserGroup
from app.schemas.admin import (
    AdminGroupList,
    AdminGroupRead,
    AdminMetrics,
    AdminUserList,
    AdminUserRead,
    PreAuthorizeResponse,
    TierCounts,
    TierUpdateResponse,
)
from app.services.errors import NotFoundError


def _admin_users(session: Session, users: list[User]) -> list[AdminUserRead]:
    if not users:
        return []
    user_ids = [user.id for user in users]
    providers_by_user: dict[str, list[str]] = {}
    for user_id, provider in session.exec(
        select(Account.user_id, Account.provider).where(Account.user_id.in_(user_ids))
    ).all():
        providers_by_user.setdefault(user_id, []).append(provider)
    groups_by_user = {
        user_id: int(count)
        for user_id, count in session.exec(
            select(UserGroup.user_id, func.count())
            .where(UserGroup.user_id.in_(user_ids))
            .group_by(UserGroup.user_id)
        ).all()
    }
    return [
        AdminUserRead(
            id=user.id,
            name=user.name,
            email=user.email,
            image=user.image,
            tier=normalize_user_tier(user.tier),
            created_at=user.created_at,
            providers=sorted(set(providers_by_user.get(user.id, []))),
            groups_count=groups_by_user.get(user.id, 0),
        )
        for user in users
    ]


def _admin_user(session: Session, user: User) -> AdminUserRead:
    return _admin_users(session, [user])[0]


def get_metrics(session: Session) -> AdminMetrics:
    total_groups = session.exec(select(func.count()).select_from(Group)).one()
    total_expenses = session.exec(select(func.count()).select_from(Expense)).one()
    total_users = session.exec(select(func.count()).select_from(User)).one()
    rows = session.exec(select(User.tier, func.count()).group_by(User.tier)).all()

    counts = {tier.value: 0 for tier in USER_TIERS}
    for tier, count in rows:
        key = normalize_user_tier(tier).value
        counts[key] += int(count)

    return AdminMetrics(
        total_groups=int(total_groups),
        total_expenses=int(total_expenses),
        total_users=int(total_users),
        tier_counts=TierCounts(**counts),
    )


def list_users(
    session: Session,
    *,
    query: str | None = None,
    tier: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> AdminUserList:
    conditions = []
    if query and query.strip():
        needle = f"%{query.strip()}%"
        conditions.append(or_(User.name.ilike(needle), User.email.ilike(needle)))
    if tier and tier != "all" and tier in {value.value for value in USER_TIERS}:
        conditions.append(User.tier == tier)

    statement = select(User)
    count_statement = select(func.count()).select_from(User)
    if conditions:
        statement = statement.where(*conditions)
        count_statement = count_statement.where(*conditions)

    total = int(session.exec(count_statement).one())
    users = session.exec(
        statement.order_by(User.created_at.desc()).offset(offset).limit(limit)
    ).all()

    return AdminUserList(
        items=_admin_users(session, list(users)),
        total=total,
        limit=limit,
        offset=offset,
    )


def preauthorize_user(
    session: Session,
    *,
    email: str,
    tier: UserTier = UserTier.GROUP_CREATORS,
    name: str | None = None,
) -> PreAuthorizeResponse:
    address = normalize_email(email)
    existing = session.exec(select(User).where(func.lower(User.email) == address)).first()

    if existing is not None:
        existing.tier = tier.value
        if not existing.name and name and name.strip():
            existing.name = name.strip()
        existing.updated_at = utc_now()
        existing.version += 1
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return PreAuthorizeResponse(user=_admin_user(session, existing), is_new=False)

    user = User(
        id=new_id("usr"),
        email=address,
        name=name.strip() if name and name.strip() else None,
        tier=tier.value,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return PreAuthorizeResponse(user=_admin_user(session, user), is_new=True)


def update_user_tier(
    session: Session,
    *,
    user_id: str,
    tier: UserTier,
) -> TierUpdateResponse:
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError("user not found")
    user.tier = tier.value
    user.updated_at = utc_now()
    user.version += 1
    session.add(user)
    session.commit()
    return TierUpdateResponse(id=user.id, tier=normalize_user_tier(user.tier))


def delete_user(session: Session, *, user_id: str) -> None:
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError("user not found")
    session.delete(user)
    session.commit()


def list_groups(
    session: Session,
    *,
    query: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> AdminGroupList:
    conditions = []
    if query and query.strip():
        needle = f"%{query.strip()}%"
        conditions.append(or_(Group.name.ilike(needle), Group.id.ilike(needle)))

    statement = select(Group)
    count_statement = select(func.count()).select_from(Group)
    if conditions:
        statement = statement.where(*conditions)
        count_statement = count_statement.where(*conditions)

    total = int(session.exec(count_statement).one())
    groups = session.exec(
        statement.order_by(Group.created_at.desc()).offset(offset).limit(limit)
    ).all()

    items: list[AdminGroupRead] = []
    group_ids = [group.id for group in groups]
    participants_by_group: dict[str, int] = {}
    expenses_by_group: dict[str, int] = {}
    users_by_group: dict[str, int] = {}
    if group_ids:
        participants_by_group = {
            group_id: int(count)
            for group_id, count in session.exec(
                select(Participant.group_id, func.count())
                .where(Participant.group_id.in_(group_ids))
                .group_by(Participant.group_id)
            ).all()
        }
        expenses_by_group = {
            group_id: int(count)
            for group_id, count in session.exec(
                select(Expense.group_id, func.count())
                .where(Expense.group_id.in_(group_ids))
                .group_by(Expense.group_id)
            ).all()
        }
        users_by_group = {
            group_id: int(count)
            for group_id, count in session.exec(
                select(UserGroup.group_id, func.count())
                .where(UserGroup.group_id.in_(group_ids))
                .group_by(UserGroup.group_id)
            ).all()
        }
    for group in groups:
        items.append(
            AdminGroupRead(
                id=group.id,
                name=group.name,
                currency=group.currency,
                currency_code=group.currency_code,
                created_at=group.created_at,
                participants_count=participants_by_group.get(group.id, 0),
                expenses_count=expenses_by_group.get(group.id, 0),
                synced_users_count=users_by_group.get(group.id, 0),
            )
        )

    return AdminGroupList(items=items, total=total, limit=limit, offset=offset)


def delete_group(session: Session, *, group_id: str) -> None:
    group = session.get(Group, group_id)
    if group is None:
        raise NotFoundError("group not found")
    session.delete(group)
    session.commit()
