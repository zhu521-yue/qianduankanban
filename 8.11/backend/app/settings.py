import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    app_env: str
    app_host: str
    app_port: int
    database_url: str
    database_connect_timeout: int
    database_pool_min_size: int
    database_pool_max_size: int
    frontend_origins: str
    session_cookie_name: str
    session_ttl_hours: int
    accounts_file: str
    max_upload_bytes: int
    app_encryption_key: str

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [value.strip() for value in self.frontend_origins.split(",") if value.strip()]

    @property
    def secure_cookie(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()