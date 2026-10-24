"""Shared Pydantic helpers and list envelopes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, PlainSerializer


def iso_z(value: datetime) -> str:
    """Serialise a datetime as ISO-8601 UTC with a ``Z`` suffix."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


UTCDateTime = Annotated[
    datetime,
    PlainSerializer(iso_z, return_type=str, when_used="json"),
]


class ListEnvelope(BaseModel):
    total: int
    limit: int
    offset: int
