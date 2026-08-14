import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import InvalidToken

from app.responses import ApiError
from app.schemas import UserContext
from app.security import _fernet, verify_password
from app.settings import get_settings


def load_accounts() -> dict[str, dict[str, str | None]]:
    path = Path(get_settings().accounts_file)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiError(503, "ACCOUNTS_UNAVAILABLE", "账号配置文件无法读取，请检查后端 config/accounts.json。") from exc
    accounts = payload.get("accounts") if isinstance(payload, dict) else None
    if not isinstance(accounts, dict):
        raise ApiError(503, "ACCOUNTS_INVALID", "账号配置文件格式不正确。")
    return accounts


def authenticate(username: str, password: str) -> UserContext:
    accounts = load_accounts()
    account = accounts.get(username.strip())
    if not account or not verify_password(password, account["password_hash"]):
        raise ApiError(401, "CREDENTIALS_INVALID", "账号或密码不正确。")
    return UserContext(
        id=account["id"],
        username=username.strip(),
        display_name=account["display_name"],
        role=account["role"],
        group_key=account["group_key"],
    )


def issue_session(user: UserContext, ttl_hours: int) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    payload = {**user.__dict__, "expires_at": expires_at.isoformat()}
    token = _fernet().encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    return token, expires_at


def read_session(token: str) -> UserContext:
    try:
        payload = json.loads(_fernet().decrypt(token.encode("ascii")).decode("utf-8"))
        expires_at = datetime.fromisoformat(payload.pop("expires_at"))
        if expires_at <= datetime.now(timezone.utc):
            raise ApiError(401, "SESSION_EXPIRED", "登录状态已过期，请重新登录。")
        return UserContext(**payload)
    except ApiError:
        raise
    except (InvalidToken, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ApiError(401, "SESSION_INVALID", "登录状态已失效，请重新登录。") from exc
