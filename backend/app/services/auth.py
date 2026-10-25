"""Account, session and OAuth business logic.

Routers own cookies and redirects; this module owns database state. Tier is
always read from the database, never trusted from the access token.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, update
from sqlmodel import Session, select

from app.core.config import Settings
from app.core.enums import UserTier, normalize_user_tier
from app.core.ids import new_id
from app.core.oauth import OAuthProfile
from app.core.security import (
    create_access_token,
    generate_csrf_token,
    generate_refresh_token,
    hash_refresh_token,
)
from app.core.validation import normalize_email
from app.models.account import Account
from app.models.base import utc_now
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import UserRead
from app.services.errors import (
    ForbiddenError,
    InvalidRefreshTokenError,
    RefreshTokenReuseError,
)


def user_to_read(user: User) -> UserRead:
    """Serialise a user with the tier normalised to a known value."""
    return UserRead(
        id=user.id,
        name=user.name,
        email=user.email,
        image=user.image,
        tier=normalize_user_tier(user.tier),
    )


@dataclass(frozen=True)
class IssuedSession:
    access_token: str
    refresh_token: str
    csrf_token: str
    expires_in: int
    user: User


def find_user_by_id(session: Session, user_id: str) -> User | None:
    user = session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        return None
    return user


def find_user_by_email(session: Session, email: str) -> User | None:
    """Find a user by case-insensitive email (legacy rows may be mixed case)."""
    if not email:
        return None
    normalized = email.strip().lower()
    statement = select(User).where(func.lower(User.email) == normalized)
    return session.exec(statement).first()


def _new_refresh_record(
    user: User,
    *,
    settings: Settings,
    user_agent: str | None,
    now: datetime,
) -> tuple[str, RefreshToken]:
    raw_token = generate_refresh_token()
    record = RefreshToken(
        id=new_id("rt"),
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        created_at=now,
        user_agent=(user_agent or "")[:500] or None,
    )
    return raw_token, record


def issue_session(
    session: Session,
    user: User,
    *,
    settings: Settings,
    user_agent: str | None = None,
    now: datetime | None = None,
) -> IssuedSession:
    """Create an access token plus a fresh refresh-token family."""
    moment = now or utc_now()
    raw_refresh, record = _new_refresh_record(
        user,
        settings=settings,
        user_agent=user_agent,
        now=moment,
    )
    session.add(record)
    session.commit()

    return IssuedSession(
        access_token=create_access_token(
            user.id,
            secret=settings.jwt_secret,
            ttl_seconds=settings.access_token_ttl_seconds,
            now=moment,
        ),
        refresh_token=raw_refresh,
        csrf_token=generate_csrf_token(),
        expires_in=settings.access_token_ttl_seconds,
        user=user,
    )


def refresh_token_user_id(session: Session, raw_token: str) -> str | None:
    """Return the owning user for rate-limit keying, without rotating."""
    if not raw_token:
        return None
    statement = select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
    record = session.exec(statement).first()
    return record.user_id if record else None


def _revoke_family(session: Session, token: RefreshToken, now: datetime) -> None:
    """Revoke a token and every token descended from it via rotation."""
    seen: set[str] = set()
    current: RefreshToken | None = token
    while current is not None and current.id not in seen:
        seen.add(current.id)
        if current.revoked_at is None:
            current.revoked_at = now
            session.add(current)
        current = (
            session.get(RefreshToken, current.replaced_by_id) if current.replaced_by_id else None
        )


def rotate_refresh_token(
    session: Session,
    raw_token: str,
    *,
    settings: Settings,
    user_agent: str | None = None,
    now: datetime | None = None,
) -> IssuedSession:
    """Rotate a refresh token, detecting reuse of an already-rotated token."""
    moment = now or utc_now()
    if not raw_token:
        raise InvalidRefreshTokenError("missing refresh token")

    statement = select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
    token = session.exec(statement).first()
    if token is None:
        raise InvalidRefreshTokenError("unknown refresh token")

    if token.revoked_at is not None:
        _revoke_family(session, token, moment)
        session.commit()
        if token.replaced_by_id:
            raise RefreshTokenReuseError("refresh token reuse detected")
        raise InvalidRefreshTokenError("refresh token revoked")

    if token.expires_at <= moment:
        token.revoked_at = moment
        session.add(token)
        session.commit()
        raise InvalidRefreshTokenError("refresh token expired")

    user = find_user_by_id(session, token.user_id)
    if user is None:
        token.revoked_at = moment
        session.add(token)
        session.commit()
        raise InvalidRefreshTokenError("refresh token owner missing")

    raw_refresh, replacement = _new_refresh_record(
        user,
        settings=settings,
        user_agent=user_agent,
        now=moment,
    )
    # Conditional update makes concurrent rotations of the same token safe:
    # exactly one request can claim the row.
    result = session.execute(
        update(RefreshToken)
        .where(RefreshToken.id == token.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=moment, replaced_by_id=replacement.id)
    )
    if result.rowcount != 1:
        session.rollback()
        current = session.get(RefreshToken, token.id)
        if current is not None:
            _revoke_family(session, current, moment)
            session.commit()
        raise RefreshTokenReuseError("refresh token already rotated")

    session.add(replacement)
    session.commit()

    return IssuedSession(
        access_token=create_access_token(
            user.id,
            secret=settings.jwt_secret,
            ttl_seconds=settings.access_token_ttl_seconds,
            now=moment,
        ),
        refresh_token=raw_refresh,
        csrf_token=generate_csrf_token(),
        expires_in=settings.access_token_ttl_seconds,
        user=user,
    )


def revoke_refresh_family(
    session: Session,
    raw_token: str,
    *,
    now: datetime | None = None,
) -> None:
    """Revoke the presented token and every descendant produced by rotation.

    Logout must invalidate descendants too: otherwise the newest rotated token
    in the family stays usable after the user signs out. Tokens belonging to
    other families (including other users) are left untouched.
    """
    if not raw_token:
        return
    statement = select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
    token = session.exec(statement).first()
    if token is None:
        return
    _revoke_family(session, token, now or utc_now())
    session.commit()


def upsert_oauth_user(session: Session, profile: OAuthProfile) -> User:
    """Resolve an OAuth profile to a user, linking by account or email."""
    account_statement = select(Account).where(
        Account.provider == profile.provider,
        Account.provider_account_id == profile.provider_account_id,
    )
    account = session.exec(account_statement).first()
    if account is not None:
        user = session.get(User, account.user_id)
        if user is not None:
            changed = False
            if profile.name and profile.name != user.name:
                user.name = profile.name
                changed = True
            if profile.image and profile.image != user.image:
                user.image = profile.image
                changed = True
            if changed:
                user.updated_at = utc_now()
                user.version += 1
                session.add(user)
                session.commit()
            return user

    email = normalize_email(profile.email) if profile.email else None
    if email and profile.email_verified is not True:
        # An unverified address proves nothing about ownership. Refuse both
        # account linking and auto-provisioning so a provider cannot be used to
        # take over an existing account.
        raise ForbiddenError("OAuth provider email is not verified.")

    existing_user = find_user_by_email(session, email) if email else None

    if existing_user is not None:
        user = existing_user
        session.add(
            Account(
                id=new_id("acc"),
                user_id=user.id,
                type="oauth",
                provider=profile.provider,
                provider_account_id=profile.provider_account_id,
            )
        )
        changed = False
        if profile.name and profile.name != user.name:
            user.name = profile.name
            changed = True
        if profile.image and profile.image != user.image:
            user.image = profile.image
            changed = True
        if changed:
            user.updated_at = utc_now()
            user.version += 1
            session.add(user)
        session.commit()
        session.refresh(user)
        return user

    user = User(
        id=new_id("usr"),
        name=profile.name,
        email=email,
        image=profile.image,
        tier=UserTier.SYNC_USERS.value,
    )
    session.add(user)
    session.flush()
    session.add(
        Account(
            id=new_id("acc"),
            user_id=user.id,
            type="oauth",
            provider=profile.provider,
            provider_account_id=profile.provider_account_id,
        )
    )
    session.commit()
    session.refresh(user)
    return user


def mock_login(
    session: Session,
    *,
    email: str | None,
    name: str | None,
    tier: UserTier | None,
) -> User:
    """Development-only passwordless login used by Playwright helpers."""
    address = normalize_email(email) if email else f"test-{uuid4().hex}@example.com"
    user = find_user_by_email(session, address)
    if user is None:
        user = User(
            id=new_id("usr"),
            email=address,
            name=name or "Test User",
            tier=(tier or UserTier.SYNC_USERS).value,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user

    if tier is not None and normalize_user_tier(user.tier) != tier:
        user.tier = tier.value
        user.updated_at = utc_now()
        user.version += 1
        session.add(user)
        session.commit()
        session.refresh(user)
    return user
