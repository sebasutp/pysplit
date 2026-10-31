#!/usr/bin/env python3
"""Create a consistent SQLite + uploads backup.

Usage:
    python scripts/backup.py --database /data/pysplit.db \
        --uploads /data/uploads --output /backups

The database copy uses the SQLite online backup API, so it is safe while the
application is running and includes uncheckpointed WAL content. Uploads are
archived separately. Every artifact is checksummed in ``manifest.json``; restore
validates those checksums before touching live data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def _iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(path: Path, root: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _table_counts(database: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])
    return counts


def backup_database(source: Path, target: Path) -> None:
    """Copy a live SQLite database with the backup API."""
    target.parent.mkdir(parents=True, exist_ok=True)
    source_uri = f"file:{source}?mode=ro"
    with (
        sqlite3.connect(source_uri, uri=True) as source_connection,
        sqlite3.connect(target) as destination,
    ):
        source_connection.backup(destination)
        destination.execute("PRAGMA journal_mode=DELETE")
        destination.execute("PRAGMA optimize")


def backup_uploads(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz") as archive:
        archive.add(source, arcname="uploads", recursive=True)


def _safe_label(value: str | None) -> str:
    if not value:
        return ""
    cleaned = "".join(
        character if character.isalnum() or character in "-_." else "-" for character in value
    )
    return cleaned.strip(".-")[:60]


def create_backup(
    *,
    database: Path,
    uploads: Path | None,
    output: Path,
    label: str | None = None,
) -> dict[str, object]:
    database = database.resolve()
    if not database.is_file():
        raise FileNotFoundError(f"database not found: {database}")
    if uploads is not None:
        uploads = uploads.resolve()
        if not uploads.exists():
            raise FileNotFoundError(f"uploads directory not found: {uploads}")

    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"-{_safe_label(label)}" if _safe_label(label) else ""
    backup_dir = output / f"pysplit-backup-{stamp}{suffix}"
    backup_dir.mkdir(parents=False, exist_ok=False)

    manifest: dict[str, object] = {
        "format_version": 1,
        "created_at": _iso_now(),
        "database_source": str(database),
    }
    try:
        target_database = backup_dir / "pysplit.db"
        with tempfile.NamedTemporaryFile(
            dir=backup_dir, prefix=".pysplit-", suffix=".db", delete=False
        ) as temp:
            temp_path = Path(temp.name)
        try:
            backup_database(database, temp_path)
            os.replace(temp_path, target_database)
        finally:
            temp_path.unlink(missing_ok=True)

        manifest["database"] = _artifact(target_database, backup_dir)
        manifest["table_counts"] = _table_counts(target_database)

        if uploads is not None:
            target_uploads = backup_dir / "uploads.tar.gz"
            with tempfile.NamedTemporaryFile(
                dir=backup_dir, prefix=".uploads-", suffix=".tar.gz", delete=False
            ) as temp:
                temp_uploads = Path(temp.name)
            try:
                backup_uploads(uploads, temp_uploads)
                os.replace(temp_uploads, target_uploads)
            finally:
                temp_uploads.unlink(missing_ok=True)
            manifest["uploads"] = _artifact(target_uploads, backup_dir)
            manifest["uploads_source"] = str(uploads)

        manifest_path = backup_dir / "manifest.json"
        with tempfile.NamedTemporaryFile(
            dir=backup_dir, prefix=".manifest-", suffix=".json", mode="w", delete=False
        ) as temp:
            json.dump(manifest, temp, indent=2, sort_keys=True)
            temp.write("\n")
            temp_manifest = Path(temp.name)
        os.replace(temp_manifest, manifest_path)
        manifest["directory"] = str(backup_dir)
        manifest["manifest"] = _artifact(manifest_path, backup_dir)
        return manifest
    except Exception:
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--uploads", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--label", help="optional label added to the directory name")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = create_backup(
            database=args.database,
            uploads=args.uploads,
            output=args.output,
            label=args.label,
        )
    except (OSError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        print(f"Backup written to {manifest['directory']}")
        print(f"  database: {manifest['database']['sha256']}")
        if "uploads" in manifest:
            print(f"  uploads:  {manifest['uploads']['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
