"""Stage 12: online SQLite backup and verified restore."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.backup import create_backup, sha256_file
from scripts.backup_loop import main as backup_loop_main
from scripts.backup_loop import prune_backups, sqlite_path
from scripts.restore import restore_backup


def _make_database(path: Path, value: str = "before") -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO notes (value) VALUES (?)", (value,))


def _read_value(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT value FROM notes").fetchone()[0]


def test_backup_and_restore_round_trip(tmp_path: Path) -> None:
    database = tmp_path / "live" / "pysplit.db"
    database.parent.mkdir()
    _make_database(database)
    uploads = tmp_path / "live" / "uploads"
    (uploads / "receipts" / "grp_1").mkdir(parents=True)
    (uploads / "receipts" / "grp_1" / "image.jpg").write_bytes(b"image-bytes")

    manifest = create_backup(
        database=database,
        uploads=uploads,
        output=tmp_path / "backups",
        label="test",
    )
    backup_dir = Path(manifest["directory"])
    assert (backup_dir / "manifest.json").is_file()
    assert manifest["database"]["sha256"] == sha256_file(backup_dir / "pysplit.db")
    stored = json.loads((backup_dir / "manifest.json").read_text())
    assert stored["database"]["sha256"] == manifest["database"]["sha256"]
    assert stored["table_counts"]["notes"] == 1

    # Simulate live changes after the backup.
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE notes SET value = 'after'")
    (uploads / "receipts" / "grp_1" / "image.jpg").write_bytes(b"changed")
    (uploads / "extra.txt").write_text("extra")

    dry_run = restore_backup(
        backup_dir=backup_dir,
        database=database,
        uploads=uploads,
        dry_run=True,
    )
    assert dry_run["ok"] is True
    assert _read_value(database) == "after"

    result = restore_backup(backup_dir=backup_dir, database=database, uploads=uploads)

    assert result["restored_database"] is True
    assert result["restored_uploads"] is True
    assert _read_value(database) == "before"
    assert (uploads / "receipts" / "grp_1" / "image.jpg").read_bytes() == b"image-bytes"
    assert not (uploads / "extra.txt").exists()

    retired_database = Path(str(result["retired_database"]))
    retired_uploads = Path(str(result["retired_uploads"]))
    assert retired_database.is_file()
    assert _read_value(retired_database) == "after"
    assert (retired_uploads / "extra.txt").is_file()


def _leave_stale_wal(path: Path, value: str = "after") -> None:
    """Insert a row and exit without a clean SQLite checkpoint.

    This is the crash shape that leaves a ``-wal`` file beside the live
    database. The subprocess uses ``os._exit`` so SQLite cannot checkpoint and
    remove the WAL during interpreter shutdown.
    """
    code = """
import os
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
connection.execute("PRAGMA journal_mode=WAL")
connection.execute("PRAGMA wal_autocheckpoint=0")
connection.execute("INSERT INTO notes (value) VALUES (?)", (sys.argv[2],))
connection.commit()
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", code, str(path), value], check=True)
    assert Path(f"{path}-wal").exists()


def test_restore_retires_stale_wal_and_shm_sidecars(tmp_path: Path) -> None:
    database = tmp_path / "pysplit.db"
    _make_database(database)
    manifest = create_backup(database=database, uploads=None, output=tmp_path / "backups")

    _leave_stale_wal(database)
    assert Path(f"{database}-shm").exists()

    result = restore_backup(
        backup_dir=Path(manifest["directory"]),
        database=database,
        uploads=None,
    )

    with sqlite3.connect(database) as connection:
        rows = [row[0] for row in connection.execute("SELECT value FROM notes ORDER BY id")]
    assert rows == ["before"]
    assert result["integrity_check"] == "ok"
    assert len(result["retired_database_sidecars"]) == 2

    retired_wal = Path(str(result["retired_database_sidecars"][0]))
    retired_shm = Path(str(result["retired_database_sidecars"][1]))
    assert retired_wal.name.startswith("pysplit.db-wal.pre-restore-")
    assert retired_shm.name.startswith("pysplit.db-shm.pre-restore-")


