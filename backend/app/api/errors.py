"""Translate expected service errors into HTTP responses."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.services.errors import (
    ConflictError,
    ForbiddenError,
    InvalidInputError,
    NotFoundError,
    PayloadTooLargeError,
    ServiceError,
)


def service_error(exc: ServiceError) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ForbiddenError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, PayloadTooLargeError):
        return HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc))
    if isinstance(exc, InvalidInputError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.detail)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def raise_service_error(exc: ServiceError) -> None:
    raise service_error(exc) from exc
