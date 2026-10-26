from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import (
    AnyHttpUrl,
    EmailStr,
    Field,
    PostgresDsn,
    SecretStr,
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

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def validate_deployment(self) -> "Settings":
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
