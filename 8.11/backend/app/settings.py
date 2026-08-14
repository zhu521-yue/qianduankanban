from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = "postgresql://postgres:postgres@127.0.0.1:5432/ai_customer_dashboard"
    frontend_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    session_cookie_name: str = "ai_dashboard_session"
    session_ttl_hours: int = 8
    accounts_file: str = "config/accounts.json"
    max_upload_bytes: int = 300 * 1024 * 1024
    app_encryption_key: str = ""
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model_name: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [value.strip() for value in self.frontend_origins.split(",") if value.strip()]

    @property
    def secure_cookie(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
