"""Token primitives for the access/refresh session model.

The access token is a compact HS256 JWT held only in SPA memory. The refresh
token is an opaque 256-bit random value; only its SHA-256 hash is stored. No
third-party JWT or crypto library is needed for these primitives.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

JWT_ALGORITHM = "HS256"
JWT_TYPE = "JWT"


class TokenError(ValueError):
    """Raised when a token cannot be decoded or verified."""


@dataclass(frozen=True)
class AccessTokenClaims:
    """Verified claims from an access token."""

    subject: str
    issued_at: int
    expires_at: int
    token_id: str


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (binascii.Error, ValueError) as exc:
        raise TokenError("invalid base64url") from exc


def _now_epoch(now: datetime | None) -> int:
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return int(moment.timestamp())


def _sign(data: str, secret: str) -> str:
    signature = hmac.new(secret.encode("utf-8"), data.encode("ascii"), hashlib.sha256).digest()
    return _base64url_encode(signature)


def create_access_token(
    subject: str,
    *,
    secret: str,
    ttl_seconds: int,
    now: datetime | None = None,
) -> str:
    """Create a signed HS256 access token for ``subject``."""
    if not subject:
        raise ValueError("subject is required")
    issued_at = _now_epoch(now)
    header = {"alg": JWT_ALGORITHM, "typ": JWT_TYPE}
    payload = {
        "sub": subject,
        "iat": issued_at,
        "exp": issued_at + int(ttl_seconds),
        "jti": secrets.token_urlsafe(16),
    }
    encoded_header = _base64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    encoded_payload = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}"
    return f"{signing_input}.{_sign(signing_input, secret)}"


def verify_access_token(
    token: str,
    *,
    secret: str,
    now: datetime | None = None,
) -> AccessTokenClaims:
    """Verify signature, shape and expiry.

    Raises :class:`TokenError` for anything invalid. Callers that want an
    optional user should catch this exception and treat it as anonymous.
    """
    if not token or token.count(".") != 2:
        raise TokenError("malformed token")

    encoded_header, encoded_payload, signature = token.split(".")
    signing_input = f"{encoded_header}.{encoded_payload}"
    expected_signature = _sign(signing_input, secret)
    if not hmac.compare_digest(signature, expected_signature):
        raise TokenError("bad signature")

    try:
        header = json.loads(_base64url_decode(encoded_header))
        payload = json.loads(_base64url_decode(encoded_payload))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TokenError("invalid token payload") from exc

    if not isinstance(header, dict) or header.get("alg") != JWT_ALGORITHM:
        raise TokenError("unsupported algorithm")
    if header.get("typ") not in (None, JWT_TYPE):
        raise TokenError("unsupported token type")
    if not isinstance(payload, dict):
        raise TokenError("invalid claims")

    subject = payload.get("sub")
    expires_at = payload.get("exp")
    if not isinstance(subject, str) or not subject:
        raise TokenError("missing subject")
    if not isinstance(expires_at, int):
        raise TokenError("missing expiry")
    if _now_epoch(now) >= expires_at:
        raise TokenError("token expired")

    issued_at = payload.get("iat")
    token_id = payload.get("jti")
    return AccessTokenClaims(
        subject=subject,
        issued_at=issued_at if isinstance(issued_at, int) else 0,
        expires_at=expires_at,
        token_id=token_id if isinstance(token_id, str) else "",
    )


def generate_refresh_token() -> str:
    """Return a 256-bit opaque refresh token."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage (never store the raw value)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_compare(left: str | None, right: str | None) -> bool:
    """Compare two secrets without leaking their contents through timing."""
    if left is None or right is None:
        return False
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def generate_csrf_token() -> str:
    """Return a random double-submit CSRF token."""
    return secrets.token_urlsafe(32)


def generate_oauth_state() -> str:
    """Return a random OAuth state value."""
    return secrets.token_urlsafe(32)
