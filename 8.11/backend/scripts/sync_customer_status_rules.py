"""Backfill every health table from the three current public rule tables."""

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.catalog import HEALTH_RULE_GROUPS
from app.database import close_pool, connection, open_pool
from app.repositories import SettingsRepository


def main() -> None:
    open_pool()
    try:
        for group_key in HEALTH_RULE_GROUPS:
            with connection() as conn:
                repository = SettingsRepository(conn)
                rules = repository.health_rules(group_key)
                result = repository.update_health_rules(group_key, rules, force_sync=True)
                conn.commit()
                print(f"{group_key}: {result['updated_health_rows']}", flush=True)
    finally:
        close_pool()


if __name__ == "__main__":
    main()
