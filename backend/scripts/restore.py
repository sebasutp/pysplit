#!/usr/bin/env python3
"""Restore a backup produced by ``scripts/backup.py``.

Usage:
    python scripts/restore.py --backup /backups/pysplit-backup-... \
        --database /data/pysplit.db --uploads /data/uploads
    python scripts/restore.py --backup ... --database ... --dry-run

Checksums are verified before any live file is replaced. Stop the API first:
SQLite restore is atomic at the file level, but the running process must not
keep the old database open. Existing targets are renamed to a timestamped
``.pre-restore-*`` sibling rather than deleted, so an operator can undo a
restore.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def _fail(message: str) -> None:
    raise ValueError(message)


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(backup_dir: Path) -> dict:
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.is_file():
        _fail(f"manifest not found: {manifest_path}")
    with manifest_path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("format_version") != 1:
        _fail("unsupported backup format_version")
    return manifest


def _verify_artifact(backup_dir: Path, artifact: dict, name: str) -> Path:
    relative = artifact.get("path")
    if not isinstance(relative, str) or not relative:
        _fail(f"{name} artifact has no path")
    path = (backup_dir / relative).resolve()
    if backup_dir.resolve() not in path.parents and path != backup_dir.resolve():
        _fail(f"{name} artifact escapes the backup directory")
    if not path.is_file():
        _fail(f"{name} artifact is missing: {path}")
    expected = artifact.get("sha256")
    if not isinstance(expected, str) or sha256_file(path) != expected:
        _fail(f"{name} checksum does not match the manifest")
    expected_bytes = artifact.get("bytes")
    if isinstance(expected_bytes, int) and path.stat().st_size != expected_bytes:
        _fail(f"{name} size does not match the manifest")
    return path


def _safe_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    for member in members:
        name = member.name.replace("\\", "/")
        parts = [part for part in name.split("/") if part not in {"", "."}]
        if name.startswith("/") or ".." in parts or not parts or parts[0] != "uploads":
            _fail(f"unsafe archive member: {member.name}")
        if not (member.isfile() or member.isdir()):
            _fail(f"unsupported archive member type: {member.name}")
    return members


def _replace_preserving_existing(path: Path, replacement: Path) -> Path | None:
    """Move ``path`` aside, then install ``replacement`` at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    retired: Path | None = None
    if path.exists():
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        retired = path.with_name(f"{path.name}.pre-restore-{stamp}")
        os.replace(path, retired)
    os.replace(replacement, path)
    return retired


def restore_backup(
    *,
    backup_dir: Path,
    database: Path,
    uploads: Path | None,
    dry_run: bool = False,
) -> dict[str, object]:
    backup_dir = backup_dir.resolve()
    manifest = load_manifest(backup_dir)
    database_artifact = manifest.get("database")
    if not isinstance(database_artifact, dict):
        _fail("manifest has no database artifact")
    source_database = _verify_artifact(backup_dir, database_artifact, "database")

    source_uploads: Path | None = None
    uploads_artifact = manifest.get("uploads")
    if uploads is not None:
        if not isinstance(uploads_artifact, dict):
            _fail("backup does not contain uploads")
        source_uploads = _verify_artifact(backup_dir, uploads_artifact, "uploads")
    elif isinstance(uploads_artifact, dict):
        # The caller did not ask for uploads; leave the live directory alone.
        source_uploads = None

    result: dict[str, object] = {
        "backup": str(backup_dir),
        "created_at": manifest.get("created_at"),
        "database": str(database.resolve()),
        "uploads": str(uploads.resolve()) if uploads and source_uploads else None,
        "dry_run": dry_run,
        "restored_database": False,
        "restored_uploads": False,
    }
    if dry_run:
        result["ok"] = True
        return result

    database = database.resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".restore-", dir=database.parent))
    try:
        staged_database = staging_root / "pysplit.db"
        shutil.copy2(source_database, staged_database)

        staged_uploads: Path | None = None
        if uploads is not None and source_uploads is not None:
            extract_root = staging_root / "uploads-extract"
            extract_root.mkdir()
            with tarfile.open(source_uploads, "r:gz") as archive:
                _safe_members(archive)
                archive.extractall(extract_root, filter="data")
            staged_uploads = extract_root / "uploads"
            if not staged_uploads.is_dir():
                _fail("uploads archive does not contain an uploads directory")

        retired_uploads: Path | None = None
        if uploads is not None and staged_uploads is not None:
            retired_uploads = _replace_preserving_existing(uploads.resolve(), staged_uploads)
            result["retired_uploads"] = str(retired_uploads) if retired_uploads else None
            result["restored_uploads"] = True

        retired_database = _replace_preserving_existing(database, staged_database)
        result["retired_database"] = str(retired_database) if retired_database else None
        result["restored_database"] = True
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)

    result["ok"] = True
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--uploads", type=Path)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the backup and checksums without replacing live files",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = restore_backup(
            backup_dir=args.backup,
            database=args.database,
            uploads=args.uploads,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError, tarfile.TarError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        if result["dry_run"]:
            print("Backup verified (dry run).")
        else:
            print(f"Restored database to {result['database']}")
            if result["restored_uploads"]:
                print(f"Restored uploads to {result['uploads']}")
            if result.get("retired_database"):
                print(f"Previous database kept at {result['retired_database']}")
            if result.get("retired_uploads"):
                print(f"Previous uploads kept at {result['retired_uploads']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
