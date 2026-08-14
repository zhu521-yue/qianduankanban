import json
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path
from threading import Lock

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"
AI_ROLE_ENV_PREFIXES = {
    "manager": "AI_MANAGER",
    "talent": "AI_TALENT",
    "private": "AI_PRIVATE",
    "distribution": "AI_DISTRIBUTION",
}
_ENV_KEY = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
_ENV_WRITE_LOCK = Lock()


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
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model_name: str = ""
    ai_manager_base_url: str = ""
    ai_manager_api_key: str = ""
    ai_manager_model_name: str = ""
    ai_talent_base_url: str = ""
    ai_talent_api_key: str = ""
    ai_talent_model_name: str = ""
    ai_private_base_url: str = ""
    ai_private_api_key: str = ""
    ai_private_model_name: str = ""
    ai_distribution_base_url: str = ""
    ai_distribution_api_key: str = ""
    ai_distribution_model_name: str = ""
    ai_default_model: str
    ai_request_timeout_seconds: float
    ai_temperature: float

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


def ai_settings_for_role(role: str) -> dict[str, str]:
    prefix = AI_ROLE_ENV_PREFIXES.get(role)
    if prefix is None:
        raise ValueError(f"不支持的AI配置角色：{role}")
    field_prefix = prefix.lower()
    settings = get_settings()
    base_url = str(getattr(settings, f"{field_prefix}_base_url")).strip().rstrip("/")
    api_key = str(getattr(settings, f"{field_prefix}_api_key")).strip()
    model_name = str(getattr(settings, f"{field_prefix}_model_name")).strip()
    # 兼容升级前主管账号使用的全局配置；任一角色保存后均只读取自己的隔离配置。
    if role == "manager" and not (base_url or api_key or model_name):
        base_url = settings.ai_base_url.strip().rstrip("/")
        api_key = settings.ai_api_key.strip()
        model_name = settings.ai_model_name.strip()
    return {"base_url": base_url, "api_key": api_key, "model_name": model_name}


def save_ai_settings_for_role(role: str, base_url: str, api_key: str, model_name: str) -> None:
    prefix = AI_ROLE_ENV_PREFIXES.get(role)
    if prefix is None:
        raise ValueError(f"不支持的AI配置角色：{role}")
    _update_env_file(
        {
            f"{prefix}_BASE_URL": base_url.strip().rstrip("/"),
            f"{prefix}_API_KEY": api_key.strip(),
            f"{prefix}_MODEL_NAME": model_name.strip(),
        }
    )


def _update_env_file(updates: dict[str, str]) -> None:
    for key, value in updates.items():
        if "\n" in value or "\r" in value:
            raise ValueError(f"{key}不能包含换行符")
    with _ENV_WRITE_LOCK:
        original = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
        lines = original.splitlines()
        remaining = dict(updates)
        rewritten: list[str] = []
        for line in lines:
            matched = _ENV_KEY.match(line)
            key = matched.group(1) if matched else None
            if key in remaining:
                rewritten.append(f"{key}={json.dumps(remaining.pop(key), ensure_ascii=False)}")
            else:
                rewritten.append(line)
        if remaining and rewritten and rewritten[-1].strip():
            rewritten.append("")
        rewritten.extend(f"{key}={json.dumps(value, ensure_ascii=False)}" for key, value in remaining.items())
        content = "\n".join(rewritten).rstrip("\n") + "\n"
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=ENV_FILE.parent,
                prefix=".env.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, ENV_FILE)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
    get_settings.cache_clear()
