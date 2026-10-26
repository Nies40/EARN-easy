from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, PostgresDsn, model_validator
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
    session_cookie_name: str = Field(default="easyearn_session", pattern=r"^[a-zA-Z0-9_-]+$")
    session_ttl_seconds: int = Field(default=604800, ge=300, le=2592000)
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=10, ge=0, le=100)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def validate_deployment(self) -> "Settings":
        if self.database_url.scheme != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must use the postgresql+psycopg driver.")
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            raise ValueError("ALLOWED_HOSTS must list explicit hostnames.")
        if self.app_url.path not in (None, "/") or self.app_url.query or self.app_url.fragment:
            raise ValueError("APP_URL must be an origin without a path, query, or fragment.")
        if self.is_production and self.app_url.scheme != "https":
            raise ValueError("APP_URL must use HTTPS in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
