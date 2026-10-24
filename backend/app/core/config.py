"""Application configuration.

Settings are read once per process. Tests construct :class:`Settings`
directly with ``_env_file=None`` so a developer's ``.env`` cannot affect them.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    app_name: str = "pysplit"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api"

    # SQLite by default. The dev launcher and Docker override this with an
    # absolute path so no database is written next to the source tree.
    database_url: str = "sqlite:///./data/dev/pysplit.db"

    # Comma-separated list; parsed into a list by `cors_origins_list`.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    request_id_header: str = "X-Request-ID"
    log_level: str = "INFO"

    @field_validator("api_prefix")
    @classmethod
    def _normalise_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("api_prefix must start with '/'")
        return value.rstrip("/") or "/"

    @field_validator("database_url")
    @classmethod
    def _ensure_sqlite_parent(cls, value: str) -> str:
        """Create the parent directory for file-backed SQLite databases."""
        prefix = "sqlite:///"
        if value.startswith(prefix) and ":memory:" not in value:
            path = Path(value[len(prefix) :])
            if path.parent != Path("."):
                path.parent.mkdir(parents=True, exist_ok=True)
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
