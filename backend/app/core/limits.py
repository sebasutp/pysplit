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

    # Sweep stale keys periodically so a long-running process does not retain
    # one deque for every IP/account that ever made a request.
    _prune_every = 256

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._checks_since_prune = 0

    def _prune(self, cutoff: float) -> None:
        """Drop empty windows. Caller must hold the lock."""
        for key in list(self._events):
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if not events:
                del self._events[key]

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
            self._checks_since_prune += 1
            if self._checks_since_prune >= self._prune_every:
                self._prune(cutoff)
                self._checks_since_prune = 0

            events = self._events.get(key)
            if events is None:
                events = deque()
                self._events[key] = events
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
            self._checks_since_prune = 0


auth_rate_limiter = SlidingWindowRateLimiter()
ai_rate_limiter = SlidingWindowRateLimiter()
upload_rate_limiter = SlidingWindowRateLimiter()
sync_rate_limiter = SlidingWindowRateLimiter()


def client_key(request: Request, settings: Settings) -> str:
    """Return a stable caller identity for rate-limit keys.

    ``X-Forwarded-For`` is client-controlled unless a known reverse proxy
    overwrites it, so it is only honoured when ``trust_forwarded_headers`` is
    enabled. The left-most entry is the original client.
    """
    if settings.trust_forwarded_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",", 1)[0].strip()
            if first:
                return first
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
        f"ip:{client_key(request, settings)}:{scope}",
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


def _enforce_shared_limit(
    limiter: SlidingWindowRateLimiter,
    request: Request,
    settings: Settings,
    *,
    scope: str,
    limit: int,
    window_seconds: int,
    detail: str,
) -> None:
    result = limiter.check(
        f"ip:{client_key(request, settings)}:{scope}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(result.retry_after)},
        )


def enforce_ai_rate_limit(request: Request, settings: Settings) -> None:
    """Throttle paid AI calls per caller."""
    _enforce_shared_limit(
        ai_rate_limiter,
        request,
        settings,
        scope="ai",
        limit=settings.ai_rate_limit_per_minute,
        window_seconds=settings.auth_rate_limit_window_seconds,
        detail="Too many AI requests. Try again later.",
    )


def enforce_upload_rate_limit(request: Request, settings: Settings) -> None:
    """Throttle uploads per caller."""
    _enforce_shared_limit(
        upload_rate_limiter,
        request,
        settings,
        scope="upload",
        limit=settings.upload_rate_limit_per_minute,
        window_seconds=settings.auth_rate_limit_window_seconds,
        detail="Too many uploads. Try again later.",
    )


def enforce_sync_rate_limit(request: Request, settings: Settings) -> None:
    """Throttle synchronization traffic per caller."""
    _enforce_shared_limit(
        sync_rate_limiter,
        request,
        settings,
        scope="sync",
        limit=settings.sync_rate_limit_per_minute,
        window_seconds=settings.auth_rate_limit_window_seconds,
        detail="Too many sync requests. Try again later.",
    )
