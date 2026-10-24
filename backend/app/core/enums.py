"""Shared enumerations.

These mirror the reference ``src/lib/enums.ts`` values exactly. They are strings
so they can be stored in SQLite without a separate lookup table.
"""

from __future__ import annotations

from enum import StrEnum


class UserTier(StrEnum):
    """Account tiers. Order is from least to most privileged."""

    SYNC_USERS = "sync_users"
    GROUP_CREATORS = "group_creators"
    ADMIN = "admin"


USER_TIERS: tuple[UserTier, ...] = (
    UserTier.SYNC_USERS,
    UserTier.GROUP_CREATORS,
    UserTier.ADMIN,
)


def normalize_user_tier(value: str | None) -> UserTier:
    """Return a known tier, falling back to ``sync_users``.

    The reference database is the source of truth for tiers, but an unknown
    value must never grant elevated access.
    """
    try:
        return UserTier(value)
    except (TypeError, ValueError):
        return UserTier.SYNC_USERS


def can_create_groups(tier: str | UserTier | None) -> bool:
    """Return whether a tier may create groups (reference matrix)."""
    return normalize_user_tier(str(tier) if tier is not None else None) in {
        UserTier.GROUP_CREATORS,
        UserTier.ADMIN,
    }
