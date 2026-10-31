#!/usr/bin/env python3
"""Scheduled backup loop for the Compose ``backup`` sidecar.

The service shares the API's ``DATABASE_URL`` and ``UPLOAD_DIR`` so a custom
deployment cannot silently back up the wrong paths. A failed attempt is logged
and retried after the interval instead of terminating the container (which
would become a restart loop). Old backup directories are pruned by age.

Usage:
    python scripts/backup_loop.py --once
    python scripts/backup_loop.py --interval 86400 --retention-days 14
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.backup import create_backup

logger = logging.getLogger("pysplit.backup")


def sqlite_path(database_url: str) -> Path:
    """Return the file path from a file-backed SQLite URL.

    Accepts the SQLAlchemy forms used by the application: ``sqlite:///rel.db``
    (relative), ``sqlite:////abs.db`` (absolute), and rejects in-memory or
    non-SQLite URLs because there is nothing durable to archive.
    """
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError(f"backup requires a file-backed sqlite:/// URL, got {database_url!r}")
    raw = database_url[len(prefix) :]
    if not raw or raw == ":memory:":
        raise ValueError("backup requires a file-backed SQLite database")
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        raise ValueError(f"unsupported SQLite URL: {database_url!r}")
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def prune_backups(output: Path, retention_days: int, *, now: datetime | None = None) -> list[Path]:
    """Delete ``pysplit-backup-*`` directories older than the retention window."""
    if retention_days <= 0:
        return []
    moment = now or datetime.now(UTC)
    cutoff = (moment - timedelta(days=retention_days)).timestamp()
    removed: list[Path] = []
    if not output.is_dir():
        return removed
    for path in sorted(output.glob("pysplit-backup-*")):
        if path.is_dir() and path.stat().st_mtime < cutoff:
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path)
    return removed


def _logger(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )


def run_once(
    *,
    database: Path,
    uploads: Path | None,
    output: Path,
    retention_days: int,
) -> Path:
    """Create one backup and prune old ones. Returns the new backup directory."""
    if uploads is not None and not uploads.is_dir():
        logger.warning("uploads directory %s is missing; backing up the database only", uploads)
        uploads = None
    manifest = create_backup(
        database=database,
        uploads=uploads,
        output=output,
        label="scheduled",
    )
    backup_dir = Path(str(manifest["directory"]))
    removed = prune_backups(output, retention_days)
    logger.info("backup complete: %s", backup_dir)
    if removed:
        logger.info("pruned %d old backup(s)", len(removed))
    return backup_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--uploads", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--interval", type=int)
    parser.add_argument("--retention-days", type=int)
    parser.add_argument("--once", action="store_true", help="run one backup and exit")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _logger(args.verbose)

    try:
        database_url = os.environ.get("DATABASE_URL", "sqlite:////data/pysplit.db")
        database = args.database or sqlite_path(database_url)
        uploads = args.uploads or Path(os.environ.get("UPLOAD_DIR", "/data/uploads"))
        output = args.output or Path(os.environ.get("BACKUP_OUTPUT", "/backups"))
        interval = args.interval or int(os.environ.get("BACKUP_INTERVAL_SECONDS", "86400"))
        retention = (
            args.retention_days
            if args.retention_days is not None
            else int(os.environ.get("BACKUP_RETENTION_DAYS", "14"))
        )
        if interval <= 0:
            raise ValueError("backup interval must be positive")
    except (ValueError, OSError) as exc:
        logger.error("%s", exc)
        return 2

    while True:
        try:
            run_once(
                database=database,
                uploads=uploads,
                output=output,
                retention_days=retention,
            )
        except Exception:
            logger.exception("backup failed; retrying after %s seconds", interval)
            if args.once:
                return 1
        if args.once:
            return 0
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("backup loop interrupted")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
