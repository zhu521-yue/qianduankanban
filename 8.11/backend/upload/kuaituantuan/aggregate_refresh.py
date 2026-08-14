from __future__ import annotations

from psycopg import Connection

from upload.doudian_kocotree.aggregate_refresh import (
    _channel_daily_select,
    _channel_period_select,
    _daily_sales_select,
    _high_frequency_select,
    _period_select,
)
from upload.table_sync import TableChange, sync_table


PRIVATE_STORES = ("qijian", "muyinqijian", "kuaituantuan")


def _prepare_aggregate_scopes(conn: Connection) -> None:
    conn.execute('''
        CREATE TEMP TABLE upload_kuaituantuan_aggregate_dates ON COMMIT DROP AS
        SELECT transaction_date FROM upload_kuaituantuan_dates
        UNION
        SELECT current.transaction_date
        FROM siyu.daily_sales current
        WHERE EXISTS (
            SELECT 1 FROM upload_kuaituantuan_dates changed
            WHERE current.transaction_date BETWEEN changed.transaction_date
                                               AND changed.transaction_date + 29
               OR current.transaction_date = (changed.transaction_date + INTERVAL '1 year')::date
        )
    ''')
    conn.execute(
        "CREATE UNIQUE INDEX ON upload_kuaituantuan_aggregate_dates (transaction_date)"
    )
    conn.execute('''
        CREATE TEMP TABLE upload_kuaituantuan_aggregate_periods ON COMMIT DROP AS
        SELECT grain, period_start, period_end
        FROM upload_kuaituantuan_periods
        UNION
        SELECT 'week'::text, sales.period_start, sales.period_end
        FROM siyu.weekly_sales sales
        WHERE EXISTS (
            SELECT 1 FROM upload_kuaituantuan_periods changed
            WHERE changed.grain = 'week'
              AND sales.period_start = changed.period_start + 7
        )
        UNION
        SELECT 'month'::text, sales.period_start, sales.period_end
        FROM siyu.monthly_sales sales
        WHERE EXISTS (
            SELECT 1 FROM upload_kuaituantuan_periods changed
            WHERE changed.grain = 'month'
              AND sales.period_start = (changed.period_start + INTERVAL '1 month')::date
        )
    ''')
    conn.execute(
        "CREATE UNIQUE INDEX ON upload_kuaituantuan_aggregate_periods "
        "(grain, period_start, period_end)"
    )


def _scope_daily(expected: str) -> str:
    return (
        f"SELECT expected.* FROM ({expected}) expected "
        "JOIN upload_kuaituantuan_aggregate_dates dates USING (transaction_date)"
    )


def _scope_period(expected: str, grain: str) -> str:
    return f'''SELECT expected.* FROM ({expected}) expected
        JOIN upload_kuaituantuan_aggregate_periods periods
          ON periods.grain = '{grain}'
         AND periods.period_start = expected.period_start
         AND periods.period_end = expected.period_end'''


def _period_delete_scope(grain: str) -> str:
    return f'''EXISTS (
        SELECT 1 FROM upload_kuaituantuan_aggregate_periods periods
        WHERE periods.grain = '{grain}'
          AND periods.period_start = target.period_start
          AND periods.period_end = target.period_end
    )'''


def _sync_scoped(
    conn: Connection,
    schema: str,
    table: str,
    keys: tuple[str, ...],
    values: tuple[str, ...],
    expected: str,
    scope: str,
) -> TableChange:
    return sync_table(
        conn,
        schema_name=schema,
        table_name=table,
        key_columns=keys,
        value_columns=values,
        expected_select=expected,
        delete_scope_sql=scope,
    )


