"""Upload helpers: receipt images, SSRF allowlisting and AI image payloads.

Receipt images can live on S3/R2 public storage or on the API's local disk. The
AI provider must only receive URLs the application itself produced, so the URL
is validated against the configured storage hosts before any model call.
Locally stored images are converted to an inline ``data:`` URL so a provider
that cannot reach the API origin can still read them.
"""

from __future__ import annotations

import base64
import re
from urllib.parse import urlsplit

from sqlmodel import Session

from app.core.config import Settings
from app.core.ids import new_id
from app.services.errors import InvalidInputError, PayloadTooLargeError
from app.storage import BlobStorage, StorageError

CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
EXTENSION_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def receipt_image_key(image_id: str, content_type: str) -> str:
    extension = CONTENT_TYPE_EXTENSIONS.get(content_type.lower())
    if extension is None:
        raise InvalidInputError("unsupported image type", field="file")
    return f"receipts/{image_id}{extension}"


def receipt_image_route(settings: Settings, group_id: str, image_id: str) -> str:
    return f"{settings.api_prefix}/groups/{group_id}/receipts/images/{image_id}"


def save_receipt_image(
    storage: BlobStorage,
    settings: Settings,
    *,
    group_id: str,
    data: bytes,
    content_type: str | None,
    width: int = 1,
    height: int = 1,
) -> dict[str, object]:
    if not data:
        raise InvalidInputError("uploaded file is empty", field="file")
    if len(data) > settings.max_upload_bytes:
        raise PayloadTooLargeError(f"file exceeds the {settings.max_upload_bytes} byte limit")

    normalized_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_type not in {item.lower() for item in settings.upload_allowed_type_list}:
        raise InvalidInputError("unsupported image type", field="file")

    image_id = new_id("img")
    key = receipt_image_key(image_id, normalized_type)
    storage.save(key, data, content_type=normalized_type)
    url = storage.public_url(key) or receipt_image_route(settings, group_id, image_id)
    return {
        "id": image_id,
        "key": key,
        "url": url,
        "width": max(1, int(width)),
        "height": max(1, int(height)),
    }


def find_receipt_image(storage: BlobStorage, image_id: str) -> tuple[bytes, str, str]:
    for extension, media_type in EXTENSION_CONTENT_TYPES.items():
        key = f"receipts/{image_id}{extension}"
        try:
            if storage.exists(key):
                return storage.read(key), media_type, f"{image_id}{extension}"
        except StorageError:
            continue
    raise InvalidInputError("receipt image not found", field="image_id")


def is_allowed_upload_url(settings: Settings, raw_url: str) -> bool:
    """Return whether ``raw_url`` may be sent to the AI provider.

    Relative paths are accepted only for the API's own upload routes; absolute
    URLs must be http(s) and their host must be one of the configured storage
    (or application) hosts. This mirrors the reference allowlist and prevents
    SSRF-via-provider / unbounded spend.
    """
    if not raw_url or not isinstance(raw_url, str):
        return False

    if raw_url.startswith("/"):
        if raw_url.startswith("//"):
            return False
        return _matches_own_upload_route(settings, raw_url) is not None

    try:
        url = urlsplit(raw_url)
    except ValueError:
        return False
    if url.scheme not in {"http", "https"}:
        return False
    if not url.hostname:
        return False
    return url.hostname in settings.allowed_upload_hosts


def _matches_own_upload_route(
    settings: Settings,
    path: str,
) -> tuple[str, str, str] | None:
    prefix = re.escape(settings.api_prefix)
    receipt = re.fullmatch(
        rf"{prefix}/groups/([^/]+)/receipts/images/([^/]+)",
        path,
    )
    if receipt:
        return ("receipt", receipt.group(1), receipt.group(2))
    document = re.fullmatch(
        rf"{prefix}/groups/([^/]+)/expenses/([^/]+)/documents/([^/]+)",
        path,
    )
    if document:
        return ("document", document.group(1), document.group(3))
    return None


def _read_local_upload(
    storage: BlobStorage,
    settings: Settings,
    kind: str,
    group_id: str,
    entity_id: str,
) -> tuple[bytes, str] | None:
    if kind == "receipt":
        try:
            data, media_type, _filename = find_receipt_image(storage, entity_id)
        except InvalidInputError:
            return None
        return data, media_type
    if kind == "document":
        for extension, media_type in EXTENSION_CONTENT_TYPES.items():
            key = f"documents/{entity_id}{extension}"
            try:
                if storage.exists(key):
                    return storage.read(key), media_type
            except StorageError:
                continue
        return None
    return None


def resolve_image_for_ai(
    session: Session,
    storage: BlobStorage,
    settings: Settings,
    *,
    group_id: str,
    image_url: str,
) -> str:
    """Validate an image URL and return the value passed to the model.

    Public storage URLs are passed through. Relative app routes (or absolute
    URLs on the app's own host) are read from blob storage and inlined as a
    ``data:`` URL. Anything else is rejected as an invalid image URL.
    """
    del session  # Reserved for future per-group document authorization.
    if not is_allowed_upload_url(settings, image_url):
        raise InvalidInputError("Invalid image URL.", field="image_url")

    if image_url.startswith("/"):
        path = urlsplit(image_url).path
    else:
        path = urlsplit(image_url).path
        own_host = urlsplit(settings.base_url).hostname if settings.base_url else None
        if urlsplit(image_url).hostname != own_host:
            # An allowlisted public storage URL can be given to the provider.
            return image_url

    match = _matches_own_upload_route(settings, path)
    if match is None:
        raise InvalidInputError("Invalid image URL.", field="image_url")
    kind, route_group_id, entity_id = match
    if route_group_id != group_id:
        raise InvalidInputError("Invalid image URL.", field="image_url")

    found = _read_local_upload(storage, settings, kind, group_id, entity_id)
    if found is None:
        raise InvalidInputError("Invalid image URL.", field="image_url")
    data, media_type = found
    if len(data) > settings.max_upload_bytes:
        raise PayloadTooLargeError("image exceeds the upload size limit")
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{media_type};base64,{encoded}"
