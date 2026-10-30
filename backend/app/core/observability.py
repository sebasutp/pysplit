"""Optional error reporting.

Sentry is deliberately not a required dependency: self-hosted deployments may
not want an external collector, and the application must start without the SDK.
Set ``SENTRY_DSN`` and install ``sentry-sdk`` to enable it.
"""

from __future__ import annotations

import logging

from app.core.config import Settings

logger = logging.getLogger("pysplit.observability")


def init_sentry(settings: Settings) -> bool:
    """Initialise Sentry when configured and available.

    Returns ``True`` when the SDK was initialised. A missing SDK is a warning,
    never a startup failure: the API can still serve requests and write local
    logs.
    """
    if not settings.sentry_dsn:
        return False
    try:
        import sentry_sdk  # type: ignore[import-not-found]
    except ImportError:
        logger.warning(
            "SENTRY_DSN is set but sentry-sdk is not installed; error reporting is disabled"
        )
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=f"{settings.app_name}@{settings.app_version}",
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
    )
    return True
