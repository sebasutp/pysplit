"""Storage backends and the runtime factory."""

from __future__ import annotations

import httpx

from app.storage.base import BlobStorage, LocalBlobStorage, StorageError
from app.storage.s3 import S3BlobStorage

__all__ = [
    "BlobStorage",
    "LocalBlobStorage",
    "S3BlobStorage",
    "StorageError",
    "build_storage",
]


def build_storage(settings, *, http_client: httpx.Client | None = None) -> BlobStorage:
    """Return the configured blob backend.

    S3-compatible storage is used when the credential/bucket/region quartet is
    present; otherwise uploads stay on local disk. Tests can pass an
    ``httpx.Client`` backed by ``MockTransport`` for the S3 adapter.
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
