"""A small in-process rate limiter shared by authentication endpoints.

The API runs as a single Uvicorn worker against SQLite (plan §12), so an
in-memory sliding window is sufficient and avoids another dependency. If the
deployment grows past one process this must move to a shared store.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.core.config import Settings


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window limiter keyed by caller-supplied strings."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> RateLimitResult:
        if limit <= 0:
            return RateLimitResult(allowed=True, remaining=0, retry_after=0)

        moment = time.monotonic() if now is None else now
        cutoff = moment - window_seconds
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= cutoff:
                events.popleft()

            if len(events) >= limit:
                retry_after = max(1, math.ceil(events[0] + window_seconds - moment))
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    retry_after=retry_after,
                )

            events.append(moment)
            return RateLimitResult(
                allowed=True,
                remaining=limit - len(events),
                retry_after=0,
            )

    def reset(self) -> None:
        """Forget every window (used by tests and after configuration reload)."""
        with self._lock:
            self._events.clear()


auth_rate_limiter = SlidingWindowRateLimiter()


def client_key(request: Request) -> str:
    """Return a stable caller identity for rate-limit keys."""
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce_rate_limit(
    request: Request,
    settings: Settings,
    *,
    scope: str,
    account_key: str | None = None,
) -> None:
    """Raise ``429`` when this caller exceeded the auth budget."""
    result = auth_rate_limiter.check(
        f"ip:{client_key(request)}:{scope}",
        limit=settings.auth_rate_limit_per_minute,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Try again later.",
            headers={"Retry-After": str(result.retry_after)},
        )

    if account_key:
        account_result = auth_rate_limiter.check(
            f"account:{account_key}:{scope}",
            limit=settings.auth_account_rate_limit_per_minute,
            window_seconds=settings.auth_rate_limit_window_seconds,
        )
        if not account_result.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts. Try again later.",
                headers={"Retry-After": str(account_result.retry_after)},
            )
