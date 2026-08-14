from __future__ import annotations

import argparse
import json
import sys
import time
from itertools import count
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.settings import get_settings  # noqa: E402
from upload.alibaba.aggregate_refresh import refresh_aggregates as refresh_alibaba_aggregates  # noqa: E402
from upload.alibaba.incremental_refresh import (  # noqa: E402
    _prepare_scopes as prepare_alibaba_scopes,
)
from upload.jushuitan.aggregate_refresh import refresh_aggregates as refresh_jushuitan_aggregates  # noqa: E402
from upload.jushuitan.incremental_refresh import (  # noqa: E402
    _prepare_scopes as prepare_jushuitan_scopes,
)


STORE_AMOUNT_TABLES = (
    "daily_sales",
    "daily_product_sales",
    "daily_customer_sales",
    "weekly_sales",
    "weekly_refunds",
    "weekly_product_sales",
    "weekly_customer_sales",
    "monthly_sales",
    "monthly_refunds",
    "monthly_product_sales",
    "monthly_customer_sales",
    "quarterly_sales",
    "quarterly_refunds",
    "quarterly_product_sales",
    "quarterly_customer_sales",
    "half_year_sales",
    "half_year_refunds",
    "half_year_product_sales",
    "half_year_customer_sales",
    "daily_sales_metrics",
    "weekly_sales_metrics",
    "monthly_sales_metrics",
    "customer_daily_sales",
    "customer_daily_sales_metrics",
    "customer_weekly_sales",
    "customer_monthly_sales",
    "customer_quarterly_sales",
    "customer_half_year_sales",
    "customer_daily_product_sales",
    "customer_monthly_product_sales",
    "customer_quarterly_product_sales",
    "customer_half_year_product_sales",
)

PERIODS = (
    ("weekly", "week"),
    ("monthly", "month"),
    ("quarterly", "quarter"),
    ("half_year", "half"),
)

STORE_AMOUNT_CHECKS = {
    "overall": {
        "daily_sales": "transaction_amount",
        "weekly_sales": "weekly_transaction_amount",
        "monthly_sales": "monthly_transaction_amount",
        "quarterly_sales": "quarterly_transaction_amount",
        "half_year_sales": "half_year_transaction_amount",
        "daily_sales_metrics": "transaction_amount",
        "weekly_sales_metrics": "weekly_transaction_amount",
        "monthly_sales_metrics": "monthly_transaction_amount",
    },
    "product": {
        "daily_product_sales": "transaction_amount",
        "weekly_product_sales": "weekly_transaction_amount",
        "monthly_product_sales": "monthly_transaction_amount",
        "quarterly_product_sales": "quarterly_transaction_amount",
        "half_year_product_sales": "half_year_transaction_amount",
    },
    "customer": {
        "daily_customer_sales": "transaction_amount",
        "weekly_customer_sales": "weekly_transaction_amount",
        "monthly_customer_sales": "monthly_transaction_amount",
        "quarterly_customer_sales": "quarterly_transaction_amount",
        "half_year_customer_sales": "half_year_transaction_amount",
        "customer_daily_sales": "transaction_amount",
        "customer_daily_sales_metrics": "transaction_amount",
        "customer_weekly_sales": "weekly_transaction_amount",
        "customer_monthly_sales": "monthly_transaction_amount",
        "customer_quarterly_sales": "quarterly_transaction_amount",
        "customer_half_year_sales": "half_year_transaction_amount",
    },
    "customer_product": {
        "customer_daily_product_sales": "transaction_amount",
        "customer_monthly_product_sales": "monthly_transaction_amount",
        "customer_quarterly_product_sales": "quarterly_transaction_amount",
        "customer_half_year_product_sales": "half_year_transaction_amount",
    },
    "refund": {
        "weekly_refunds": "weekly_refund_amount",
        "monthly_refunds": "monthly_refund_amount",
        "quarterly_refunds": "quarterly_refund_amount",
        "half_year_refunds": "half_year_refund_amount",
    },
}

