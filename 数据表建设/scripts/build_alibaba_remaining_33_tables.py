from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "8.11" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.settings import get_settings  # noqa: E402


DATABASE = "weidian"
SCHEMA = "alibaba"
EXPECTED_RAW_ROWS = 978_128
EXPECTED_SHIPPED_ROWS = 977_649
EXPECTED_CUSTOMERS = 128_678


@dataclass(frozen=True)
class TableDefinition:
    name: str
    columns: str
    unique_columns: tuple[str, ...]


COMMON_TIMESTAMPS = """
    created_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai'),
    updated_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')
"""


TABLES = [
    TableDefinition("daily_sales", """
        id BIGSERIAL PRIMARY KEY,
        transaction_date DATE NOT NULL,
        transaction_amount NUMERIC(18,2) NOT NULL,
        {timestamps}
    """, ("transaction_date",)),
    TableDefinition("daily_product_sales", """
        id BIGSERIAL PRIMARY KEY,
        transaction_date DATE NOT NULL,
        product_code VARCHAR(255) NOT NULL,
        transaction_amount NUMERIC(18,2) NOT NULL,
        product_quantity NUMERIC(18,4) NOT NULL,
        {timestamps}
    """, ("transaction_date", "product_code")),
    TableDefinition("daily_customer_sales", """
        id BIGSERIAL PRIMARY KEY,
        transaction_date DATE NOT NULL,
        customer_id VARCHAR(255) NOT NULL,
        transaction_amount NUMERIC(18,2) NOT NULL,
        {timestamps}
    """, ("transaction_date", "customer_id")),
    TableDefinition("weekly_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        weekly_transaction_amount NUMERIC(18,2) NOT NULL,
        {timestamps},
        CHECK (period_end = period_start + 6)
    """, ("period_start", "period_end")),
    TableDefinition("weekly_refunds", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        weekly_refund_amount NUMERIC(18,2) NOT NULL,
        {timestamps},
        CHECK (period_end = period_start + 6)
    """, ("period_start", "period_end")),
    TableDefinition("weekly_product_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        product_code VARCHAR(255) NOT NULL,
        weekly_transaction_amount NUMERIC(18,2) NOT NULL,
        weekly_product_quantity NUMERIC(18,4) NOT NULL,
        {timestamps},
        CHECK (period_end = period_start + 6)
    """, ("period_start", "period_end", "product_code")),
    TableDefinition("weekly_customer_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        customer_id VARCHAR(255) NOT NULL,
        weekly_transaction_amount NUMERIC(18,2) NOT NULL,
        {timestamps},
        CHECK (period_end = period_start + 6)
    """, ("period_start", "period_end", "customer_id")),
    TableDefinition("monthly_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        monthly_transaction_amount NUMERIC(18,2) NOT NULL,
        {timestamps},
        CHECK (period_start = date_trunc('month', period_start)::date),
        CHECK (period_end = (period_start + INTERVAL '1 month - 1 day')::date)
    """, ("period_start", "period_end")),
    TableDefinition("monthly_refunds", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        monthly_refund_amount NUMERIC(18,2) NOT NULL,
        {timestamps},
        CHECK (period_start = date_trunc('month', period_start)::date),
        CHECK (period_end = (period_start + INTERVAL '1 month - 1 day')::date)
    """, ("period_start", "period_end")),
    TableDefinition("monthly_product_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        product_code VARCHAR(255) NOT NULL,
        monthly_transaction_amount NUMERIC(18,2) NOT NULL,
        monthly_product_quantity NUMERIC(18,4) NOT NULL,
        {timestamps}
    """, ("period_start", "period_end", "product_code")),
    TableDefinition("monthly_customer_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        customer_id VARCHAR(255) NOT NULL,
        monthly_transaction_amount NUMERIC(18,2) NOT NULL,
        {timestamps}
    """, ("period_start", "period_end", "customer_id")),
    TableDefinition("quarterly_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        quarterly_transaction_amount NUMERIC(18,2) NOT NULL,
        {timestamps},
        CHECK (period_end = (period_start + INTERVAL '3 months - 1 day')::date)
    """, ("period_start", "period_end")),
    TableDefinition("quarterly_refunds", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        quarterly_refund_amount NUMERIC(18,2) NOT NULL,
        {timestamps},
        CHECK (period_end = (period_start + INTERVAL '3 months - 1 day')::date)
    """, ("period_start", "period_end")),
    TableDefinition("quarterly_product_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        product_code VARCHAR(255) NOT NULL,
        quarterly_transaction_amount NUMERIC(18,2) NOT NULL,
        quarterly_product_quantity NUMERIC(18,4) NOT NULL,
        {timestamps}
    """, ("period_start", "period_end", "product_code")),
    TableDefinition("quarterly_customer_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        customer_id VARCHAR(255) NOT NULL,
        quarterly_transaction_amount NUMERIC(18,2) NOT NULL,
        {timestamps}
    """, ("period_start", "period_end", "customer_id")),
    TableDefinition("half_year_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        half_year_transaction_amount NUMERIC(18,2) NOT NULL,
        {timestamps},
        CHECK (period_end = (period_start + INTERVAL '6 months - 1 day')::date)
    """, ("period_start", "period_end")),
    TableDefinition("half_year_refunds", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        half_year_refund_amount NUMERIC(18,2) NOT NULL,
        {timestamps},
        CHECK (period_end = (period_start + INTERVAL '6 months - 1 day')::date)
    """, ("period_start", "period_end")),
    TableDefinition("half_year_product_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        product_code VARCHAR(255) NOT NULL,
        half_year_transaction_amount NUMERIC(18,2) NOT NULL,
        half_year_product_quantity NUMERIC(18,4) NOT NULL,
        {timestamps}
    """, ("period_start", "period_end", "product_code")),
    TableDefinition("half_year_customer_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        customer_id VARCHAR(255) NOT NULL,
        half_year_transaction_amount NUMERIC(18,2) NOT NULL,
        {timestamps}
    """, ("period_start", "period_end", "customer_id")),
    TableDefinition("daily_sales_metrics", """
        id BIGSERIAL PRIMARY KEY,
        transaction_date DATE NOT NULL,
        transaction_amount NUMERIC(18,2) NOT NULL,
        year_over_year_rate NUMERIC(10,2) NOT NULL,
        rolling_7_day_transaction_amount NUMERIC(18,2) NOT NULL,
        rolling_30_day_transaction_amount NUMERIC(18,2) NOT NULL,
        {timestamps}
    """, ("transaction_date",)),
    TableDefinition("weekly_sales_metrics", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        weekly_transaction_amount NUMERIC(18,2) NOT NULL,
        week_over_week_rate NUMERIC(10,2) NOT NULL,
        {timestamps}
    """, ("period_start", "period_end")),
    TableDefinition("monthly_sales_metrics", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        monthly_transaction_amount NUMERIC(18,2) NOT NULL,
        month_over_month_rate NUMERIC(10,2) NOT NULL,
        {timestamps}
    """, ("period_start", "period_end")),
    TableDefinition("customer_daily_sales", """
        id BIGSERIAL PRIMARY KEY,
        transaction_date DATE NOT NULL,
        customer_id VARCHAR(255) NOT NULL,
        transaction_amount NUMERIC(18,2) NOT NULL,
        {timestamps}
    """, ("customer_id", "transaction_date")),
    TableDefinition("customer_daily_sales_metrics", """
        id BIGSERIAL PRIMARY KEY,
        transaction_date DATE NOT NULL,
        customer_id VARCHAR(255) NOT NULL,
        transaction_amount NUMERIC(18,2) NOT NULL,
        rolling_7_day_transaction_amount NUMERIC(18,2) NOT NULL,
        rolling_30_day_transaction_amount NUMERIC(18,2) NOT NULL,
        {timestamps}
    """, ("customer_id", "transaction_date")),
    TableDefinition("customer_weekly_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        customer_id VARCHAR(255) NOT NULL,
        weekly_transaction_amount NUMERIC(18,2) NOT NULL,
        weekly_purchase_count INTEGER NOT NULL CHECK (weekly_purchase_count BETWEEN 1 AND 7),
        {timestamps},
        CHECK (period_end = period_start + 6)
    """, ("customer_id", "period_start", "period_end")),
    TableDefinition("customer_monthly_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        customer_id VARCHAR(255) NOT NULL,
        monthly_transaction_amount NUMERIC(18,2) NOT NULL,
        monthly_purchase_count INTEGER NOT NULL CHECK (monthly_purchase_count BETWEEN 1 AND 31),
        {timestamps}
    """, ("customer_id", "period_start", "period_end")),
    TableDefinition("customer_quarterly_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        customer_id VARCHAR(255) NOT NULL,
        quarterly_transaction_amount NUMERIC(18,2) NOT NULL,
        quarterly_purchase_count INTEGER NOT NULL,
        {timestamps},
        CHECK (quarterly_purchase_count BETWEEN 1 AND (period_end - period_start + 1))
    """, ("customer_id", "period_start", "period_end")),
    TableDefinition("customer_half_year_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        customer_id VARCHAR(255) NOT NULL,
        half_year_transaction_amount NUMERIC(18,2) NOT NULL,
        half_year_purchase_count INTEGER NOT NULL,
        {timestamps},
        CHECK (half_year_purchase_count BETWEEN 1 AND (period_end - period_start + 1))
    """, ("customer_id", "period_start", "period_end")),
    TableDefinition("customer_daily_product_sales", """
        id BIGSERIAL PRIMARY KEY,
        transaction_date DATE NOT NULL,
        customer_id VARCHAR(255) NOT NULL,
        product_code VARCHAR(255) NOT NULL,
        transaction_amount NUMERIC(18,2) NOT NULL,
        product_quantity NUMERIC(18,4) NOT NULL,
        {timestamps}
    """, ("customer_id", "transaction_date", "product_code")),
    TableDefinition("customer_monthly_product_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        customer_id VARCHAR(255) NOT NULL,
        product_code VARCHAR(255) NOT NULL,
        monthly_transaction_amount NUMERIC(18,2) NOT NULL,
        monthly_product_quantity NUMERIC(18,4) NOT NULL,
        {timestamps}
    """, ("customer_id", "period_start", "period_end", "product_code")),
    TableDefinition("customer_quarterly_product_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        customer_id VARCHAR(255) NOT NULL,
        product_code VARCHAR(255) NOT NULL,
        quarterly_transaction_amount NUMERIC(18,2) NOT NULL,
        quarterly_product_quantity NUMERIC(18,4) NOT NULL,
        {timestamps}
    """, ("customer_id", "period_start", "period_end", "product_code")),
    TableDefinition("customer_half_year_product_sales", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        customer_id VARCHAR(255) NOT NULL,
        product_code VARCHAR(255) NOT NULL,
        half_year_transaction_amount NUMERIC(18,2) NOT NULL,
        half_year_product_quantity NUMERIC(18,4) NOT NULL,
        {timestamps}
    """, ("customer_id", "period_start", "period_end", "product_code")),
    TableDefinition("customer_health_detail", """
        id BIGSERIAL PRIMARY KEY,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        customer_id VARCHAR(255) NOT NULL,
        week_period_start DATE NOT NULL,
        week_period_end DATE NOT NULL,
        month_period_start DATE NOT NULL,
        month_period_end DATE NOT NULL,
        week_purchase_count INTEGER NOT NULL CHECK (week_purchase_count BETWEEN 0 AND 7),
        week_score NUMERIC(5,2) NOT NULL CHECK (week_score BETWEEN 0 AND 100),
        month_purchase_count NUMERIC(10,2) NOT NULL CHECK (month_purchase_count >= 0),
        month_score NUMERIC(5,2) NOT NULL CHECK (month_score BETWEEN 0 AND 100),
        customer_score NUMERIC(5,2) NOT NULL CHECK (customer_score BETWEEN 0 AND 100),
        customer_health_status VARCHAR(50) NOT NULL,
        state_instructions TEXT NULL,
        follow_up_action TEXT NULL,
        {timestamps},
        CHECK (period_start = week_period_start),
        CHECK (period_end = week_period_end),
        CHECK (period_end = period_start + 6)
    """, ("customer_id", "period_start", "period_end")),
]


QUARTER_START_FROM_DATE = """
CASE
    WHEN EXTRACT(MONTH FROM {date_col}) = 1
        THEN make_date(EXTRACT(YEAR FROM {date_col})::int - 1, 11, 1)
    WHEN EXTRACT(MONTH FROM {date_col}) BETWEEN 2 AND 4
        THEN make_date(EXTRACT(YEAR FROM {date_col})::int, 2, 1)
    WHEN EXTRACT(MONTH FROM {date_col}) BETWEEN 5 AND 7
        THEN make_date(EXTRACT(YEAR FROM {date_col})::int, 5, 1)
    WHEN EXTRACT(MONTH FROM {date_col}) BETWEEN 8 AND 10
        THEN make_date(EXTRACT(YEAR FROM {date_col})::int, 8, 1)
    ELSE make_date(EXTRACT(YEAR FROM {date_col})::int, 11, 1)
END
"""


HALF_START_FROM_DATE = """
CASE
    WHEN EXTRACT(MONTH FROM {date_col}) = 1
        THEN make_date(EXTRACT(YEAR FROM {date_col})::int - 1, 8, 1)
    WHEN EXTRACT(MONTH FROM {date_col}) BETWEEN 2 AND 7
        THEN make_date(EXTRACT(YEAR FROM {date_col})::int, 2, 1)
    ELSE make_date(EXTRACT(YEAR FROM {date_col})::int, 8, 1)
END
"""


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def create_tables(cur: psycopg.Cursor[Any]) -> None:
    for table in TABLES:
        columns = table.columns.format(timestamps=COMMON_TIMESTAMPS.strip())
        cur.execute(
            sql.SQL("CREATE TABLE {}.{} ({})").format(
                sql.Identifier(SCHEMA), sql.Identifier(table.name), sql.SQL(columns)
            )
        )
    log("33张目标表结构创建完成（尚未提交）")


def insert_and_count(cur: psycopg.Cursor[Any], table: str, statement: str) -> int:
    started = time.perf_counter()
    cur.execute(statement)
    inserted = cur.rowcount
    log(f"{table}: 写入 {inserted:,} 行，用时 {time.perf_counter() - started:.1f}s")
    return inserted


def assert_equal(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise RuntimeError(f"校验失败 [{label}]：实际={actual!r}，期望={expected!r}")


def scalar(cur: psycopg.Cursor[Any], statement: str) -> Any:
    cur.execute(statement)
    row = cur.fetchone()
    return row[0] if row else None


def main() -> int:
    settings = get_settings()

    row_counts: dict[str, int] = {}
    started_all = time.perf_counter()
    log(f"连接数据库 {DATABASE}.{SCHEMA}，准备启动单一事务")

    with psycopg.connect(
        settings.database_url,
        connect_timeout=settings.database_connect_timeout,
        application_name="build_alibaba_remaining_33_tables",
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = 0")
            cur.execute("SET LOCAL lock_timeout = '10s'")
            cur.execute("SET LOCAL idle_in_transaction_session_timeout = 0")
            cur.execute("SET LOCAL work_mem = '64MB'")
            cur.execute("SET LOCAL maintenance_work_mem = '512MB'")
            cur.execute("SET LOCAL temp_buffers = '128MB'")
            cur.execute("SET LOCAL max_parallel_workers_per_gather = 4")
            cur.execute("SET LOCAL synchronous_commit = on")
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{DATABASE}.{SCHEMA}.remaining33.v1",))

            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """, (SCHEMA,))
            existing_tables = [row[0] for row in cur.fetchall()]
            assert_equal("现有表集合", existing_tables, ["customer_id_mapping", "raw_data"])

            cur.execute("""
                SELECT table_name, COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name IN ('raw_data', 'customer_id_mapping')
                GROUP BY table_name
            """, (SCHEMA,))
            source_column_counts = dict(cur.fetchall())
            assert_equal("raw_data字段数", source_column_counts.get("raw_data"), 81)
            assert_equal("customer_id_mapping字段数", source_column_counts.get("customer_id_mapping"), 6)
            assert_equal("raw_data行数", scalar(cur, f'SELECT COUNT(*) FROM {SCHEMA}.raw_data'), EXPECTED_RAW_ROWS)
            assert_equal("客户ID表行数", scalar(cur, f'SELECT COUNT(*) FROM {SCHEMA}.customer_id_mapping'), EXPECTED_CUSTOMERS)

            preflight = scalar(cur, f"""
                SELECT COUNT(*)
                FROM {SCHEMA}.raw_data
                WHERE NULLIF(BTRIM("付款日期"), '') IS NULL
                   OR NULLIF(BTRIM("买家ID"), '') IS NULL
                   OR NULLIF(BTRIM("商品编码"), '') IS NULL
                   OR "订单状态" NOT IN ('已取消', '已发货')
            """)
            assert_equal("关键字段及订单状态异常行数", preflight, 0)
            log("源表结构、行数、关键字段和订单状态预检通过")

            quarter_expression = QUARTER_START_FROM_DATE.format(date_col="transaction_date").strip()
            half_expression = HALF_START_FROM_DATE.format(date_col="transaction_date").strip()
            cur.execute(f"""
                CREATE TEMP TABLE tmp_alibaba_fact ON COMMIT DROP AS
                WITH normalized AS (
                    SELECT
                        NULLIF(BTRIM("付款日期"), '')::timestamp::date AS transaction_date,
                        NULLIF(BTRIM("买家ID"), '')::varchar(255) AS customer_id,
                        NULLIF(BTRIM("商品编码"), '')::varchar(255) AS product_code,
                        COALESCE(NULLIF(BTRIM("销售数量"), '')::numeric, 0)::numeric(18,4) AS product_quantity,
                        COALESCE(NULLIF(BTRIM("销售金额"), '')::numeric, 0) AS sales_amount,
                        COALESCE(NULLIF(BTRIM("实退数量"), '')::numeric, 0) AS refund_quantity,
                        COALESCE(NULLIF(BTRIM("退货金额"), '')::numeric, 0) AS return_amount
                    FROM {SCHEMA}.raw_data
                    WHERE "订单状态" = '已发货'
                ), calculated AS (
                    SELECT
                        transaction_date,
                        customer_id,
                        product_code,
                        product_quantity,
                        ROUND(sales_amount, 2)::numeric(18,2) AS transaction_amount,
                        ROUND(return_amount, 2)::numeric(18,2) AS refund_amount
                    FROM normalized
                )
                SELECT
                    transaction_date,
                    customer_id,
                    product_code,
                    product_quantity,
                    transaction_amount,
                    refund_amount,
                    (product_quantity <> 0 OR transaction_amount <> 0) AS effective_purchase,
                    date_trunc('week', transaction_date)::date AS week_start,
                    (date_trunc('week', transaction_date)::date + 6) AS week_end,
                    date_trunc('month', transaction_date)::date AS month_start,
                    (date_trunc('month', transaction_date)::date + INTERVAL '1 month - 1 day')::date AS month_end,
                    ({quarter_expression})::date AS quarter_start,
                    (({quarter_expression})::date + INTERVAL '3 months - 1 day')::date AS quarter_end,
                    ({half_expression})::date AS half_start,
                    (({half_expression})::date + INTERVAL '6 months - 1 day')::date AS half_end
                FROM calculated
            """)
            cur.execute("ANALYZE tmp_alibaba_fact")
            log("类型化临时事实层创建完成；原始文本仅解析一次")

            cur.execute("""
                SELECT COUNT(*),
                       COALESCE(SUM(transaction_amount), 0),
                       COALESCE(SUM(refund_amount), 0),
                       MIN(transaction_date), MAX(transaction_date),
                       COUNT(DISTINCT customer_id), COUNT(DISTINCT product_code)
                FROM tmp_alibaba_fact
            """)
            baseline = cur.fetchone()
            assert_equal("已发货事实层行数", baseline[0], EXPECTED_SHIPPED_ROWS)
            expected_transaction_amount = baseline[1]
            expected_refund_amount = baseline[2]
            log(
                f"事实基线：{baseline[3]}~{baseline[4]}，客户 {baseline[5]:,}，商品 {baseline[6]:,}，"
                f"交易额 {baseline[1]}，退款额 {baseline[2]}"
            )

            create_tables(cur)

            insert_and_count(cur, "daily_sales", f"""
                INSERT INTO {SCHEMA}.daily_sales (transaction_date, transaction_amount)
                SELECT transaction_date, SUM(transaction_amount)::numeric(18,2)
                FROM tmp_alibaba_fact GROUP BY transaction_date
            """)
            insert_and_count(cur, "daily_product_sales", f"""
                INSERT INTO {SCHEMA}.daily_product_sales
                    (transaction_date, product_code, transaction_amount, product_quantity)
                SELECT transaction_date, product_code,
                       SUM(transaction_amount)::numeric(18,2), SUM(product_quantity)::numeric(18,4)
                FROM tmp_alibaba_fact GROUP BY transaction_date, product_code
            """)
            insert_and_count(cur, "daily_customer_sales", f"""
                INSERT INTO {SCHEMA}.daily_customer_sales
                    (transaction_date, customer_id, transaction_amount)
                SELECT transaction_date, customer_id, SUM(transaction_amount)::numeric(18,2)
                FROM tmp_alibaba_fact GROUP BY transaction_date, customer_id
            """)

            insert_and_count(cur, "weekly_sales", f"""
                INSERT INTO {SCHEMA}.weekly_sales (period_start, period_end, weekly_transaction_amount)
                SELECT date_trunc('week', transaction_date)::date,
                       date_trunc('week', transaction_date)::date + 6,
                       SUM(transaction_amount)::numeric(18,2)
                FROM {SCHEMA}.daily_sales GROUP BY 1, 2
            """)
            insert_and_count(cur, "weekly_refunds", f"""
                INSERT INTO {SCHEMA}.weekly_refunds (period_start, period_end, weekly_refund_amount)
                SELECT week_start, week_end, SUM(refund_amount)::numeric(18,2)
                FROM tmp_alibaba_fact GROUP BY week_start, week_end
            """)
            insert_and_count(cur, "weekly_product_sales", f"""
                INSERT INTO {SCHEMA}.weekly_product_sales
                    (period_start, period_end, product_code, weekly_transaction_amount, weekly_product_quantity)
                SELECT date_trunc('week', transaction_date)::date,
                       date_trunc('week', transaction_date)::date + 6,
                       product_code, SUM(transaction_amount)::numeric(18,2), SUM(product_quantity)::numeric(18,4)
                FROM {SCHEMA}.daily_product_sales GROUP BY 1, 2, product_code
            """)
            insert_and_count(cur, "weekly_customer_sales", f"""
                INSERT INTO {SCHEMA}.weekly_customer_sales
                    (period_start, period_end, customer_id, weekly_transaction_amount)
                SELECT date_trunc('week', transaction_date)::date,
                       date_trunc('week', transaction_date)::date + 6,
                       customer_id, SUM(transaction_amount)::numeric(18,2)
                FROM {SCHEMA}.daily_customer_sales GROUP BY 1, 2, customer_id
            """)

            insert_and_count(cur, "monthly_sales", f"""
                INSERT INTO {SCHEMA}.monthly_sales (period_start, period_end, monthly_transaction_amount)
                SELECT date_trunc('month', transaction_date)::date,
                       (date_trunc('month', transaction_date)::date + INTERVAL '1 month - 1 day')::date,
                       SUM(transaction_amount)::numeric(18,2)
                FROM {SCHEMA}.daily_sales GROUP BY 1, 2
            """)
            insert_and_count(cur, "monthly_refunds", f"""
                INSERT INTO {SCHEMA}.monthly_refunds (period_start, period_end, monthly_refund_amount)
                SELECT month_start, month_end, SUM(refund_amount)::numeric(18,2)
                FROM tmp_alibaba_fact GROUP BY month_start, month_end
            """)
            insert_and_count(cur, "monthly_product_sales", f"""
                INSERT INTO {SCHEMA}.monthly_product_sales
                    (period_start, period_end, product_code, monthly_transaction_amount, monthly_product_quantity)
                SELECT date_trunc('month', transaction_date)::date,
                       (date_trunc('month', transaction_date)::date + INTERVAL '1 month - 1 day')::date,
                       product_code, SUM(transaction_amount)::numeric(18,2), SUM(product_quantity)::numeric(18,4)
                FROM {SCHEMA}.daily_product_sales GROUP BY 1, 2, product_code
            """)
            insert_and_count(cur, "monthly_customer_sales", f"""
                INSERT INTO {SCHEMA}.monthly_customer_sales
                    (period_start, period_end, customer_id, monthly_transaction_amount)
                SELECT date_trunc('month', transaction_date)::date,
                       (date_trunc('month', transaction_date)::date + INTERVAL '1 month - 1 day')::date,
                       customer_id, SUM(transaction_amount)::numeric(18,2)
                FROM {SCHEMA}.daily_customer_sales GROUP BY 1, 2, customer_id
            """)

            quarter_from_period = QUARTER_START_FROM_DATE.format(date_col="period_start").strip()
            half_from_period = HALF_START_FROM_DATE.format(date_col="period_start").strip()
            insert_and_count(cur, "quarterly_sales", f"""
                INSERT INTO {SCHEMA}.quarterly_sales (period_start, period_end, quarterly_transaction_amount)
                SELECT q_start, (q_start + INTERVAL '3 months - 1 day')::date,
                       SUM(monthly_transaction_amount)::numeric(18,2)
                FROM (SELECT ({quarter_from_period})::date q_start, monthly_transaction_amount
                      FROM {SCHEMA}.monthly_sales) s
                GROUP BY q_start
            """)
            insert_and_count(cur, "quarterly_refunds", f"""
                INSERT INTO {SCHEMA}.quarterly_refunds (period_start, period_end, quarterly_refund_amount)
                SELECT q_start, (q_start + INTERVAL '3 months - 1 day')::date,
                       SUM(monthly_refund_amount)::numeric(18,2)
                FROM (SELECT ({quarter_from_period})::date q_start, monthly_refund_amount
                      FROM {SCHEMA}.monthly_refunds) s
                GROUP BY q_start
            """)
            insert_and_count(cur, "quarterly_product_sales", f"""
                INSERT INTO {SCHEMA}.quarterly_product_sales
                    (period_start, period_end, product_code, quarterly_transaction_amount, quarterly_product_quantity)
                SELECT q_start, (q_start + INTERVAL '3 months - 1 day')::date, product_code,
                       SUM(monthly_transaction_amount)::numeric(18,2), SUM(monthly_product_quantity)::numeric(18,4)
                FROM (SELECT ({quarter_from_period})::date q_start, product_code,
                             monthly_transaction_amount, monthly_product_quantity
                      FROM {SCHEMA}.monthly_product_sales) s
                GROUP BY q_start, product_code
            """)
            insert_and_count(cur, "quarterly_customer_sales", f"""
                INSERT INTO {SCHEMA}.quarterly_customer_sales
                    (period_start, period_end, customer_id, quarterly_transaction_amount)
                SELECT q_start, (q_start + INTERVAL '3 months - 1 day')::date, customer_id,
                       SUM(monthly_transaction_amount)::numeric(18,2)
                FROM (SELECT ({quarter_from_period})::date q_start, customer_id, monthly_transaction_amount
                      FROM {SCHEMA}.monthly_customer_sales) s
                GROUP BY q_start, customer_id
            """)

            insert_and_count(cur, "half_year_sales", f"""
                INSERT INTO {SCHEMA}.half_year_sales (period_start, period_end, half_year_transaction_amount)
                SELECT h_start, (h_start + INTERVAL '6 months - 1 day')::date,
                       SUM(monthly_transaction_amount)::numeric(18,2)
                FROM (SELECT ({half_from_period})::date h_start, monthly_transaction_amount
                      FROM {SCHEMA}.monthly_sales) s
                GROUP BY h_start
            """)
            insert_and_count(cur, "half_year_refunds", f"""
                INSERT INTO {SCHEMA}.half_year_refunds (period_start, period_end, half_year_refund_amount)
                SELECT h_start, (h_start + INTERVAL '6 months - 1 day')::date,
                       SUM(monthly_refund_amount)::numeric(18,2)
                FROM (SELECT ({half_from_period})::date h_start, monthly_refund_amount
                      FROM {SCHEMA}.monthly_refunds) s
                GROUP BY h_start
            """)
            insert_and_count(cur, "half_year_product_sales", f"""
                INSERT INTO {SCHEMA}.half_year_product_sales
                    (period_start, period_end, product_code, half_year_transaction_amount, half_year_product_quantity)
                SELECT h_start, (h_start + INTERVAL '6 months - 1 day')::date, product_code,
                       SUM(monthly_transaction_amount)::numeric(18,2), SUM(monthly_product_quantity)::numeric(18,4)
                FROM (SELECT ({half_from_period})::date h_start, product_code,
                             monthly_transaction_amount, monthly_product_quantity
                      FROM {SCHEMA}.monthly_product_sales) s
                GROUP BY h_start, product_code
            """)
            insert_and_count(cur, "half_year_customer_sales", f"""
                INSERT INTO {SCHEMA}.half_year_customer_sales
                    (period_start, period_end, customer_id, half_year_transaction_amount)
                SELECT h_start, (h_start + INTERVAL '6 months - 1 day')::date, customer_id,
                       SUM(monthly_transaction_amount)::numeric(18,2)
                FROM (SELECT ({half_from_period})::date h_start, customer_id, monthly_transaction_amount
                      FROM {SCHEMA}.monthly_customer_sales) s
                GROUP BY h_start, customer_id
            """)

            insert_and_count(cur, "daily_sales_metrics", f"""
                INSERT INTO {SCHEMA}.daily_sales_metrics
                    (transaction_date, transaction_amount, year_over_year_rate,
                     rolling_7_day_transaction_amount, rolling_30_day_transaction_amount)
                SELECT d.transaction_date, d.transaction_amount,
                       CASE WHEN y.transaction_amount IS NULL OR y.transaction_amount = 0 THEN 0
                            ELSE ROUND((d.transaction_amount / y.transaction_amount - 1) * 100, 2) END,
                       (SELECT SUM(r.transaction_amount) FROM {SCHEMA}.daily_sales r
                        WHERE r.transaction_date BETWEEN d.transaction_date - 6 AND d.transaction_date)::numeric(18,2),
                       (SELECT SUM(r.transaction_amount) FROM {SCHEMA}.daily_sales r
                        WHERE r.transaction_date BETWEEN d.transaction_date - 29 AND d.transaction_date)::numeric(18,2)
                FROM {SCHEMA}.daily_sales d
                LEFT JOIN {SCHEMA}.daily_sales y
                  ON y.transaction_date = (d.transaction_date - INTERVAL '1 year')::date
            """)
            insert_and_count(cur, "weekly_sales_metrics", f"""
                INSERT INTO {SCHEMA}.weekly_sales_metrics
                    (period_start, period_end, weekly_transaction_amount, week_over_week_rate)
                SELECT w.period_start, w.period_end, w.weekly_transaction_amount,
                       CASE WHEN p.weekly_transaction_amount IS NULL OR p.weekly_transaction_amount = 0 THEN 0
                            ELSE ROUND((w.weekly_transaction_amount / p.weekly_transaction_amount - 1) * 100, 2) END
                FROM {SCHEMA}.weekly_sales w
                LEFT JOIN {SCHEMA}.weekly_sales p ON p.period_start = w.period_start - 7
            """)
            insert_and_count(cur, "monthly_sales_metrics", f"""
                INSERT INTO {SCHEMA}.monthly_sales_metrics
                    (period_start, period_end, monthly_transaction_amount, month_over_month_rate)
                SELECT m.period_start, m.period_end, m.monthly_transaction_amount,
                       CASE WHEN p.monthly_transaction_amount IS NULL OR p.monthly_transaction_amount = 0 THEN 0
                            ELSE ROUND((m.monthly_transaction_amount / p.monthly_transaction_amount - 1) * 100, 2) END
                FROM {SCHEMA}.monthly_sales m
                LEFT JOIN {SCHEMA}.monthly_sales p
                  ON p.period_start = (m.period_start - INTERVAL '1 month')::date
            """)

            insert_and_count(cur, "customer_daily_sales", f"""
                INSERT INTO {SCHEMA}.customer_daily_sales
                    (transaction_date, customer_id, transaction_amount)
                SELECT f.transaction_date, f.customer_id, SUM(f.transaction_amount)::numeric(18,2)
                FROM tmp_alibaba_fact f
                JOIN (
                    SELECT DISTINCT transaction_date, customer_id
                    FROM tmp_alibaba_fact WHERE effective_purchase
                ) e USING (transaction_date, customer_id)
                GROUP BY f.customer_id, f.transaction_date
            """)
            insert_and_count(cur, "customer_daily_sales_metrics", f"""
                INSERT INTO {SCHEMA}.customer_daily_sales_metrics
                    (transaction_date, customer_id, transaction_amount,
                     rolling_7_day_transaction_amount, rolling_30_day_transaction_amount)
                SELECT transaction_date, customer_id, transaction_amount,
                       SUM(transaction_amount) OVER (
                           PARTITION BY customer_id ORDER BY transaction_date
                           RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW
                       )::numeric(18,2),
                       SUM(transaction_amount) OVER (
                           PARTITION BY customer_id ORDER BY transaction_date
                           RANGE BETWEEN INTERVAL '29 days' PRECEDING AND CURRENT ROW
                       )::numeric(18,2)
                FROM {SCHEMA}.customer_daily_sales
            """)
            insert_and_count(cur, "customer_weekly_sales", f"""
                INSERT INTO {SCHEMA}.customer_weekly_sales
                    (period_start, period_end, customer_id, weekly_transaction_amount, weekly_purchase_count)
                SELECT date_trunc('week', transaction_date)::date,
                       date_trunc('week', transaction_date)::date + 6,
                       customer_id, SUM(transaction_amount)::numeric(18,2), COUNT(*)::integer
                FROM {SCHEMA}.customer_daily_sales GROUP BY customer_id, 1, 2
            """)
            insert_and_count(cur, "customer_monthly_sales", f"""
                INSERT INTO {SCHEMA}.customer_monthly_sales
                    (period_start, period_end, customer_id, monthly_transaction_amount, monthly_purchase_count)
                SELECT date_trunc('month', transaction_date)::date,
                       (date_trunc('month', transaction_date)::date + INTERVAL '1 month - 1 day')::date,
                       customer_id, SUM(transaction_amount)::numeric(18,2), COUNT(*)::integer
                FROM {SCHEMA}.customer_daily_sales GROUP BY customer_id, 1, 2
            """)
            insert_and_count(cur, "customer_quarterly_sales", f"""
                INSERT INTO {SCHEMA}.customer_quarterly_sales
                    (period_start, period_end, customer_id,
                     quarterly_transaction_amount, quarterly_purchase_count)
                SELECT quarter_start, quarter_end, customer_id,
                       SUM(transaction_amount)::numeric(18,2), COUNT(*)::integer
                FROM (
                    SELECT customer_id, transaction_amount,
                           ({quarter_expression})::date quarter_start,
                           (({quarter_expression})::date + INTERVAL '3 months - 1 day')::date quarter_end
                    FROM {SCHEMA}.customer_daily_sales
                ) s GROUP BY customer_id, quarter_start, quarter_end
            """)
            insert_and_count(cur, "customer_half_year_sales", f"""
                INSERT INTO {SCHEMA}.customer_half_year_sales
                    (period_start, period_end, customer_id,
                     half_year_transaction_amount, half_year_purchase_count)
                SELECT half_start, half_end, customer_id,
                       SUM(transaction_amount)::numeric(18,2), COUNT(*)::integer
                FROM (
                    SELECT customer_id, transaction_amount,
                           ({half_expression})::date half_start,
                           (({half_expression})::date + INTERVAL '6 months - 1 day')::date half_end
                    FROM {SCHEMA}.customer_daily_sales
                ) s GROUP BY customer_id, half_start, half_end
            """)

            insert_and_count(cur, "customer_daily_product_sales", f"""
                INSERT INTO {SCHEMA}.customer_daily_product_sales
                    (transaction_date, customer_id, product_code, transaction_amount, product_quantity)
                SELECT transaction_date, customer_id, product_code,
                       SUM(transaction_amount)::numeric(18,2), SUM(product_quantity)::numeric(18,4)
                FROM tmp_alibaba_fact GROUP BY customer_id, transaction_date, product_code
            """)
            insert_and_count(cur, "customer_monthly_product_sales", f"""
                INSERT INTO {SCHEMA}.customer_monthly_product_sales
                    (period_start, period_end, customer_id, product_code,
                     monthly_transaction_amount, monthly_product_quantity)
                SELECT date_trunc('month', transaction_date)::date,
                       (date_trunc('month', transaction_date)::date + INTERVAL '1 month - 1 day')::date,
                       customer_id, product_code,
                       SUM(transaction_amount)::numeric(18,2), SUM(product_quantity)::numeric(18,4)
                FROM {SCHEMA}.customer_daily_product_sales GROUP BY customer_id, product_code, 1, 2
            """)
            insert_and_count(cur, "customer_quarterly_product_sales", f"""
                INSERT INTO {SCHEMA}.customer_quarterly_product_sales
                    (period_start, period_end, customer_id, product_code,
                     quarterly_transaction_amount, quarterly_product_quantity)
                SELECT q_start, (q_start + INTERVAL '3 months - 1 day')::date, customer_id, product_code,
                       SUM(monthly_transaction_amount)::numeric(18,2), SUM(monthly_product_quantity)::numeric(18,4)
                FROM (SELECT ({quarter_from_period})::date q_start, customer_id, product_code,
                             monthly_transaction_amount, monthly_product_quantity
                      FROM {SCHEMA}.customer_monthly_product_sales) s
                GROUP BY customer_id, product_code, q_start
            """)
            insert_and_count(cur, "customer_half_year_product_sales", f"""
                INSERT INTO {SCHEMA}.customer_half_year_product_sales
                    (period_start, period_end, customer_id, product_code,
                     half_year_transaction_amount, half_year_product_quantity)
                SELECT h_start, (h_start + INTERVAL '6 months - 1 day')::date, customer_id, product_code,
                       SUM(monthly_transaction_amount)::numeric(18,2), SUM(monthly_product_quantity)::numeric(18,4)
                FROM (SELECT ({half_from_period})::date h_start, customer_id, product_code,
                             monthly_transaction_amount, monthly_product_quantity
                      FROM {SCHEMA}.customer_monthly_product_sales) s
                GROUP BY customer_id, product_code, h_start
            """)

            insert_and_count(cur, "customer_health_detail", f"""
                INSERT INTO {SCHEMA}.customer_health_detail
                    (period_start, period_end, customer_id,
                     week_period_start, week_period_end, month_period_start, month_period_end,
                     week_purchase_count, week_score, month_purchase_count, month_score,
                     customer_score, customer_health_status, state_instructions, follow_up_action)
                WITH global_bound AS (
                    SELECT MAX(period_start) AS latest_week FROM {SCHEMA}.customer_weekly_sales
                ), customer_bounds AS (
                    SELECT customer_id, MIN(period_start) AS first_week
                    FROM {SCHEMA}.customer_weekly_sales GROUP BY customer_id
                ), calendar AS (
                    SELECT b.customer_id, gs::date AS period_start, (gs::date + 6) AS period_end
                    FROM customer_bounds b CROSS JOIN global_bound g
                    CROSS JOIN LATERAL generate_series(b.first_week, g.latest_week, INTERVAL '7 days') gs
                ), counts AS (
                    SELECT c.*,
                           date_trunc('month', c.period_start)::date AS month_period_start,
                           (date_trunc('month', c.period_end)::date + INTERVAL '1 month - 1 day')::date AS month_period_end,
                           COALESCE(w.weekly_purchase_count, 0)::integer AS week_purchase_count,
                           CASE
                               WHEN date_trunc('month', c.period_start)::date = date_trunc('month', c.period_end)::date
                                   THEN COALESCE(m1.monthly_purchase_count, 0)::numeric(10,2)
                               ELSE ROUND((COALESCE(m1.monthly_purchase_count, 0)
                                         + COALESCE(m2.monthly_purchase_count, 0)) / 2.0, 2)::numeric(10,2)
                           END AS month_purchase_count
                    FROM calendar c
                    LEFT JOIN {SCHEMA}.customer_weekly_sales w
                      ON w.customer_id = c.customer_id AND w.period_start = c.period_start
                    LEFT JOIN {SCHEMA}.customer_monthly_sales m1
                      ON m1.customer_id = c.customer_id
                     AND m1.period_start = date_trunc('month', c.period_start)::date
                    LEFT JOIN {SCHEMA}.customer_monthly_sales m2
                      ON m2.customer_id = c.customer_id
                     AND m2.period_start = date_trunc('month', c.period_end)::date
                ), sub_scores AS (
                    SELECT *,
                           CASE
                               WHEN week_purchase_count >= 7 THEN 100 WHEN week_purchase_count >= 6 THEN 90
                               WHEN week_purchase_count >= 5 THEN 80 WHEN week_purchase_count >= 4 THEN 70
                               WHEN week_purchase_count >= 3 THEN 50 WHEN week_purchase_count >= 2 THEN 30
                               WHEN week_purchase_count >= 1 THEN 10 ELSE 0
                           END::numeric(5,2) AS week_score,
                           CASE
                               WHEN month_purchase_count >= 30 THEN 100 WHEN month_purchase_count >= 20 THEN 80
                               WHEN month_purchase_count >= 15 THEN 60 WHEN month_purchase_count >= 10 THEN 40
                               WHEN month_purchase_count >= 5 THEN 20 ELSE 10
                           END::numeric(5,2) AS month_score
                    FROM counts
                ), final_scores AS (
                    SELECT *, ROUND(0.7 * week_score + 0.3 * month_score, 2)::numeric(5,2) AS customer_score
                    FROM sub_scores
                )
                SELECT period_start, period_end, customer_id,
                       period_start, period_end, month_period_start, month_period_end,
                       week_purchase_count, week_score, month_purchase_count, month_score, customer_score,
                       CASE
                           WHEN customer_score >= 90 THEN '高活跃' WHEN customer_score >= 80 THEN '活跃'
                           WHEN customer_score >= 70 THEN '稳定' WHEN customer_score >= 60 THEN '观察'
                           WHEN customer_score >= 50 THEN '风险' WHEN customer_score >= 40 THEN '流失预警'
                           ELSE '流失'
                       END,
                       NULL, NULL
                FROM final_scores
            """)

            log("开始后置创建33个业务唯一键（避免逐行维护索引）")
            for table in TABLES:
                constraint_name = f"uq_{table.name}_business"
                identifiers = sql.SQL(", ").join(sql.Identifier(column) for column in table.unique_columns)
                cur.execute(
                    sql.SQL("ALTER TABLE {}.{} ADD CONSTRAINT {} UNIQUE ({})").format(
                        sql.Identifier(SCHEMA), sql.Identifier(table.name),
                        sql.Identifier(constraint_name), identifiers
                    )
                )
            log("全部业务唯一键创建完成")

            # Validate full-table totals across every aggregation branch.
            amount_checks = {
                "daily_sales": "transaction_amount",
                "daily_product_sales": "transaction_amount",
                "daily_customer_sales": "transaction_amount",
                "weekly_sales": "weekly_transaction_amount",
                "weekly_product_sales": "weekly_transaction_amount",
                "weekly_customer_sales": "weekly_transaction_amount",
                "monthly_sales": "monthly_transaction_amount",
                "monthly_product_sales": "monthly_transaction_amount",
                "monthly_customer_sales": "monthly_transaction_amount",
                "quarterly_sales": "quarterly_transaction_amount",
                "quarterly_product_sales": "quarterly_transaction_amount",
                "quarterly_customer_sales": "quarterly_transaction_amount",
                "half_year_sales": "half_year_transaction_amount",
                "half_year_product_sales": "half_year_transaction_amount",
                "half_year_customer_sales": "half_year_transaction_amount",
                "daily_sales_metrics": "transaction_amount",
                "weekly_sales_metrics": "weekly_transaction_amount",
                "monthly_sales_metrics": "monthly_transaction_amount",
                "customer_daily_sales": "transaction_amount",
                "customer_daily_sales_metrics": "transaction_amount",
                "customer_weekly_sales": "weekly_transaction_amount",
                "customer_monthly_sales": "monthly_transaction_amount",
                "customer_quarterly_sales": "quarterly_transaction_amount",
                "customer_half_year_sales": "half_year_transaction_amount",
                "customer_daily_product_sales": "transaction_amount",
                "customer_monthly_product_sales": "monthly_transaction_amount",
                "customer_quarterly_product_sales": "quarterly_transaction_amount",
                "customer_half_year_product_sales": "half_year_transaction_amount",
            }
            for table, column in amount_checks.items():
                total = scalar(cur, f"SELECT COALESCE(SUM({column}), 0) FROM {SCHEMA}.{table}")
                assert_equal(f"{table}交易金额守恒", total, expected_transaction_amount)

            refund_checks = {
                "weekly_refunds": "weekly_refund_amount",
                "monthly_refunds": "monthly_refund_amount",
                "quarterly_refunds": "quarterly_refund_amount",
                "half_year_refunds": "half_year_refund_amount",
            }
            for table, column in refund_checks.items():
                total = scalar(cur, f"SELECT COALESCE(SUM({column}), 0) FROM {SCHEMA}.{table}")
                assert_equal(f"{table}退款金额守恒", total, expected_refund_amount)

            quantity_checks = {
                "daily_product_sales": "product_quantity",
                "weekly_product_sales": "weekly_product_quantity",
                "monthly_product_sales": "monthly_product_quantity",
                "quarterly_product_sales": "quarterly_product_quantity",
                "half_year_product_sales": "half_year_product_quantity",
                "customer_daily_product_sales": "product_quantity",
                "customer_monthly_product_sales": "monthly_product_quantity",
                "customer_quarterly_product_sales": "quarterly_product_quantity",
                "customer_half_year_product_sales": "half_year_product_quantity",
            }
            fact_quantity = scalar(cur, "SELECT COALESCE(SUM(product_quantity), 0) FROM tmp_alibaba_fact")
            for table, column in quantity_checks.items():
                total = scalar(cur, f"SELECT COALESCE(SUM({column}), 0) FROM {SCHEMA}.{table}")
                assert_equal(f"{table}商品数量守恒", total, fact_quantity)

            assert_equal(
                "客户映射覆盖",
                scalar(cur, f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT customer_id FROM {SCHEMA}.daily_customer_sales
                        EXCEPT SELECT customer_id FROM {SCHEMA}.customer_id_mapping
                    ) x
                """),
                0,
            )
            assert_equal(
                "健康度预计行数",
                scalar(cur, f"SELECT COUNT(*) FROM {SCHEMA}.customer_health_detail"),
                scalar(cur, f"""
                    WITH g AS (SELECT MAX(period_start) latest_week FROM {SCHEMA}.customer_weekly_sales),
                    b AS (SELECT customer_id, MIN(period_start) first_week
                          FROM {SCHEMA}.customer_weekly_sales GROUP BY customer_id)
                    SELECT SUM(((g.latest_week - b.first_week) / 7) + 1)::bigint FROM b CROSS JOIN g
                """),
            )
            assert_equal(
                "健康度得分及状态公式",
                scalar(cur, f"""
                    SELECT COUNT(*) FROM {SCHEMA}.customer_health_detail
                    WHERE customer_score <> ROUND(0.7 * week_score + 0.3 * month_score, 2)
                       OR customer_health_status <> CASE
                           WHEN customer_score >= 90 THEN '高活跃' WHEN customer_score >= 80 THEN '活跃'
                           WHEN customer_score >= 70 THEN '稳定' WHEN customer_score >= 60 THEN '观察'
                           WHEN customer_score >= 50 THEN '风险' WHEN customer_score >= 40 THEN '流失预警'
                           ELSE '流失' END
                """),
                0,
            )
            assert_equal(
                "健康度周连续性",
                scalar(cur, f"""
                    SELECT COUNT(*) FROM (
                        SELECT period_start,
                               LAG(period_start) OVER (PARTITION BY customer_id ORDER BY period_start) previous_start
                        FROM {SCHEMA}.customer_health_detail
                    ) s WHERE previous_start IS NOT NULL AND period_start <> previous_start + 7
                """),
                0,
            )
            assert_equal(
                "健康度分销组说明默认值",
                scalar(cur, f"""
                    SELECT COUNT(*) FROM {SCHEMA}.customer_health_detail
                    WHERE state_instructions IS NOT NULL OR follow_up_action IS NOT NULL
                """),
                0,
            )

            for table in TABLES:
                row_counts[table.name] = scalar(cur, f"SELECT COUNT(*) FROM {SCHEMA}.{table.name}")
                if row_counts[table.name] <= 0:
                    raise RuntimeError(f"校验失败 [{table.name}]：表为空")
                cur.execute(sql.SQL("ANALYZE {}.{}").format(sql.Identifier(SCHEMA), sql.Identifier(table.name)))

            cur.execute("""
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = %s AND table_type = 'BASE TABLE'
            """, (SCHEMA,))
            assert_equal("Schema总表数", cur.fetchone()[0], 35)
            log("金额、退款、数量、客户覆盖、周期连续性、健康度公式及唯一键校验全部通过")
            log("准备提交事务；提交成功前其他会话看不到任何一张新表")

        conn.commit()

    elapsed = time.perf_counter() - started_all
    log(f"事务提交成功，总用时 {elapsed:.1f}s")
    print(json.dumps({
        "database": DATABASE,
        "schema": SCHEMA,
        "committed": True,
        "elapsed_seconds": round(elapsed, 1),
        "row_counts": row_counts,
    }, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        print("事务未提交；连接退出时将自动回滚全部33张表及数据。", file=sys.stderr, flush=True)
        raise
