"""Opaque identifier generation.

New identifiers are UUIDv4 with a short type prefix. Legacy Prisma/nanoid IDs
are preserved by the importer; nothing here rewrites them.
"""

from __future__ import annotations

from uuid import uuid4


def new_id(prefix: str) -> str:
    """Return ``<prefix>_<uuid4 hex>``."""
    return f"{prefix}_{uuid4().hex}"
