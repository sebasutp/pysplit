"""Small validation helpers shared by schemas and services."""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlsplit

# Deliberately pragmatic: the reference accepts any string that looks like an
# email address (zod's ``.email()``); OAuth is the only way to obtain one.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    return value.strip().lower()


def is_valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(value.strip()))


def safe_return_to(
    value: str | None,
    *,
    default: str = "/groups",
    allowed_origins: Iterable[str] = (),
) -> str:
    """Return a safe, origin-relative path to redirect to after login.

    Relative paths are accepted as-is. Absolute URLs are accepted only when
    their origin is in ``allowed_origins`` (normally the configured frontend
    origin), and are reduced to their path, query and fragment. External URLs,
    protocol-relative URLs, backslash tricks and control characters are
    rejected so OAuth callbacks cannot be used as an open redirect.
    """
    if not value:
        return default
    candidate = value.strip()
    if any(character in candidate for character in ("\n", "\r", "\t", "\\")):
        return default

    parsed = urlsplit(candidate)
    if candidate.startswith("/") and not candidate.startswith("//"):
        if parsed.scheme or parsed.netloc:
            return default
        return candidate or default

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return default
    origin = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
    if origin not in {item.lower() for item in allowed_origins}:
        return default
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    if parsed.fragment:
        path = f"{path}#{parsed.fragment}"
    return path
