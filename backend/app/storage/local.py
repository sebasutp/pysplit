"""Local-disk blob storage.

The implementation lives in :mod:`app.storage.base` so the S3 adapter can share
the same protocol and key validation. This module remains the import location
used by earlier stages.
"""

from __future__ import annotations

from app.storage.base import LocalBlobStorage, StorageError, validate_key

__all__ = ["LocalBlobStorage", "StorageError", "validate_key"]
