"""Service-layer errors translated to HTTP status codes by routers."""

from __future__ import annotations


class ServiceError(Exception):
    """Base class for expected business errors."""


class NotFoundError(ServiceError):
    """A requested entity does not exist."""


class InvalidRefreshTokenError(ServiceError):
    """The presented refresh token is unknown, expired or revoked."""


class RefreshTokenReuseError(InvalidRefreshTokenError):
    """A rotated refresh token was presented again; the family is revoked."""
