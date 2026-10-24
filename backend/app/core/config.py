"""Application configuration.

Settings are read once per process. Tests construct :class:`Settings`
directly with ``_env_file=None`` so a developer's ``.env`` cannot affect them.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_JWT_SECRET = "development-only-jwt-secret-change-me"


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

    # --- Authentication -------------------------------------------------
    # The development default is deliberately rejected in production.
    jwt_secret: str = DEVELOPMENT_JWT_SECRET
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_days: int = 30
    oauth_state_ttl_seconds: int = 10 * 60
    # None means "secure when running in production or over HTTPS".
    cookie_secure: bool | None = None
    refresh_cookie_name: str = "pysplit_refresh"
    csrf_cookie_name: str = "pysplit_csrf"
    oauth_state_cookie_name: str = "pysplit_oauth_state"
    oauth_return_to_cookie_name: str = "pysplit_oauth_return_to"
    auth_cookie_path: str = "/api/auth"
    # Public origin used for OAuth redirect URIs and CSRF origin checks.
    base_url: str | None = None

    auth_google_id: str | None = None
    auth_google_secret: str | None = None
    auth_github_id: str | None = None
    auth_github_secret: str | None = None

    # Shared limiter for authentication endpoints.
    auth_rate_limit_per_minute: int = 30
    auth_account_rate_limit_per_minute: int = 60
    auth_rate_limit_window_seconds: int = 60

    # --- Uploads and runtime feature flags ------------------------------
    # Local disk is the default blob backend; Stage 7 adds an S3 adapter.
    upload_dir: str = "data/uploads"
    max_upload_bytes: int = 10 * 1024 * 1024
    upload_allowed_types: str = "image/jpeg,image/png,image/webp"
    enable_receipt_extract: bool = False
    enable_receipt_items: bool = False
    enable_category_extract: bool = False
    enable_expense_documents: bool = False

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

    @field_validator("base_url")
    @classmethod
    def _normalise_base_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value.strip().rstrip("/")

    @field_validator("jwt_secret")
    @classmethod
    def _normalise_secret(cls, value: str) -> str:
        # An empty environment value means "use the development default" in
        # development; production validation below still rejects it.
        return value.strip() or DEVELOPMENT_JWT_SECRET

    @field_validator("access_token_ttl_seconds", "oauth_state_ttl_seconds")
    @classmethod
    def _positive_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be positive")
        return value

    @field_validator("refresh_token_ttl_days")
    @classmethod
    def _positive_days(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be positive")
        return value

    @field_validator("max_upload_bytes")
    @classmethod
    def _positive_upload_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be positive")
        return value

    @field_validator("upload_dir")
    @classmethod
    def _normalise_upload_dir(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("upload_dir must not be empty")
        return cleaned

    @model_validator(mode="after")
    def _require_production_secret(self) -> Settings:
        if self.environment.lower() == "production":
            if not self.jwt_secret or self.jwt_secret == DEVELOPMENT_JWT_SECRET:
                raise ValueError("JWT_SECRET must be set to a unique value in production")
            if len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be at least 32 characters")
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def secure_cookies(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        if self.is_production:
            return True
        return bool(self.base_url and self.base_url.startswith("https://"))

    @property
    def enabled_oauth_providers(self) -> list[str]:
        providers: list[str] = []
        if self.auth_google_id and self.auth_google_secret:
            providers.append("google")
        if self.auth_github_id and self.auth_github_secret:
            providers.append("github")
        return providers

    @property
    def upload_allowed_type_list(self) -> list[str]:
        return [
            item.strip().lower() for item in self.upload_allowed_types.split(",") if item.strip()
        ]

    @property
    def receipt_extract_enabled(self) -> bool:
        return self.enable_receipt_extract or self.enable_receipt_items


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
