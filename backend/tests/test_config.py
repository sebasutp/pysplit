"""Configuration parsing tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_name == "pysplit"
    assert settings.api_prefix == "/api"
    assert settings.environment == "development"
    assert settings.database_url.startswith("sqlite:///")


def test_api_prefix_is_normalised() -> None:
    assert Settings(api_prefix="/v1/", _env_file=None).api_prefix == "/v1"


def test_api_prefix_requires_leading_slash() -> None:
    with pytest.raises(ValidationError):
        Settings(api_prefix="api", _env_file=None)


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = Settings(cors_origins=" http://a.test , http://b.test ,", _env_file=None)
    assert settings.cors_origins_list == ["http://a.test", "http://b.test"]


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "pysplit-test")
    monkeypatch.setenv("ENVIRONMENT", "test")
    settings = Settings(_env_file=None)
    assert settings.app_name == "pysplit-test"
    assert settings.environment == "test"


def test_sqlite_parent_directory_is_created(tmp_path: Path) -> None:
    database = tmp_path / "nested" / "db.sqlite"
    Settings(database_url=f"sqlite:///{database}", _env_file=None)
    assert database.parent.is_dir()


def test_memory_database_is_left_alone() -> None:
    settings = Settings(database_url="sqlite://", _env_file=None)
    assert settings.database_url == "sqlite://"