TEMP_COUNTER = count(1)


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def assert_equal(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise RuntimeError(f"校验失败 [{label}]：实际={actual!r}，期望={expected!r}")


def scalar(conn: psycopg.Connection, query: str, params: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(query, params).fetchone()
    if row is None:
        raise RuntimeError("标量查询未返回结果")
    return next(iter(row.values()))


def platform_dates(conn: psycopg.Connection, schema: str) -> tuple[Any, ...]:
    if schema == "alibaba":
        date_expression = "REPLACE(LEFT(BTRIM(COALESCE(\"付款日期\"::text, '')), 10), '/', '-')"
    else:
        date_expression = """
            REGEXP_REPLACE(
                REGEXP_REPLACE(
                    REPLACE(LEFT(BTRIM(COALESCE("付款日期"::text, '')), 10), '/', '-'),
                    '^2525', '2025'
                ),
                '^2024', '2026'
            )
        """
    rows = conn.execute(f'''
        SELECT DISTINCT ({date_expression})::date AS transaction_date
        FROM {schema}.raw_data
        WHERE BTRIM(COALESCE("订单状态"::text, ''), E' \\t\\n\\r') = '已发货'
          AND ({date_expression}) ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}$'
        ORDER BY transaction_date
    ''').fetchall()
    dates = tuple(row["transaction_date"] for row in rows)
    if not dates:
        raise RuntimeError(f"{schema}.raw_data没有可回刷的已发货日期")
    return dates


def raw_quality(conn: psycopg.Connection, schema: str) -> dict[str, Any]:
    if schema == "alibaba":
        date_expression = "REPLACE(LEFT(BTRIM(COALESCE(\"付款日期\"::text, '')), 10), '/', '-')"
    else:
        date_expression = """
            REGEXP_REPLACE(
                REGEXP_REPLACE(
                    REPLACE(LEFT(BTRIM(COALESCE("付款日期"::text, '')), 10), '/', '-'),
                    '^2525', '2025'
                ),
                '^2024', '2026'
            )
        """
    return dict(conn.execute(f'''
        WITH cleaned AS (
            SELECT
                BTRIM(COALESCE("订单状态"::text, ''), E' \\t\\n\\r') AS order_status,
                {date_expression} AS transaction_date,
                NULLIF(REGEXP_REPLACE(COALESCE("销售金额"::text, ''),
                    '[,￥¥[:space:]]', '', 'g'), '') AS sales_amount,
                NULLIF(REGEXP_REPLACE(COALESCE("退货金额"::text, ''),
                    '[,￥¥[:space:]]', '', 'g'), '') AS return_amount
            FROM {schema}.raw_data
        )
        SELECT
            COUNT(*)::bigint AS raw_rows,
            COUNT(*) FILTER (WHERE order_status = '已发货')::bigint AS shipped_rows,
            COUNT(*) FILTER (
                WHERE order_status = '已发货'
                  AND transaction_date !~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}$'
            )::bigint AS invalid_dates,
            COUNT(*) FILTER (
                WHERE order_status = '已发货' AND sales_amount IS NOT NULL
                  AND NOT pg_input_is_valid(sales_amount, 'numeric')
            )::bigint AS invalid_sales_amounts,
            COUNT(*) FILTER (
                WHERE order_status = '已发货' AND return_amount IS NOT NULL
                  AND NOT pg_input_is_valid(return_amount, 'numeric')
            )::bigint AS invalid_return_amounts
        FROM cleaned
    ''').fetchone())


def preflight_tables(conn: psycopg.Connection) -> None:
    required = set(STORE_AMOUNT_TABLES) | {"raw_data", "customer_id_mapping", "customer_health_detail"}
    for schema in ("alibaba", "jushuitan"):
        existing = {
            row["table_name"]
            for row in conn.execute('''
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ''', (schema,))
        }
        missing = sorted(required - existing)
        if missing:
            raise RuntimeError(f"{schema}缺少回刷所需表：{missing}")
    references = conn.execute('''
        SELECT source_ns.nspname AS source_schema, source.relname AS source_table,
               target_ns.nspname AS target_schema, target.relname AS target_table
        FROM pg_constraint constraint_info
        JOIN pg_class source ON source.oid = constraint_info.conrelid
        JOIN pg_namespace source_ns ON source_ns.oid = source.relnamespace
        JOIN pg_class target ON target.oid = constraint_info.confrelid
        JOIN pg_namespace target_ns ON target_ns.oid = target.relnamespace
        WHERE constraint_info.contype = 'f'
          AND target_ns.nspname = ANY(%s)
          AND target.relname = ANY(%s)
    ''', (["alibaba", "jushuitan"], list(STORE_AMOUNT_TABLES))).fetchall()
    if references:
        raise RuntimeError(f"金额表存在外键引用，拒绝回刷：{references}")


def prepare_platform_fact(
    conn: psycopg.Connection,
    schema: str,
    dates: tuple[Any, ...],
) -> None:
    if schema == "alibaba":
        prepare_alibaba_scopes(conn, dates)
        conn.execute(r'''
            CREATE TEMP TABLE upload_alibaba_fact ON COMMIT DROP AS
            WITH raw_filtered AS MATERIALIZED (
                SELECT
                    REPLACE(
                        LEFT(BTRIM(COALESCE(raw."付款日期"::text, '')), 10), '/', '-'
                    ) AS transaction_date_text,
                    NULLIF(REGEXP_REPLACE(COALESCE(raw."销售金额"::text, ''),
                        '[,￥¥[:space:]]', '', 'g'), '') AS sales_amount_text,
                    NULLIF(REGEXP_REPLACE(COALESCE(raw."退货金额"::text, ''),
                        '[,￥¥[:space:]]', '', 'g'), '') AS return_amount_text,
                    NULLIF(BTRIM(COALESCE(raw."商品编码"::text, ''), E' \t\n\r'), '')
                        AS product_code_text,
                    REGEXP_REPLACE(
                        BTRIM(COALESCE(raw."买家ID"::text, ''), E' \t\n\r'),
                        '\.0+$', ''
                    ) AS customer_id_text
                FROM alibaba.raw_data raw
                WHERE BTRIM(COALESCE(raw."订单状态"::text, ''), E' \t\n\r') = '已发货'
            ), typed AS (
                SELECT
                    transaction_date_text::date AS transaction_date,
                    CASE WHEN pg_input_is_valid(sales_amount_text, 'numeric')
                         THEN sales_amount_text::numeric ELSE 0 END AS sales_amount,
                    CASE WHEN pg_input_is_valid(return_amount_text, 'numeric')
                         THEN return_amount_text::numeric ELSE 0 END AS return_amount,
                    product_code_text,
                    customer_id_text
                FROM raw_filtered
                WHERE transaction_date_text ~ '^\d{4}-\d{2}-\d{2}$'
            )
            SELECT
                transaction_date,
                ROUND(sales_amount, 2)::numeric(18,2) AS transaction_amount,
                ROUND(return_amount, 2)::numeric(18,2) AS refund_amount,
                CASE WHEN product_code_text IS NOT NULL AND product_code_text <> '-'
                     THEN product_code_text END AS product_code,
                CASE WHEN customer_id_text NOT IN ('', '-', '0', '0.0')
                     THEN customer_id_text END AS customer_id,
                TRUE AS is_sale,
                return_amount <> 0 AS is_refund
            FROM typed
        ''')
    else:
        prepare_jushuitan_scopes(conn, dates)
        conn.execute(r'''
            CREATE TEMP TABLE upload_jushuitan_fact ON COMMIT DROP AS
            WITH raw_filtered AS MATERIALIZED (
                SELECT
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REPLACE(
                                LEFT(BTRIM(COALESCE(raw."付款日期"::text, '')), 10),
                                '/', '-'
                            ),
                            '^2525', '2025'
                        ),
                        '^2024', '2026'
                    ) AS transaction_date_text,
                    NULLIF(REGEXP_REPLACE(COALESCE(raw."销售金额"::text, ''),
                        '[,￥¥[:space:]]', '', 'g'), '') AS sales_amount_text,
                    NULLIF(REGEXP_REPLACE(COALESCE(raw."退货金额"::text, ''),
                        '[,￥¥[:space:]]', '', 'g'), '') AS return_amount_text,
                    NULLIF(BTRIM(COALESCE(raw."商品编码"::text, ''), E' \t\n\r'), '')
                        AS product_code_text,
                    BTRIM(COALESCE(raw."分销商"::text, ''), E' \t\n\r')
                        AS distributor_text,
                    BTRIM(COALESCE(raw."店铺"::text, ''), E' \t\n\r') AS shop_text
                FROM jushuitan.raw_data raw
                WHERE BTRIM(COALESCE(raw."订单状态"::text, ''), E' \t\n\r') = '已发货'
            ), typed AS (
                SELECT
                    transaction_date_text::date AS transaction_date,
                    CASE WHEN pg_input_is_valid(sales_amount_text, 'numeric')
                         THEN sales_amount_text::numeric ELSE 0 END AS sales_amount,
                    CASE WHEN pg_input_is_valid(return_amount_text, 'numeric')
                         THEN return_amount_text::numeric ELSE 0 END AS return_amount,
                    product_code_text,
                    distributor_text,
                    shop_text
                FROM raw_filtered
                WHERE transaction_date_text ~ '^\d{4}-\d{2}-\d{2}$'
            )
            SELECT
                transaction_date,
                ROUND(sales_amount, 2)::numeric(18,2) AS transaction_amount,
                ROUND(return_amount, 2)::numeric(18,2) AS refund_amount,
                CASE WHEN product_code_text IS NOT NULL AND product_code_text <> '-'
                     THEN product_code_text END AS product_code,
                CASE
                    WHEN distributor_text <> '' THEN distributor_text
                    WHEN shop_text LIKE '%童鞋%' THEN '童鞋'
                    WHEN shop_text LIKE '%晨秋%' THEN '晨秋'
                    WHEN shop_text LIKE '%老爸评测%' THEN '老爸评测'
                    WHEN shop_text LIKE ANY (ARRAY[
                        '%阿里巴巴%', '%京东商城%', '%拼多多%', '%奇门Wms%',
                        '%淘宝天猫%', '%头条放心购%', '%小红书%'
                    ]) THEN '戎井'
                    WHEN shop_text <> '' THEN shop_text
                END AS customer_id,
                TRUE AS is_sale,
                return_amount <> 0 AS is_refund
            FROM typed
        ''')
    conn.execute(f"CREATE INDEX ON upload_{schema}_fact (transaction_date)")
    conn.execute(f"CREATE INDEX ON upload_{schema}_fact (customer_id, transaction_date)")
    conn.execute(f"CREATE INDEX ON upload_{schema}_fact (product_code, transaction_date)")
    conn.execute(f"ANALYZE upload_{schema}_fact")


def fact_totals(conn: psycopg.Connection, schema: str) -> dict[str, Any]:
    fact = f"upload_{schema}_fact"
    return dict(conn.execute(f'''
        SELECT
            COUNT(*)::bigint AS shipped_rows,
            MIN(transaction_date) AS min_date,
            MAX(transaction_date) AS max_date,
            COALESCE(SUM(transaction_amount), 0)::numeric(30,2) AS overall,
            COALESCE(SUM(transaction_amount) FILTER (
                WHERE product_code IS NOT NULL
            ), 0)::numeric(30,2) AS product,
            COALESCE(SUM(transaction_amount) FILTER (
                WHERE customer_id IS NOT NULL
            ), 0)::numeric(30,2) AS customer,
            COALESCE(SUM(transaction_amount) FILTER (
                WHERE customer_id IS NOT NULL AND product_code IS NOT NULL
            ), 0)::numeric(30,2) AS customer_product,
            COALESCE(SUM(refund_amount), 0)::numeric(30,2) AS refund
        FROM {fact}
        WHERE is_sale
    ''').fetchone())


def update_existing_values(
    conn: psycopg.Connection,
    *,
    schema: str,
    table: str,
    keys: tuple[str, ...],
    values: tuple[str, ...],
    expected_select: str,
    apply_changes: bool,
) -> dict[str, int | str]:
    target = sql.Identifier(schema, table)
    temp = sql.Identifier(f"amount_backfill_expected_{next(TEMP_COUNTER)}")
    conn.execute(
        sql.SQL("CREATE TEMP TABLE {} ON COMMIT DROP AS ").format(temp)
        + sql.SQL(expected_select)
    )
    null_predicate = sql.SQL(" OR ").join(
        sql.SQL("{} IS NULL").format(sql.Identifier(column)) for column in (*keys, *values)
    )
    invalid = conn.execute(
        sql.SQL("SELECT COUNT(*)::bigint AS count FROM {} WHERE ").format(temp)
        + null_predicate
    ).fetchone()["count"]
    if invalid:
        raise RuntimeError(f"{schema}.{table}期望结果存在{invalid}条空键或空金额")

    duplicate = conn.execute(
        sql.SQL(
            "SELECT COALESCE(SUM(count - 1), 0)::bigint AS count FROM ("
            "SELECT COUNT(*)::bigint count FROM {} GROUP BY {} HAVING COUNT(*) > 1"
            ") duplicated"
        ).format(
            temp,
            sql.SQL(", ").join(sql.Identifier(column) for column in keys),
        )
    ).fetchone()["count"]
    if duplicate:
        raise RuntimeError(f"{schema}.{table}期望结果存在{duplicate}条重复业务键")

    key_join = sql.SQL(" AND ").join(
        sql.SQL("target.{0} = expected.{0}").format(sql.Identifier(column))
        for column in keys
    )
    missing = conn.execute(
        sql.SQL(
            "SELECT COUNT(*)::bigint AS count FROM {} expected WHERE NOT EXISTS ("
            "SELECT 1 FROM {} target WHERE {})"
        ).format(temp, target, key_join)
    ).fetchone()["count"]
    expected_rows = conn.execute(
        sql.SQL("SELECT COUNT(*)::bigint AS count FROM {}").format(temp)
    ).fetchone()["count"]
    if missing:
        raise RuntimeError(
            f"{schema}.{table}缺少{missing}个期望业务键；金额专用回刷不会擅自新增数量记录"
        )

    zeroed = 0
    updated = 0
    if apply_changes:
        zero_assignments = sql.SQL(", ").join(
            sql.SQL("{} = 0").format(sql.Identifier(column)) for column in values
        )
        zero_assignments += sql.SQL(", updated_at = CURRENT_TIMESTAMP")
        nonzero = sql.SQL(" OR ").join(
            sql.SQL("target.{} IS DISTINCT FROM 0").format(sql.Identifier(column))
            for column in values
        )
        zeroed = conn.execute(
            sql.SQL(
                "UPDATE {} target SET {} WHERE NOT EXISTS ("
                "SELECT 1 FROM {} expected WHERE {}) AND ({})"
            ).format(target, zero_assignments, temp, key_join, nonzero)
        ).rowcount

        value_assignments = sql.SQL(", ").join(
            sql.SQL("{0} = expected.{0}").format(sql.Identifier(column))
            for column in values
        )
        value_assignments += sql.SQL(", updated_at = CURRENT_TIMESTAMP")
        changed = sql.SQL(" OR ").join(
            sql.SQL("target.{0} IS DISTINCT FROM expected.{0}").format(
                sql.Identifier(column)
            )
            for column in values
        )
        updated = conn.execute(
            sql.SQL(
                "UPDATE {} target SET {} FROM {} expected WHERE {} AND ({})"
            ).format(target, value_assignments, temp, key_join, changed)
        ).rowcount

    conn.execute(sql.SQL("DROP TABLE {}").format(temp))
    result: dict[str, int | str] = {
        "schema": schema,
        "table": table,
        "expected_rows": expected_rows,
        "missing_keys": missing,
        "zeroed_rows": zeroed,
        "updated_rows": updated,
    }
    log(
        f"{schema}.{table}: expected={expected_rows:,}, "
        f"zeroed={zeroed:,}, updated={updated:,}"
    )
    return result


def refresh_store_amounts(
    conn: psycopg.Connection,
    schema: str,
    *,
    apply_changes: bool,
) -> list[dict[str, int | str]]:
    fact = f"upload_{schema}_fact"
    periods = f"upload_{schema}_periods"
    changes: list[dict[str, int | str]] = []

    def update(
        table: str,
        keys: tuple[str, ...],
        values: tuple[str, ...],
        expected: str,
    ) -> None:
        changes.append(update_existing_values(
            conn,
            schema=schema,
            table=table,
            keys=keys,
            values=values,
            expected_select=expected,
            apply_changes=apply_changes,
        ))

    update("daily_sales", ("transaction_date",), ("transaction_amount",), f'''
        SELECT transaction_date,
               SUM(transaction_amount)::numeric(18,2) AS transaction_amount
        FROM {fact}
        WHERE is_sale
        GROUP BY transaction_date
    ''')
    update(
        "daily_product_sales",
        ("transaction_date", "product_code"),
        ("transaction_amount",),
        f'''
            SELECT transaction_date, product_code,
                   SUM(transaction_amount)::numeric(18,2) AS transaction_amount
            FROM {fact}
            WHERE is_sale AND product_code IS NOT NULL
            GROUP BY transaction_date, product_code
        ''',
    )
    update(
        "daily_customer_sales",
        ("transaction_date", "customer_id"),
        ("transaction_amount",),
        f'''
            SELECT transaction_date, customer_id,
                   SUM(transaction_amount)::numeric(18,2) AS transaction_amount
            FROM {fact}
            WHERE is_sale AND customer_id IS NOT NULL
            GROUP BY transaction_date, customer_id
        ''',
    )

    for prefix, grain in PERIODS:
        amount = f"{prefix}_transaction_amount"
        refund = f"{prefix}_refund_amount"
        update(
            f"{prefix}_sales",
            ("period_start", "period_end"),
            (amount,),
            f'''
                SELECT scope.period_start, scope.period_end,
                       SUM(fact.transaction_amount)::numeric(18,2) AS {amount}
                FROM {periods} scope
                JOIN {fact} fact
                  ON fact.transaction_date BETWEEN scope.period_start AND scope.period_end
                 AND fact.is_sale
                WHERE scope.grain = '{grain}'
                GROUP BY scope.period_start, scope.period_end
            ''',
        )
        update(
            f"{prefix}_refunds",
            ("period_start", "period_end"),
            (refund,),
            f'''
                SELECT scope.period_start, scope.period_end,
                       COALESCE(SUM(fact.refund_amount) FILTER (
                           WHERE fact.is_refund
                       ), 0)::numeric(18,2) AS {refund}
                FROM {periods} scope
                LEFT JOIN {fact} fact
                  ON fact.transaction_date BETWEEN scope.period_start AND scope.period_end
                 AND fact.is_sale
                WHERE scope.grain = '{grain}'
                GROUP BY scope.period_start, scope.period_end
            ''',
        )
        update(
            f"{prefix}_product_sales",
            ("period_start", "period_end", "product_code"),
            (amount,),
            f'''
                SELECT scope.period_start, scope.period_end, fact.product_code,
                       SUM(fact.transaction_amount)::numeric(18,2) AS {amount}
                FROM {periods} scope
                JOIN {fact} fact
                  ON fact.transaction_date BETWEEN scope.period_start AND scope.period_end
                 AND fact.is_sale AND fact.product_code IS NOT NULL
                WHERE scope.grain = '{grain}'
                GROUP BY scope.period_start, scope.period_end, fact.product_code
            ''',
        )
        update(
            f"{prefix}_customer_sales",
            ("period_start", "period_end", "customer_id"),
            (amount,),
            f'''
                SELECT scope.period_start, scope.period_end, fact.customer_id,
                       SUM(fact.transaction_amount)::numeric(18,2) AS {amount}
                FROM {periods} scope
                JOIN {fact} fact
                  ON fact.transaction_date BETWEEN scope.period_start AND scope.period_end
                 AND fact.is_sale AND fact.customer_id IS NOT NULL
                WHERE scope.grain = '{grain}'
                GROUP BY scope.period_start, scope.period_end, fact.customer_id
            ''',
        )

    update(
        "daily_sales_metrics",
        ("transaction_date",),
        (
            "transaction_amount",
            "year_over_year_rate",
            "rolling_7_day_transaction_amount",
            "rolling_30_day_transaction_amount",
        ),
        f'''
            SELECT current.transaction_date, current.transaction_amount,
                   CASE WHEN previous.transaction_amount IS NULL
                                  OR previous.transaction_amount = 0 THEN 0.00
                        ELSE ROUND((current.transaction_amount - previous.transaction_amount)
                             / previous.transaction_amount * 100, 2)
                   END::numeric(12,2) AS year_over_year_rate,
                   (SELECT COALESCE(SUM(item.transaction_amount), 0)::numeric(18,2)
                    FROM {schema}.daily_sales item
                    WHERE item.transaction_date BETWEEN current.transaction_date - 6
                                                    AND current.transaction_date)
                       AS rolling_7_day_transaction_amount,
                   (SELECT COALESCE(SUM(item.transaction_amount), 0)::numeric(18,2)
                    FROM {schema}.daily_sales item
                    WHERE item.transaction_date BETWEEN current.transaction_date - 29
                                                    AND current.transaction_date)
                       AS rolling_30_day_transaction_amount
            FROM {schema}.daily_sales current
            LEFT JOIN {schema}.daily_sales previous
              ON previous.transaction_date = (current.transaction_date - INTERVAL '1 year')::date
        ''',
    )
    for prefix, rate, interval in (
        ("weekly", "week_over_week_rate", "7 days"),
        ("monthly", "month_over_month_rate", "1 month"),
    ):
        amount = f"{prefix}_transaction_amount"
        update(
            f"{prefix}_sales_metrics",
            ("period_start", "period_end"),
            (amount, rate),
            f'''
                SELECT current.period_start, current.period_end, current.{amount},
                       CASE WHEN previous.{amount} IS NULL OR previous.{amount} = 0 THEN 0.00
                            ELSE ROUND((current.{amount} - previous.{amount})
                                 / previous.{amount} * 100, 2)
                       END::numeric(12,2) AS {rate}
                FROM {schema}.{prefix}_sales current
                LEFT JOIN {schema}.{prefix}_sales previous
                  ON previous.period_start = (current.period_start - INTERVAL '{interval}')::date
            ''',
        )

    update(
        "customer_daily_sales",
        ("customer_id", "transaction_date"),
        ("transaction_amount",),
        f'''
            SELECT customer_id, transaction_date, transaction_amount
            FROM {schema}.daily_customer_sales
        ''',
    )
    update(
        "customer_daily_sales_metrics",
        ("customer_id", "transaction_date"),
        (
            "transaction_amount",
            "rolling_7_day_transaction_amount",
            "rolling_30_day_transaction_amount",
        ),
        f'''
            SELECT current.customer_id, current.transaction_date, current.transaction_amount,
                   (SELECT COALESCE(SUM(item.transaction_amount), 0)::numeric(18,2)
                    FROM {schema}.customer_daily_sales item
                    WHERE item.customer_id = current.customer_id
                      AND item.transaction_date BETWEEN current.transaction_date - 6
                                                    AND current.transaction_date)
                       AS rolling_7_day_transaction_amount,
                   (SELECT COALESCE(SUM(item.transaction_amount), 0)::numeric(18,2)
                    FROM {schema}.customer_daily_sales item
                    WHERE item.customer_id = current.customer_id
                      AND item.transaction_date BETWEEN current.transaction_date - 29
                                                    AND current.transaction_date)
                       AS rolling_30_day_transaction_amount
            FROM {schema}.customer_daily_sales current
        ''',
    )

    for prefix, grain in PERIODS:
        amount = f"{prefix}_transaction_amount"
        update(
            f"customer_{prefix}_sales",
            ("customer_id", "period_start", "period_end"),
            (amount,),
            f'''
                SELECT fact.customer_id, scope.period_start, scope.period_end,
                       SUM(fact.transaction_amount)::numeric(18,2) AS {amount}
                FROM {periods} scope
                JOIN {fact} fact
                  ON fact.transaction_date BETWEEN scope.period_start AND scope.period_end
                 AND fact.is_sale AND fact.customer_id IS NOT NULL
                WHERE scope.grain = '{grain}'
                GROUP BY fact.customer_id, scope.period_start, scope.period_end
            ''',
        )

    update(
        "customer_daily_product_sales",
        ("customer_id", "transaction_date", "product_code"),
        ("transaction_amount",),
        f'''
            SELECT customer_id, transaction_date, product_code,
                   SUM(transaction_amount)::numeric(18,2) AS transaction_amount
            FROM {fact}
            WHERE is_sale AND customer_id IS NOT NULL AND product_code IS NOT NULL
            GROUP BY customer_id, transaction_date, product_code
        ''',
    )
    for prefix, grain in (
        ("monthly", "month"),
        ("quarterly", "quarter"),
        ("half_year", "half"),
    ):
        amount = f"{prefix}_transaction_amount"
        update(
            f"customer_{prefix}_product_sales",
            ("customer_id", "period_start", "period_end", "product_code"),
            (amount,),
            f'''
                SELECT fact.customer_id, scope.period_start, scope.period_end,
                       fact.product_code,
                       SUM(fact.transaction_amount)::numeric(18,2) AS {amount}
                FROM {periods} scope
                JOIN {fact} fact
                  ON fact.transaction_date BETWEEN scope.period_start AND scope.period_end
                 AND fact.is_sale AND fact.customer_id IS NOT NULL
                 AND fact.product_code IS NOT NULL
                WHERE scope.grain = '{grain}'
                GROUP BY fact.customer_id, scope.period_start, scope.period_end,
                         fact.product_code
            ''',
        )

    assert_equal(f"{schema}金额表刷新数量", len(changes), len(STORE_AMOUNT_TABLES))
    return changes


def table_invariants(conn: psycopg.Connection, schema: str) -> dict[str, Any]:
    quantities = {
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
    purchase_counts = {
        "customer_weekly_sales": "weekly_purchase_count",
        "customer_monthly_sales": "monthly_purchase_count",
        "customer_quarterly_sales": "quarterly_purchase_count",
        "customer_half_year_sales": "half_year_purchase_count",
    }
    result: dict[str, Any] = {"rows": {}, "quantities": {}, "purchase_counts": {}}
    for table in (*STORE_AMOUNT_TABLES, "customer_health_detail"):
        result["rows"][table] = scalar(
            conn,
            f"SELECT COUNT(*)::bigint FROM {schema}.{table}",
        )
    for table, column in quantities.items():
        result["quantities"][table] = scalar(
            conn,
            f"SELECT COALESCE(SUM({column}), 0) FROM {schema}.{table}",
        )
    for table, column in purchase_counts.items():
        result["purchase_counts"][table] = scalar(
            conn,
            f"SELECT COALESCE(SUM({column}), 0) FROM {schema}.{table}",
        )
    result["health_max_updated_at"] = scalar(
        conn,
        f"SELECT MAX(updated_at) FROM {schema}.customer_health_detail",
    )
    return result


def validate_store_amounts(
    conn: psycopg.Connection,
    schema: str,
    expected: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for category, checks in STORE_AMOUNT_CHECKS.items():
        expected_value = expected[category]
        for table, column in checks.items():
            actual = scalar(
                conn,
                f"SELECT COALESCE(SUM({column}), 0) FROM {schema}.{table}",
            )
            assert_equal(f"{schema}.{table}.{column}", actual, expected_value)
            results.append({
                "table": f"{schema}.{table}",
                "column": column,
                "total": actual,
            })
    return results


def validate_aggregates(
    conn: psycopg.Connection,
    combined_sales: Any,
    combined_refunds: Any,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for prefix in ("daily", "weekly", "monthly", "quarterly", "half_year"):
        table = "daily_sales" if prefix == "daily" else f"{prefix}_sales"
        column = "transaction_amount" if prefix == "daily" else f"{prefix}_transaction_amount"
        total = scalar(conn, f"SELECT COALESCE(SUM({column}), 0) FROM fenxiao.{table}")
        assert_equal(f"fenxiao.{table}.{column}", total, combined_sales)
        results.append({"table": f"fenxiao.{table}", "column": column, "total": total})

        component = f"fenxiao_{column}"
        channel_component_total = scalar(
            conn,
            f"SELECT COALESCE(SUM({component}), 0) FROM qudao.{table}",
        )
        assert_equal(f"qudao.{table}.{component}", channel_component_total, total)
        arithmetic_errors = scalar(conn, f'''
            SELECT COUNT(*)::bigint
            FROM qudao.{table}
            WHERE {column} IS DISTINCT FROM (
                COALESCE(daren_{column}, 0)
                + COALESCE(siyu_{column}, 0)
                + COALESCE(fenxiao_{column}, 0)
            )
        ''')
        assert_equal(f"qudao.{table}渠道金额加总异常", arithmetic_errors, 0)

    for prefix in ("weekly", "monthly", "quarterly", "half_year"):
        table = f"{prefix}_refunds"
        column = f"{prefix}_refund_amount"
        total = scalar(conn, f"SELECT COALESCE(SUM({column}), 0) FROM fenxiao.{table}")
        assert_equal(f"fenxiao.{table}.{column}", total, combined_refunds)
        results.append({"table": f"fenxiao.{table}", "column": column, "total": total})

        component = f"fenxiao_{column}"
        channel_component_total = scalar(
            conn,
            f"SELECT COALESCE(SUM({component}), 0) FROM qudao.{table}",
        )
        assert_equal(f"qudao.{table}.{component}", channel_component_total, total)
        arithmetic_errors = scalar(conn, f'''
            SELECT COUNT(*)::bigint
            FROM qudao.{table}
            WHERE {column} IS DISTINCT FROM (
                COALESCE(daren_{column}, 0)
                + COALESCE(siyu_{column}, 0)
                + COALESCE(fenxiao_{column}, 0)
            )
        ''')
        assert_equal(f"qudao.{table}渠道退款加总异常", arithmetic_errors, 0)

    invalid_high_frequency = scalar(conn, '''
        SELECT COUNT(*)::bigint
        FROM fenxiao.half_year_high_frequency_products
        WHERE half_year_transaction_amount IS NULL
           OR amount_rank IS NULL
           OR selection_type IS NULL
    ''')
    assert_equal("fenxiao.half_year_high_frequency_products金额排名完整性", invalid_high_frequency, 0)
    return results


def acquire_locks(conn: psycopg.Connection) -> None:
    for schema in ("alibaba", "jushuitan"):
        log(f"等待{schema}上传事务锁")
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"upload:{schema}",),
        )
    for aggregate in ("fenxiao", "qudao"):
        log(f"等待{aggregate}汇总事务锁")
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            (f"upload:{aggregate}",),
        )


def run(execute: bool) -> dict[str, Any]:
    settings = get_settings()
    started = time.monotonic()
    report: dict[str, Any] = {
        "mode": "execute" if execute else "preflight",
        "store_tables": len(STORE_AMOUNT_TABLES) * 2,
        "aggregate_tables": 19,
        "total_distinct_tables": len(STORE_AMOUNT_TABLES) * 2 + 19,
    }
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        conn.execute("SET LOCAL statement_timeout = 0")
        conn.execute("SET LOCAL lock_timeout = '30s'")
        preflight_tables(conn)
        quality = {schema: raw_quality(conn, schema) for schema in ("alibaba", "jushuitan")}
        for schema, values in quality.items():
            for key in ("invalid_dates", "invalid_sales_amounts", "invalid_return_amounts"):
                assert_equal(f"{schema}.{key}", values[key], 0)
        report["raw_quality"] = quality
        log(f"原始数据质量预检通过：{json.dumps(json_value(quality), ensure_ascii=False)}")

        if execute:
            acquire_locks(conn)
        dates = {
            schema: platform_dates(conn, schema)
            for schema in ("alibaba", "jushuitan")
        }
        report["date_ranges"] = {
            schema: {
                "count": len(values),
                "start": values[0],
                "end": values[-1],
            }
            for schema, values in dates.items()
        }
        before = {
            schema: table_invariants(conn, schema)
            for schema in ("alibaba", "jushuitan")
        }

        totals: dict[str, dict[str, Any]] = {}
        store_changes: dict[str, list[dict[str, int | str]]] = {}
        for schema in ("alibaba", "jushuitan"):
            log(f"准备{schema}全日期临时事实层")
            prepare_platform_fact(conn, schema, dates[schema])
            totals[schema] = fact_totals(conn, schema)
            log(f"{schema}新口径基准：{json.dumps(json_value(totals[schema]), ensure_ascii=False)}")
            if execute:
                log(f"开始更新{schema}的32张金额表；数量和频次字段保持不变")
                store_changes[schema] = refresh_store_amounts(
                    conn,
                    schema,
                    apply_changes=True,
                )

        report["source_totals"] = totals
        if not execute:
            conn.rollback()
            report["elapsed_seconds"] = round(time.monotonic() - started, 2)
            return report

        store_validations = {
            schema: validate_store_amounts(conn, schema, totals[schema])
            for schema in ("alibaba", "jushuitan")
        }
        log("两平台32张金额表均已通过源数据金额守恒校验")

        after = {
            schema: table_invariants(conn, schema)
            for schema in ("alibaba", "jushuitan")
        }
        for schema in ("alibaba", "jushuitan"):
            assert_equal(f"{schema}行数保持不变", after[schema]["rows"], before[schema]["rows"])
            assert_equal(
                f"{schema}商品数量保持不变",
                after[schema]["quantities"],
                before[schema]["quantities"],
            )
            assert_equal(
                f"{schema}拿货频次保持不变",
                after[schema]["purchase_counts"],
                before[schema]["purchase_counts"],
            )
            assert_equal(
                f"{schema}健康度未更新",
                after[schema]["health_max_updated_at"],
                before[schema]["health_max_updated_at"],
            )
        log("两平台商品数量、拿货频次、健康度和表行数均保持不变")

        log("刷新fenxiao和qudao上级汇总表")
        alibaba_aggregate_changes = refresh_alibaba_aggregates(
            conn,
            include_health=False,
        )
        jushuitan_aggregate_changes = refresh_jushuitan_aggregates(
            conn,
            include_health=False,
        )
        assert_equal("阿里巴巴上级金额表刷新数", len(alibaba_aggregate_changes), 19)
        assert_equal("聚水潭上级金额表刷新数", len(jushuitan_aggregate_changes), 19)

        combined_sales = totals["alibaba"]["overall"] + totals["jushuitan"]["overall"]
        combined_refunds = totals["alibaba"]["refund"] + totals["jushuitan"]["refund"]
        aggregate_validations = validate_aggregates(conn, combined_sales, combined_refunds)
        log("fenxiao与qudao汇总金额、退款额和渠道分项均已对平")

        report["store_changes"] = store_changes
        report["store_validations"] = store_validations
        report["aggregate_validations"] = aggregate_validations
        report["combined_sales"] = combined_sales
        report["combined_refunds"] = combined_refunds
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        conn.commit()
        log("全部校验通过，数据库事务已提交")
        return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按销售金额/退货金额直接汇总规则回刷阿里巴巴与聚水潭金额表。"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="执行并提交回刷；不传时只做只读预检。",
    )
    parser.add_argument(
        "--confirm",
        choices=("REBUILD_DISTRIBUTION_AMOUNTS",),
        help="执行模式必须提供的确认短语。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.execute and args.confirm != "REBUILD_DISTRIBUTION_AMOUNTS":
        raise SystemExit("执行模式必须传入 --confirm REBUILD_DISTRIBUTION_AMOUNTS")
    report = run(args.execute)
    print(json.dumps(json_value(report), ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
