"""Blob storage interface.

The application stores uploads through this small interface so local disk and
S3-compatible object storage are interchangeable. Keys are always
server-generated and validated against path traversal.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath


class StorageError(Exception):
    """A blob could not be stored or read."""


def validate_key(key: str) -> PurePosixPath:
    relative = PurePosixPath(key)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise StorageError("invalid storage key")
    return relative


class BlobStorage:
    """Common storage protocol."""

    def save(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        raise NotImplementedError

    def read(self, key: str) -> bytes:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def public_url(self, key: str) -> str | None:
        """Return a publicly readable URL, or ``None`` when the app proxies it."""
        return None


class LocalBlobStorage(BlobStorage):
    """Store blobs under a fixed root using server-generated keys."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        relative = validate_key(key)
        return self.root.joinpath(*relative.parts)

    def save(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_bytes(data)
            temporary.replace(path)
        except OSError as exc:  # pragma: no cover - filesystem failure
            raise StorageError("could not store blob") from exc
        return key

    def read(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return path.read_bytes()
        except OSError as exc:
            raise StorageError("blob not found") from exc

    def delete(self, key: str) -> None:
        path = self._path(key)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover - filesystem failure
            raise StorageError("could not delete blob") from exc

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()
