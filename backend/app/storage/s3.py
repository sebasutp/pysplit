"""S3-compatible object storage.

Implements the small :class:`~app.storage.base.BlobStorage` interface against
any S3-compatible endpoint (AWS S3, Cloudflare R2, MinIO, ...). Only the three
operations the application needs are supported: PUT, GET/HEAD and DELETE.

Signing is AWS Signature Version 4 with path-style addressing. The project
already depends on ``httpx`` and the standard library, so no vendor SDK is
required; tests inject an ``httpx.MockTransport``.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

import httpx

from app.storage.base import BlobStorage, StorageError, validate_key

_ALGORITHM = "AWS4-HMAC-SHA256"
_SERVICE = "s3"
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_UNRESERVED = "-_.~"


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, date: str, region: str) -> bytes:
    date_key = _hmac(f"AWS4{secret}".encode(), date)
    region_key = _hmac(date_key, region)
    service_key = _hmac(region_key, _SERVICE)
    return _hmac(service_key, "aws4_request")


class S3BlobStorage(BlobStorage):
    """Store blobs in an S3-compatible bucket using path-style URLs."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
        endpoint: str | None = None,
        public_url: str | None = None,
        http_client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.bucket = bucket
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key
        self.endpoint = (endpoint or f"https://s3.{region}.amazonaws.com").rstrip("/")
        self._public_url = public_url.rstrip("/") if public_url else None
        self._owns_client = http_client is None
        self._client = http_client
        self._timeout = timeout

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> S3BlobStorage:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _object_url(self, key: str) -> str:
        validated = validate_key(key)
        encoded = "/".join(quote(part, safe=_UNRESERVED) for part in validated.parts)
        return f"{self.endpoint}/{quote(self.bucket, safe=_UNRESERVED)}/{encoded}"

    def _signed_headers(
        self,
        method: str,
        key: str,
        *,
        payload_hash: str,
        now: datetime,
    ) -> dict[str, str]:
        url = urlsplit(self._object_url(key))
        host = url.netloc
        canonical_uri = url.path or "/"
        amz_date = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        date = amz_date[:8]
        canonical_headers = (
            f"host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
        )
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        canonical_request = (
            f"{method}\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
        )
        scope = f"{date}/{self.region}/{_SERVICE}/aws4_request"
        string_to_sign = (
            f"{_ALGORITHM}\n{amz_date}\n{scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )
        signature = hmac.new(
            _signing_key(self.secret_key, date, self.region),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
            "authorization": (
                f"{_ALGORITHM} Credential={self.access_key}/{scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
        }

    def _request(
        self,
        method: str,
        key: str,
        *,
        data: bytes | None = None,
        content_type: str | None = None,
    ) -> httpx.Response:
        payload_hash = (
            hashlib.sha256(data or b"").hexdigest() if data is not None else _EMPTY_SHA256
        )
        now = datetime.now(UTC)
        headers = self._signed_headers(method, key, payload_hash=payload_hash, now=now)
        if content_type:
            headers["content-type"] = content_type
        try:
            return self._get_client().request(
                method,
                self._object_url(key),
                headers=headers,
                content=data,
            )
        except httpx.HTTPError as exc:  # pragma: no cover - transport failure
            raise StorageError("could not reach object storage") from exc

    def save(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        response = self._request("PUT", key, data=data, content_type=content_type)
        if response.status_code >= 400:
            raise StorageError("could not store blob")
        return key

    def read(self, key: str) -> bytes:
        response = self._request("GET", key)
        if response.status_code == 404:
            raise StorageError("blob not found")
        if response.status_code >= 400:
            raise StorageError("could not read blob")
        return response.content

    def delete(self, key: str) -> None:
        response = self._request("DELETE", key)
        if response.status_code >= 400 and response.status_code != 404:
            raise StorageError("could not delete blob")

    def exists(self, key: str) -> bool:
        response = self._request("HEAD", key)
        if response.status_code == 404:
            return False
        if response.status_code >= 400:
            raise StorageError("could not check blob")
        return True

    def public_url(self, key: str) -> str | None:
        if not self._public_url:
            return None
        validate_key(key)
        return f"{self._public_url}/{key}"