def test_restore_rejects_a_tampered_database(tmp_path: Path) -> None:
    database = tmp_path / "pysplit.db"
    _make_database(database)
    manifest = create_backup(database=database, uploads=None, output=tmp_path / "backups")
    backup_dir = Path(manifest["directory"])
    with (backup_dir / "pysplit.db").open("ab") as handle:
        handle.write(b"tampered")

    with pytest.raises(ValueError, match="checksum"):
        restore_backup(backup_dir=backup_dir, database=database, uploads=None)


def test_restore_requires_uploads_requested_by_the_operator(tmp_path: Path) -> None:
    database = tmp_path / "pysplit.db"
    _make_database(database)
    manifest = create_backup(database=database, uploads=None, output=tmp_path / "backups")

    with pytest.raises(ValueError, match="does not contain uploads"):
        restore_backup(
            backup_dir=Path(manifest["directory"]),
            database=database,
            uploads=tmp_path / "uploads",
        )


def test_backup_refuses_a_missing_database(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        create_backup(
            database=tmp_path / "missing.db",
            uploads=None,
            output=tmp_path / "backups",
        )


def test_restore_rejects_an_archive_path_traversal(tmp_path: Path) -> None:
    import io
    import tarfile

    database = tmp_path / "pysplit.db"
    _make_database(database)
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    manifest = create_backup(
        database=database,
        uploads=uploads,
        output=tmp_path / "backups",
    )
    backup_dir = Path(manifest["directory"])
    archive_path = backup_dir / "uploads.tar.gz"

    with tarfile.open(archive_path, "w:gz") as archive:
        info = tarfile.TarInfo("../escape.txt")
        payload = b"escape"
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    stored = json.loads((backup_dir / "manifest.json").read_text())
    stored["uploads"]["sha256"] = sha256_file(archive_path)
    stored["uploads"]["bytes"] = archive_path.stat().st_size
    (backup_dir / "manifest.json").write_text(json.dumps(stored))

    with pytest.raises(ValueError, match="unsafe archive member"):
        restore_backup(backup_dir=backup_dir, database=database, uploads=uploads)


def test_backup_loop_parses_sqlite_urls(tmp_path: Path) -> None:
    assert sqlite_path("sqlite:////data/pysplit.db") == Path("/data/pysplit.db")
    assert sqlite_path("sqlite:///./relative.db") == Path.cwd() / "./relative.db"
    with pytest.raises(ValueError, match="file-backed"):
        sqlite_path("sqlite://")
    with pytest.raises(ValueError, match="file-backed"):
        sqlite_path("postgresql://example/db")


def test_backup_loop_runs_once_and_tolerates_missing_uploads(tmp_path: Path) -> None:
    database = tmp_path / "pysplit.db"
    _make_database(database)
    output = tmp_path / "backups"

    status = backup_loop_main(
        [
            "--once",
            "--database",
            str(database),
            "--uploads",
            str(tmp_path / "missing-uploads"),
            "--output",
            str(output),
            "--retention-days",
            "14",
        ]
    )

    assert status == 0
    manifests = list(output.glob("pysplit-backup-*/manifest.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text())
    assert manifest["table_counts"]["notes"] == 1
    assert "uploads" not in manifest


def test_backup_loop_prunes_only_expired_backups(tmp_path: Path) -> None:
    import os
    from datetime import UTC, datetime, timedelta

    output = tmp_path / "backups"
    old = output / "pysplit-backup-old"
    recent = output / "pysplit-backup-recent"
    old.mkdir(parents=True)
    recent.mkdir()
    now = datetime(2026, 10, 31, tzinfo=UTC)
    old_time = (now - timedelta(days=20)).timestamp()
    os.utime(old, (old_time, old_time))

    removed = prune_backups(output, retention_days=14, now=now)

    assert removed == [old]
    assert not old.exists()
    assert recent.exists()


def test_backup_loop_entrypoint_runs_without_pythonpath() -> None:
    import subprocess
    import sys

    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/backup_loop.py", "--help"],
        cwd=backend,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