def refresh_siyu(conn: Connection) -> list[TableChange]:
    changes = [_sync_scoped(
        conn,
        "siyu",
        "daily_sales",
        ("transaction_date",),
        (
            "transaction_amount", "year_over_year_rate",
            "rolling_7_day_transaction_amount", "rolling_30_day_transaction_amount",
        ),
        _scope_daily(_daily_sales_select(PRIVATE_STORES, "daily_sales", 2)),
        "target.transaction_date IN "
        "(SELECT transaction_date FROM upload_kuaituantuan_aggregate_dates)",
    )]

    for prefix, rate, interval, grain in (
        ("weekly", "week_over_week_rate", "7 days", "week"),
        ("monthly", "month_over_month_rate", "1 month", "month"),
        ("quarterly", None, None, "quarter"),
        ("half_year", None, None, "half"),
    ):
        amount = f"{prefix}_transaction_amount"
        changes.append(_sync_scoped(
            conn,
            "siyu",
            f"{prefix}_sales",
            ("period_start", "period_end"),
            (amount, *((rate,) if rate else ())),
            _scope_period(_period_select(
                PRIVATE_STORES,
                f"{prefix}_sales",
                amount,
                rate,
                interval,
                2,
            ), grain),
            _period_delete_scope(grain),
        ))

    for prefix, grain in (
        ("weekly", "week"),
        ("monthly", "month"),
        ("quarterly", "quarter"),
        ("half_year", "half"),
    ):
        amount = f"{prefix}_refund_amount"
        changes.append(_sync_scoped(
            conn,
            "siyu",
            f"{prefix}_refunds",
            ("period_start", "period_end"),
            (amount,),
            _scope_period(_period_select(
                PRIVATE_STORES,
                f"{prefix}_refunds",
                amount,
            ), grain),
            _period_delete_scope(grain),
        ))

    changes.append(sync_table(
        conn,
        schema_name="siyu",
        table_name="customer_health_detail",
        key_columns=(
            "health_grain", "source_platform", "customer_id",
            "period_start", "period_end",
        ),
        value_columns=(
            "week_purchase_count", "month_purchase_count",
            "half_year_purchase_count", "half_year_purchase_amount",
            "week_score", "month_score", "customer_score",
            "customer_health_status", "state_instructions", "follow_up_action",
        ),
        expected_select='''
            SELECT 'natural_week'::text AS health_grain,
                   'kuaituantuan'::text AS source_platform,
                   health.period_start, health.period_end, health.customer_id,
                   health.week_purchase_count::numeric(20,4),
                   health.month_purchase_count::numeric(20,4),
                   NULL::bigint AS half_year_purchase_count,
                   NULL::numeric(20,2) AS half_year_purchase_amount,
                   health.week_score::numeric(10,2),
                   health.month_score::numeric(10,2),
                   health.customer_score::numeric(10,2),
                   health.customer_health_status,
                   rules.state_instructions,
                   rules.follow_up_action
            FROM kuaituantuan.customer_health_detail health
            JOIN upload_kuaituantuan_health_weeks weeks
              ON weeks.period_start = health.period_start
             AND weeks.period_end = health.period_end
            LEFT JOIN public.private_customer_status_action rules
              ON rules.customer_health_status = health.customer_health_status
        ''',
        delete_scope_sql='''
            target.health_grain = 'natural_week'
            AND target.source_platform = 'kuaituantuan'
            AND EXISTS (
                SELECT 1 FROM upload_kuaituantuan_health_weeks weeks
                WHERE weeks.period_start = target.period_start
                  AND weeks.period_end = target.period_end
            )
        ''',
    ))
    changes.append(_sync_scoped(
        conn,
        "siyu",
        "half_year_high_frequency_products",
        ("period_start", "period_end", "product_code"),
        (
            "half_year_product_quantity", "half_year_transaction_amount",
            "quantity_rank", "amount_rank", "selection_type",
        ),
        _scope_period(_high_frequency_select(PRIVATE_STORES), "half"),
        _period_delete_scope("half"),
    ))
    if len(changes) != 11:
        raise ValueError(f"私域组刷新表数异常：{len(changes)} != 11")
    return changes


def refresh_qudao(conn: Connection) -> list[TableChange]:
    changes = [_sync_scoped(
        conn,
        "qudao",
        "daily_sales",
        ("transaction_date",),
        (
            "daren_transaction_amount", "siyu_transaction_amount",
            "fenxiao_transaction_amount", "transaction_amount",
            "included_group_count", "is_complete", "year_over_year_rate",
            "rolling_7_day_transaction_amount", "rolling_30_day_transaction_amount",
        ),
        _scope_daily(_channel_daily_select()),
        "target.transaction_date IN "
        "(SELECT transaction_date FROM upload_kuaituantuan_aggregate_dates)",
    )]
    for prefix, rate, interval, grain in (
        ("weekly", "week_over_week_rate", "7 days", "week"),
        ("monthly", "month_over_month_rate", "1 month", "month"),
        ("quarterly", None, None, "quarter"),
        ("half_year", None, None, "half"),
    ):
        amount = f"{prefix}_transaction_amount"
        changes.append(_sync_scoped(
            conn,
            "qudao",
            f"{prefix}_sales",
            ("period_start", "period_end"),
            (
                f"daren_{amount}", f"siyu_{amount}", f"fenxiao_{amount}",
                amount, "included_group_count", "is_complete",
                *((rate,) if rate else ()),
            ),
            _scope_period(
                _channel_period_select(prefix, "sales", rate, interval),
                grain,
            ),
            _period_delete_scope(grain),
        ))
    for prefix, grain in (
        ("weekly", "week"),
        ("monthly", "month"),
        ("quarterly", "quarter"),
        ("half_year", "half"),
    ):
        amount = f"{prefix}_refund_amount"
        changes.append(_sync_scoped(
            conn,
            "qudao",
            f"{prefix}_refunds",
            ("period_start", "period_end"),
            (
                f"daren_{amount}", f"siyu_{amount}", f"fenxiao_{amount}",
                amount, "included_group_count", "is_complete",
            ),
            _scope_period(_channel_period_select(prefix, "refunds"), grain),
            _period_delete_scope(grain),
        ))
    if len(changes) != 9:
        raise ValueError(f"渠道刷新表数异常：{len(changes)} != 9")
    return changes


def refresh_aggregates(conn: Connection) -> list[TableChange]:
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:siyu'))")
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:qudao'))")
    _prepare_aggregate_scopes(conn)
    changes = [*refresh_siyu(conn), *refresh_qudao(conn)]
    if len(changes) != 20:
        raise ValueError(f"快团团上层汇总刷新表数异常：{len(changes)} != 20")
    return changes
