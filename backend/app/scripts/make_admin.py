"""Bootstrap an administrator without touching SQLite by hand.

Usage::

    python -m app.scripts.make_admin --email owner@example.com
    python -m app.scripts.make_admin --email owner@example.com --db /tmp/new.db

If the email already belongs to a user, that user is promoted to ``admin``.
Otherwise a pre-authorized admin account is created so the owner's first OAuth
login links to it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.core.config import get_settings
from app.core.enums import UserTier
from app.schemas.admin import PreAuthorizeResponse
from app.services.admin import preauthorize_user


def database_url(value: str | None) -> str:
    """Accept either a SQLAlchemy URL or a filesystem path."""
    if not value:
        return get_settings().database_url
    if "://" in value:
        return value
    return f"sqlite:///{Path(value).expanduser().resolve()}"


def make_admin(
    *,
    email: str,
    db: str | None = None,
    name: str | None = None,
) -> PreAuthorizeResponse:
    """Promote an existing user or create a pre-authorized admin account."""
    url = database_url(db)
    engine = create_engine(url)
    try:
        with Session(engine) as session:
            return preauthorize_user(
                session,
                email=email,
                tier=UserTier.ADMIN,
                name=name,
            )
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="user email to promote")
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite path or SQLAlchemy URL (defaults to DATABASE_URL)",
    )
    parser.add_argument("--name", default=None, help="display name for new users")
    args = parser.parse_args(argv)

    try:
        result = make_admin(email=args.email, db=args.db, name=args.name)
    except SQLAlchemyError as exc:
        print(f"error: could not update the database: {exc}", file=sys.stderr)
        return 2

    action = "Created pre-authorized admin" if result.is_new else "Promoted user"
    print(f"{action}: {result.user.email} (tier={result.user.tier.value})")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess test
    raise SystemExit(main())
