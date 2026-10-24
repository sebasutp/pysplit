"""Service-layer errors translated to HTTP status codes by routers."""

from __future__ import annotations


class ServiceError(Exception):
    """Base class for expected business errors."""


class NotFoundError(ServiceError):
    """A requested entity does not exist."""


class ConflictError(ServiceError):
    """The request conflicts with current state (HTTP 409)."""


class InvalidInputError(ServiceError):
    """A business-rule validation error (HTTP 422)."""

    def __init__(self, detail: str, *, field: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.field = field


class PayloadTooLargeError(ServiceError):
    """An upload exceeds the configured limit (HTTP 413)."""


class InvalidRefreshTokenError(ServiceError):
    """The presented refresh token is unknown, expired or revoked."""


class RefreshTokenReuseError(InvalidRefreshTokenError):
    """A rotated refresh token was presented again; the family is revoked."""
