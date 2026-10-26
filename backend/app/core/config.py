from functools import lru_cache
from pathlib import Path
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import (
    AnyHttpUrl,
    EmailStr,
    Field,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")
    database_url: PostgresDsn = PostgresDsn(
        "postgresql+psycopg://easyearn:easyearn_dev_password@localhost:5432/easyearn"
    )
    allowed_hosts: list[str] = ["localhost", "127.0.0.1"]
    max_request_body_bytes: int = Field(default=20480, ge=1024, le=1048576)
    session_cookie_name: str = Field(
        default="easyearn_session", pattern=r"^[a-zA-Z0-9_-]+$"
    )
    session_ttl_seconds: int = Field(default=604800, ge=300, le=2592000)
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=10, ge=0, le=100)
    email_verification_ttl_seconds: int = Field(default=86400, ge=300, le=604800)
    password_reset_ttl_seconds: int = Field(default=1800, ge=300, le=3600)
    auth_email_cooldown_seconds: int = Field(default=60, ge=1, le=3600)
    smtp_host: str = Field(default="localhost", min_length=1)
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_tls_mode: Literal["none", "starttls", "ssl"] = "none"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_email: EmailStr = "no-reply@example.com"
    smtp_timeout_seconds: int = Field(default=10, ge=1, le=60)
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    redis_timeout_seconds: float = Field(default=0.5, gt=0, le=10)
    redis_max_connections: int = Field(default=20, ge=1, le=1000)
    auth_rate_limit_key_prefix: str = Field(
        default="easyearn:auth-limits", pattern=r"^[A-Za-z0-9:_-]{1,80}$"
    )
    auth_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    auth_rate_limit_signup: int = Field(default=5, ge=1, le=10000)
    auth_rate_limit_login: int = Field(default=10, ge=1, le=10000)
    auth_rate_limit_verification_request: int = Field(default=5, ge=1, le=10000)
    auth_rate_limit_verification_confirm: int = Field(default=20, ge=1, le=10000)
    auth_rate_limit_password_forgot: int = Field(default=5, ge=1, le=10000)
    auth_rate_limit_password_reset: int = Field(default=10, ge=1, le=10000)
    email_outbox_keys: list[SecretStr] = []
    email_worker_poll_seconds: float = Field(default=1, ge=0.05, le=60)
    email_worker_lease_seconds: int = Field(default=120, ge=30, le=3600)
    email_worker_max_attempts: int = Field(default=5, ge=1, le=20)
    email_retry_base_seconds: int = Field(default=30, ge=1, le=3600)
    email_retry_max_seconds: int = Field(default=3600, ge=1, le=86400)
    email_cleanup_interval_seconds: int = Field(default=300, ge=1, le=86400)
    email_cleanup_batch_size: int = Field(default=500, ge=1, le=10000)
    email_outbox_retention_seconds: int = Field(default=604800, ge=3600, le=2592000)

    @field_validator("email_outbox_keys")
    @classmethod
    def validate_outbox_keys(cls, values: list[SecretStr]) -> list[SecretStr]:
        for value in values:
            try:
                Fernet(value.get_secret_value().encode("ascii"))
            except (ValueError, UnicodeError):
                raise ValueError("EMAIL_OUTBOX_KEYS must contain valid Fernet keys.") from None
        if len({value.get_secret_value() for value in values}) != len(values):
            raise ValueError("EMAIL_OUTBOX_KEYS must not contain duplicate keys.")
        return values

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, value: SecretStr) -> SecretStr:
        try:
            url = RedisDsn(value.get_secret_value())
        except ValidationError:
            raise ValueError("REDIS_URL must be a redis:// or rediss:// URL.") from None
        if url.query or url.fragment:
            raise ValueError("REDIS_URL must not contain query parameters or a fragment.")
        if url.path and not url.path.removeprefix("/").isdigit():
            raise ValueError("REDIS_URL must specify a nonnegative database number.")
        return SecretStr(str(url))

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def validate_deployment(self) -> "Settings":
        if self.email_retry_max_seconds < self.email_retry_base_seconds:
            raise ValueError("EMAIL_RETRY_MAX_SECONDS must be at least EMAIL_RETRY_BASE_SECONDS.")
        if self.database_url.scheme != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must use the postgresql+psycopg driver.")
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            raise ValueError("ALLOWED_HOSTS must list explicit hostnames.")
        if (
            self.app_url.path not in (None, "/")
            or self.app_url.query
            or self.app_url.fragment
        ):
            raise ValueError(
                "APP_URL must be an origin without a path, query, or fragment."
            )
        if self.is_production and self.app_url.scheme != "https":
            raise ValueError("APP_URL must use HTTPS in production.")
        has_smtp_password = bool(
            self.smtp_password and self.smtp_password.get_secret_value()
        )
        if bool(self.smtp_username) != has_smtp_password:
            raise ValueError("Set both SMTP_USERNAME and SMTP_PASSWORD, or neither.")
        if self.is_production and self.smtp_tls_mode == "none":
            raise ValueError("SMTP_TLS_MODE must use starttls or ssl in production.")
        if self.is_production and str(self.smtp_from_email).endswith("@example.com"):
            raise ValueError("Set SMTP_FROM_EMAIL to your production sender address.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
