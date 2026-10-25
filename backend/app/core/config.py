"""Application configuration.

Settings are read once per process. Tests construct :class:`Settings`
directly with ``_env_file=None`` so a developer's ``.env`` cannot affect them.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

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
    # Only trust X-Forwarded-Proto/X-Forwarded-Host when a known reverse proxy
    # sets them. Without this, clients can spoof the origin used for CSRF
    # checks and OAuth redirect URIs.
    trust_forwarded_headers: bool = False
    # Development-only passwordless login. Must be enabled explicitly and is
    # always unavailable in production.
    enable_mock_login: bool = False

    auth_google_id: str | None = None
    auth_google_secret: str | None = None
    auth_github_id: str | None = None
    auth_github_secret: str | None = None

    # Shared limiter for authentication endpoints.
    auth_rate_limit_per_minute: int = 30
    auth_account_rate_limit_per_minute: int = 60
    auth_rate_limit_window_seconds: int = 60

    # --- Synchronization ------------------------------------------------
    # Operations are replayable for seven days. Change-log rows are retained
    # for 30 days; a cursor older than the retained window must bootstrap.
    sync_operation_retention_days: int = 7
    sync_change_retention_days: int = 30
    # Per-caller budget for the synchronization endpoints (single worker).
    sync_rate_limit_per_minute: int = 120

    # --- Uploads and runtime feature flags ------------------------------
    # Local disk is the default blob backend; S3-compatible storage is used
    # when the S3_* variables are configured.
    upload_dir: str = "data/uploads"
    max_upload_bytes: int = 10 * 1024 * 1024
    upload_allowed_types: str = "image/jpeg,image/png,image/webp"
    upload_rate_limit_per_minute: int = 60
    enable_receipt_extract: bool = False
    enable_receipt_items: bool = False
    enable_category_extract: bool = False
    enable_expense_documents: bool = False

    # --- S3-compatible document storage ---------------------------------
    # All optional. When the key/secret/bucket/region quartet is present the
    # storage factory selects the S3 adapter instead of local disk.
    s3_upload_key: str | None = None
    s3_upload_secret: str | None = None
    s3_upload_bucket: str | None = None
    s3_upload_region: str | None = None
    s3_upload_endpoint: str | None = None
    s3_public_url: str | None = None

    # --- AI receipt/category extraction ---------------------------------
    # AI_* variables take precedence over the historical OPENAI_* names, as in
    # the reference application.
    ai_api_key: str | None = None
    openai_api_key: str | None = None
    ai_base_url: str | None = None
    openai_base_url: str | None = None
    ai_model_receipt_extract: str | None = None
    openai_model_receipt_extract: str | None = None
    ai_model_receipt_items_extract: str | None = None
    openai_model_receipt_items_extract: str | None = None
    ai_model_category_extract: str | None = None
    openai_model_category_extract: str | None = None
    ai_timeout_seconds: float = 60.0
    ai_rate_limit_per_minute: int = 20

    # --- Receipt item limits --------------------------------------------
    # Mirror the reference server-side caps. The item amount matches the
    # expense form's 10,000,000.00 ceiling in minor units.
    max_receipt_items: int = 200
    max_receipt_item_name_length: int = 200
    max_receipt_item_amount: int = 10_000_000_00
    max_receipt_item_quantity_milli: int = 1_000_000_000
    max_receipt_item_portions: int = 100
    receipt_extraction_stale_seconds: int = 5 * 60
    # A failed extraction is retryable, but each retry is another paid model
    # call. Once the cap is reached the image must be uploaded again.
    receipt_max_attempts: int = 3

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

    @field_validator("sync_operation_retention_days", "sync_change_retention_days")
    @classmethod
    def _positive_retention(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("retention must be positive")
        return value

    @field_validator("max_upload_bytes")
    @classmethod
    def _positive_upload_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be positive")
        return value

    @field_validator(
        "upload_rate_limit_per_minute",
        "ai_rate_limit_per_minute",
        "max_receipt_items",
        "max_receipt_item_name_length",
        "max_receipt_item_amount",
        "max_receipt_item_quantity_milli",
        "max_receipt_item_portions",
        "receipt_extraction_stale_seconds",
        "receipt_max_attempts",
        "sync_rate_limit_per_minute",
    )
    @classmethod
    def _positive_receipt_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be positive")
        return value

    @field_validator("ai_timeout_seconds")
    @classmethod
    def _positive_ai_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("must be positive")
        return value

    @field_validator(
        "s3_upload_key",
        "s3_upload_secret",
        "s3_upload_bucket",
        "s3_upload_region",
        "s3_upload_endpoint",
        "s3_public_url",
        "ai_api_key",
        "openai_api_key",
        "ai_base_url",
        "openai_base_url",
        "ai_model_receipt_extract",
        "openai_model_receipt_extract",
        "ai_model_receipt_items_extract",
        "openai_model_receipt_items_extract",
        "ai_model_category_extract",
        "openai_model_category_extract",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("s3_public_url")
    @classmethod
    def _normalise_public_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().rstrip("/") or None

    @field_validator("ai_base_url", "openai_base_url", "s3_upload_endpoint")
    @classmethod
    def _normalise_optional_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().rstrip("/") or None

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
            if not self.base_url:
                raise ValueError("BASE_URL must be set in production")
            parsed = urlsplit(self.base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("BASE_URL must be an http(s) URL in production")
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

    @property
    def ai_api_key_resolved(self) -> str | None:
        """Provider-neutral ``AI_API_KEY`` wins over ``OPENAI_API_KEY``."""
        return self.ai_api_key or self.openai_api_key

    @property
    def ai_base_url_resolved(self) -> str | None:
        """Provider-neutral ``AI_BASE_URL`` wins over ``OPENAI_BASE_URL``."""
        return self.ai_base_url or self.openai_base_url

    @property
    def ai_provider(self) -> str:
        return self.ai_base_url_resolved or "openai"

    @property
    def ai_provider_label(self) -> str:
        """Stable public label for the configured AI provider.

        ``ai_provider`` contains the internal base URL and must never be
        exposed to clients. This collapses the configuration into a small,
        non-sensitive enum used in receipt read models.
        """
        if not self.ai_api_key_resolved and not self.ai_base_url_resolved:
            return "disabled"
        base = (self.ai_base_url_resolved or "").lower()
        if "google" in base or "generativelanguage" in base:
            return "google"
        return "openai-compatible"

    @property
    def receipt_extract_model(self) -> str:
        return self.ai_model_receipt_extract or self.openai_model_receipt_extract or "gpt-5-nano"

    @property
    def receipt_items_model(self) -> str:
        return (
            self.ai_model_receipt_items_extract
            or self.openai_model_receipt_items_extract
            or self.receipt_extract_model
        )

    @property
    def category_extract_model(self) -> str:
        return self.ai_model_category_extract or self.openai_model_category_extract or "gpt-5-nano"

    @property
    def s3_configured(self) -> bool:
        return bool(
            self.s3_upload_key
            and self.s3_upload_secret
            and self.s3_upload_bucket
            and self.s3_upload_region
        )

    @property
    def allowed_upload_hosts(self) -> list[str]:
        """Hosts the AI may receive image URLs for (SSRF allowlist).

        Mirrors the reference precedence: a dedicated public base URL wins
        over the S3 API endpoint, which wins over the AWS bucket/region
        fallback. The application's own ``BASE_URL`` host is also trusted so
        locally stored receipt images can be resolved safely.
        """
        from urllib.parse import urlsplit

        hosts: list[str] = []
        if self.s3_public_url:
            host = urlsplit(self.s3_public_url).hostname
            if host:
                hosts.append(host)
        elif self.s3_upload_endpoint:
            host = urlsplit(self.s3_upload_endpoint).hostname
            if host:
                hosts.append(host)
        elif self.s3_upload_bucket and self.s3_upload_region:
            hosts.append(f"{self.s3_upload_bucket}.s3.{self.s3_upload_region}.amazonaws.com")

        if self.base_url:
            host = urlsplit(self.base_url).hostname
            if host and host not in hosts:
                hosts.append(host)

        return hosts


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
