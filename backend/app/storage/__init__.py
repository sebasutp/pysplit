"""Storage backends and the runtime factory."""

from __future__ import annotations

import threading
from pathlib import Path

import httpx

from app.storage.base import BlobStorage, LocalBlobStorage, StorageError
from app.storage.s3 import S3BlobStorage

__all__ = [
    "BlobStorage",
    "LocalBlobStorage",
    "S3BlobStorage",
    "StorageError",
    "build_storage",
    "close_storage",
    "get_storage",
    "reset_storage",
]


def build_storage(settings, *, http_client: httpx.Client | None = None) -> BlobStorage:
    """Return the configured blob backend.

    S3-compatible storage is used when the credential/bucket/region quartet is
    present; otherwise uploads stay on local disk. Tests can pass an
    ``httpx.Client`` backed by ``MockTransport`` for the S3 adapter. Production
    code should use :func:`get_storage` so the process keeps one client.
    """
    if settings.s3_configured:
        return S3BlobStorage(
            bucket=settings.s3_upload_bucket,
            region=settings.s3_upload_region,
            access_key=settings.s3_upload_key,
            secret_key=settings.s3_upload_secret,
            endpoint=settings.s3_upload_endpoint,
            public_url=settings.s3_public_url,
            http_client=http_client,
        )
    return LocalBlobStorage(settings.upload_dir)


_lock = threading.Lock()
_cached_storage: BlobStorage | None = None
_cached_key: tuple[object, ...] | None = None


def _storage_key(settings) -> tuple[object, ...]:
    """Identity of the configured backend, used to invalidate the cache.

    A key derived from the configuration (rather than the ``Settings`` object)
    lets tests switch upload directories/S3 endpoints without keeping a stale
    client, while production still reuses a single instance.
    """
    if settings.s3_configured:
        return (
            "s3",
            settings.s3_upload_bucket,
            settings.s3_upload_region,
            settings.s3_upload_key,
            settings.s3_upload_secret,
            settings.s3_upload_endpoint,
            settings.s3_public_url,
        )
    return ("local", str(Path(settings.upload_dir).resolve()))


def _close(storage: BlobStorage) -> None:
    close = getattr(storage, "close", None)
    if callable(close):
        close()


def get_storage(settings) -> BlobStorage:
    """Return the process-wide blob backend for ``settings``.

    The client (and its lazily-created ``httpx.Client``) is reused across
    requests instead of being rebuilt per request. When the configuration
    changes the previous backend is closed before the new one is created.
    """
    global _cached_storage, _cached_key

    key = _storage_key(settings)
    with _lock:
        if _cached_storage is None or _cached_key != key:
            if _cached_storage is not None:
                _close(_cached_storage)
            _cached_storage = build_storage(settings)
            _cached_key = key
        return _cached_storage


def close_storage() -> None:
    """Close and forget the cached backend (registered on app shutdown)."""
    global _cached_storage, _cached_key

    with _lock:
        if _cached_storage is not None:
            _close(_cached_storage)
        _cached_storage = None
        _cached_key = None


def reset_storage() -> None:
    """Test helper: drop the cached backend without keeping any state."""
    close_storage()
