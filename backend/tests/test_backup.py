"""Stage 12: online SQLite backup and verified restore."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.backup import create_backup, sha256_file
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
