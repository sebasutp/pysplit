"""Small validation helpers shared by schemas and services."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

# Deliberately pragmatic: the reference accepts any string that looks like an
# email address (zod's ``.email()``); OAuth is the only way to obtain one.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    return value.strip().lower()


def is_valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(value.strip()))


def safe_return_to(value: str | None, *, default: str = "/groups") -> str:
    """Return ``value`` only when it is a same-origin relative path.

    Rejects absolute URLs, protocol-relative URLs, backslash tricks and
    control characters so OAuth callbacks cannot be used as an open redirect.
    """
    if not value:
        return default
    candidate = value.strip()
    if any(character in candidate for character in ("\n", "\r", "\t", "\\")):
        return default
    if not candidate.startswith("/") or candidate.startswith("//"):
        return default
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        return default
    return candidate or default
