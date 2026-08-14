"""Safely replace an existing dashboard account password hash."""

import getpass
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.security import hash_password
from app.settings import get_settings


def account_path() -> Path:
    path = Path(get_settings().accounts_file)
    return path if path.is_absolute() else Path(__file__).resolve().parents[1] / path


def main() -> int:
    if len(sys.argv) != 2:
        print("用法：python scripts/set_account_password.py <账号名>")
        return 2
    username = sys.argv[1].strip()
    path = account_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    accounts = payload.get("accounts", {})
    if username not in accounts:
        print(f"账号不存在：{username}")
        return 1
    first = getpass.getpass("请输入新密码：")
    second = getpass.getpass("请再次输入新密码：")
    if not first or first != second:
        print("两次密码不一致或密码为空，未修改。")
        return 1
    accounts[username]["password_hash"] = hash_password(first)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(f"账号 {username} 的密码哈希已更新。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
