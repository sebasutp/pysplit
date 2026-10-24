"""Category listing and default seeding."""

from __future__ import annotations

from sqlmodel import Session, select

from app.core.categories import DEFAULT_CATEGORIES
from app.models.category import Category
from app.schemas.categories import CategoryList, CategoryRead


def ensure_default_categories(session: Session) -> int:
    """Insert any missing default category rows.

    The reference seeds only when the table is empty; the migration plan is
    stricter ("seed the 44 defaults if missing"), so a partially populated table
    is repaired while existing custom rows and names are preserved.
    """
    existing_ids = {
        int(category_id)
        for category_id in session.exec(select(Category.id)).all()
        if category_id is not None
    }
    added = 0
    for category_id, grouping, name in DEFAULT_CATEGORIES:
        if category_id in existing_ids:
            continue
        session.add(Category(id=category_id, grouping=grouping, name=name))
        added += 1
    if added:
        session.commit()
    return added


def list_categories(
    session: Session,
    *,
    limit: int = 200,
    offset: int = 0,
) -> CategoryList:
    ensure_default_categories(session)
    rows = session.exec(
        select(Category).order_by(Category.id.asc()).offset(offset).limit(limit)
    ).all()
    total = len(session.exec(select(Category.id)).all())
    return CategoryList(
        items=[
            CategoryRead(id=int(category.id or 0), grouping=category.grouping, name=category.name)
            for category in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
