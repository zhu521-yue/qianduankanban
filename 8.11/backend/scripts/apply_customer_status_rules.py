"""Apply and verify customer status rule migrations in the existing weidian database."""

from pathlib import Path
import sys

import psycopg

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import close_pool, connection, open_pool
from app.settings import get_settings


MIGRATIONS = (
    BACKEND_ROOT / "migrations" / "001_customer_status_rules.sql",
    BACKEND_ROOT / "migrations" / "002_platform_health_rule_columns.sql",
)
CONCURRENT_MIGRATIONS = (
    BACKEND_ROOT / "migrations" / "003_distribution_non_loss_status_indexes.concurrent.sql",
)
TABLES = (
    "talent_customer_status_action",
    "private_customer_status_action",
    "distribution_customer_status_action",
)
EXPECTED_COLUMNS = (
    "id",
    "customer_health_status",
    "state_instructions",
    "follow_up_action",
    "created_time",
    "updated_time",
)


def main() -> None:
    open_pool()
    try:
        with connection() as conn:
            for migration in MIGRATIONS:
                conn.execute(migration.read_text(encoding="utf-8"))
                print(f"applied: {migration.name}")
            for table in TABLES:
                columns = conn.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (table,),
                ).fetchall()
                actual_columns = tuple(row["column_name"] for row in columns)
                if actual_columns != EXPECTED_COLUMNS:
                    raise RuntimeError(f"{table} 字段不符合预期：{actual_columns}")
                count = conn.execute(f'SELECT COUNT(*) AS value FROM public."{table}"').fetchone()["value"]
                if count != 7:
                    raise RuntimeError(f"{table} 应有 7 条固定状态，实际为 {count}")
                print(f"{table}: 6 fields, 7 statuses")
            doudian_columns = conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'doudian'
                  AND table_name = 'half_year_customer_health'
                  AND column_name IN ('state_instructions', 'follow_up_action')
                ORDER BY column_name
                """
            ).fetchall()
            if {row["column_name"] for row in doudian_columns} != {"state_instructions", "follow_up_action"}:
                raise RuntimeError("doudian.half_year_customer_health 缺少规则同步字段")
            print("doudian.half_year_customer_health: rule columns ready")
    finally:
        close_pool()
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        for migration in CONCURRENT_MIGRATIONS:
            statements = [statement.strip() for statement in migration.read_text(encoding="utf-8").split(";") if statement.strip()]
            for statement in statements:
                conn.execute(statement)
            print(f"applied concurrently: {migration.name}")


if __name__ == "__main__":
    main()
