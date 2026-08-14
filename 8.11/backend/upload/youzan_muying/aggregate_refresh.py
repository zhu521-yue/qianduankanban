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


YOUZAN_STORES = ("qijian", "muyinqijian")
PRIVATE_STORES = ("qijian", "muyinqijian", "kuaituantuan")


def _sync(
    conn: Connection,
    schema: str,
    table: str,
    keys: tuple[str, ...],
    values: tuple[str, ...],
    expected: str,
    delete_scope_sql: str | None = None,
) -> TableChange:
    return sync_table(
        conn,
        schema_name=schema,
        table_name=table,
        key_columns=keys,
        value_columns=values,
        expected_select=expected,
        delete_scope_sql=delete_scope_sql,
    )


def _youzan_daily_sales_select() -> str:
    return '''
        SELECT transaction_date,
               SUM(transaction_amount)::numeric(18,2) AS transaction_amount
        FROM (
            SELECT transaction_date, transaction_amount FROM qijian.daily_sales
            UNION ALL
            SELECT transaction_date, transaction_amount FROM muyinqijian.daily_sales
        ) source_rows
        GROUP BY transaction_date
    '''


def _prepare_youzan_health_counts(conn: Connection) -> None:
    conn.execute('''
        CREATE TEMP TABLE upload_youzan_customer_days ON COMMIT DROP AS
        SELECT customer_id, transaction_date FROM qijian.customer_daily_sales
        UNION
        SELECT customer_id, transaction_date FROM muyinqijian.customer_daily_sales
    ''')
    conn.execute('''
        CREATE UNIQUE INDEX ON upload_youzan_customer_days
        (customer_id, transaction_date)
    ''')
    conn.execute('''
        CREATE TEMP TABLE upload_youzan_month_mtd ON COMMIT DROP AS
        SELECT customer_id, transaction_date,
               COUNT(*) OVER (
                   PARTITION BY customer_id, DATE_TRUNC('month', transaction_date)
                   ORDER BY transaction_date
               )::numeric(10,2) AS month_to_date_count
        FROM upload_youzan_customer_days
    ''')
    conn.execute('''
        CREATE UNIQUE INDEX ON upload_youzan_month_mtd
        (customer_id, transaction_date)
    ''')
    conn.execute("ANALYZE upload_youzan_customer_days")
    conn.execute("ANALYZE upload_youzan_month_mtd")
    conn.execute('''
        CREATE TEMP TABLE upload_youzan_health_counts ON COMMIT DROP AS
        WITH global_bound AS (
            SELECT (MAX(transaction_date)
                    - (EXTRACT(ISODOW FROM MAX(transaction_date))::integer - 1))::date
                       AS latest_week
            FROM upload_youzan_customer_days
        ), customer_bounds AS (
            SELECT customer_id,
                   (MIN(transaction_date)
                    - (EXTRACT(ISODOW FROM MIN(transaction_date))::integer - 1))::date
                       AS first_week
            FROM upload_youzan_customer_days
            GROUP BY customer_id
        ), calendar AS (
            SELECT bounds.customer_id,
                   weeks.week_start::date AS period_start,
                   (weeks.week_start::date + 6) AS period_end
            FROM customer_bounds bounds
            CROSS JOIN global_bound global
            CROSS JOIN LATERAL generate_series(
                bounds.first_week,
                global.latest_week,
                INTERVAL '7 days'
            ) AS weeks(week_start)
        )
        SELECT calendar.*,
               DATE_TRUNC('month', calendar.period_start)::date AS month_period_start,
               (DATE_TRUNC('month', calendar.period_end)::date
                    + INTERVAL '1 month - 1 day')::date AS month_period_end,
               COALESCE((
                   SELECT COUNT(*)::integer
                   FROM upload_youzan_customer_days daily
                   WHERE daily.customer_id = calendar.customer_id
                     AND daily.transaction_date BETWEEN calendar.period_start
                                                    AND calendar.period_end
               ), 0)::integer AS week_purchase_count,
               CASE
                   WHEN DATE_TRUNC('month', calendar.period_start)::date
                        = DATE_TRUNC('month', calendar.period_end)::date
                       THEN COALESCE((
                           SELECT MAX(mtd.month_to_date_count)
                           FROM upload_youzan_month_mtd mtd
                           WHERE mtd.customer_id = calendar.customer_id
                             AND mtd.transaction_date BETWEEN
                                 DATE_TRUNC('month', calendar.period_start)::date
                                 AND calendar.period_end
                       ), 0)::numeric(10,2)
                   ELSE ROUND((COALESCE((
                           SELECT MAX(mtd.month_to_date_count)
                           FROM upload_youzan_month_mtd mtd
                           WHERE mtd.customer_id = calendar.customer_id
                             AND mtd.transaction_date BETWEEN
                                 DATE_TRUNC('month', calendar.period_start)::date
                                 AND (DATE_TRUNC('month', calendar.period_start)::date
                                      + INTERVAL '1 month - 1 day')::date
                       ), 0) + COALESCE((
                           SELECT MAX(mtd.month_to_date_count)
                           FROM upload_youzan_month_mtd mtd
                           WHERE mtd.customer_id = calendar.customer_id
                             AND mtd.transaction_date BETWEEN
                                 DATE_TRUNC('month', calendar.period_end)::date
                                 AND calendar.period_end
                       ), 0)) / 2.0, 2)::numeric(10,2)
               END AS month_purchase_count
        FROM calendar
    ''')
    conn.execute('''
        CREATE UNIQUE INDEX ON upload_youzan_health_counts
        (customer_id, period_start, period_end)
    ''')
    conn.execute("ANALYZE upload_youzan_health_counts")


def _youzan_health_select() -> str:
    return '''
        WITH sub_scores AS (
            SELECT counts.*,
                   CASE WHEN week_purchase_count >= 7 THEN 100
                        WHEN week_purchase_count >= 6 THEN 90
                        WHEN week_purchase_count >= 5 THEN 80
                        WHEN week_purchase_count >= 4 THEN 70
                        WHEN week_purchase_count >= 3 THEN 50
                        WHEN week_purchase_count >= 2 THEN 30
                        WHEN week_purchase_count >= 1 THEN 10
                        ELSE 0 END::numeric(5,2) AS week_score,
                   CASE WHEN month_purchase_count >= 30 THEN 100
                        WHEN month_purchase_count >= 20 THEN 80
                        WHEN month_purchase_count >= 15 THEN 60
                        WHEN month_purchase_count >= 10 THEN 40
                        WHEN month_purchase_count >= 5 THEN 20
                        ELSE 10 END::numeric(5,2) AS month_score
            FROM upload_youzan_health_counts counts
        ), scored AS (
            SELECT sub_scores.*,
                   ROUND(0.7 * week_score + 0.3 * month_score, 2)::numeric(5,2)
                       AS customer_score
            FROM sub_scores
        ), classified AS (
            SELECT scored.*,
                   CASE WHEN customer_score >= 90 THEN '高活跃'
                        WHEN customer_score >= 80 THEN '活跃'
                        WHEN customer_score >= 70 THEN '稳定'
                        WHEN customer_score >= 60 THEN '观察'
                        WHEN customer_score >= 50 THEN '风险'
                        WHEN customer_score >= 40 THEN '流失预警'
                        ELSE '流失' END AS customer_health_status
            FROM scored
        )
        SELECT classified.period_start, classified.period_end, classified.customer_id,
               classified.period_start AS week_period_start,
               classified.period_end AS week_period_end,
               classified.month_period_start, classified.month_period_end,
               classified.week_purchase_count, classified.week_score,
               classified.month_purchase_count, classified.month_score,
               classified.customer_score, classified.customer_health_status,
               rules.state_instructions, rules.follow_up_action
        FROM classified
        LEFT JOIN public.private_customer_status_action rules
          ON rules.customer_health_status = classified.customer_health_status
    '''


def _youzan_product_frequency_select() -> str:
    return '''
        WITH totals AS (
            SELECT period_start, period_end, product_code,
                   SUM(half_year_transaction_amount)::numeric(18,2)
                       AS half_year_transaction_amount,
                   SUM(half_year_product_quantity)::numeric(18,4)
                       AS half_year_product_quantity
            FROM (
                SELECT period_start, period_end, product_code,
                       half_year_transaction_amount, half_year_product_quantity
                FROM qijian.half_year_product_sales
                UNION ALL
                SELECT period_start, period_end, product_code,
                       half_year_transaction_amount, half_year_product_quantity
                FROM muyinqijian.half_year_product_sales
            ) source_rows
            GROUP BY period_start, period_end, product_code
        ), ranked AS (
            SELECT totals.*,
                   DENSE_RANK() OVER (
                       PARTITION BY period_start, period_end
                       ORDER BY half_year_product_quantity DESC
                   )::integer AS quantity_rank,
                   ROUND(((1 - PERCENT_RANK() OVER (
                       PARTITION BY period_start, period_end
                       ORDER BY half_year_product_quantity DESC
                   )) * 100)::numeric, 2)::numeric(6,2) AS frequency_percentile
            FROM totals
        )
        SELECT period_start, period_end, product_code,
               half_year_transaction_amount, half_year_product_quantity,
               quantity_rank, frequency_percentile
        FROM ranked
    '''


def refresh_youzan(conn: Connection) -> list[TableChange]:
    _prepare_youzan_health_counts(conn)
    changes = [_sync(
        conn, "youzan", "daily_sales", ("transaction_date",),
        ("transaction_amount",), _youzan_daily_sales_select(),
    )]
    for prefix in ("weekly", "monthly", "quarterly", "half_year"):
        amount = f"{prefix}_transaction_amount"
        changes.append(_sync(
            conn, "youzan", f"{prefix}_sales", ("period_start", "period_end"),
            (amount,), _period_select(YOUZAN_STORES, f"{prefix}_sales", amount),
        ))
    for prefix in ("weekly", "monthly", "quarterly", "half_year"):
        amount = f"{prefix}_refund_amount"
        changes.append(_sync(
            conn, "youzan", f"{prefix}_refunds", ("period_start", "period_end"),
            (amount,), _period_select(YOUZAN_STORES, f"{prefix}_refunds", amount),
        ))
    changes.append(_sync(
        conn, "youzan", "customer_health_detail",
        ("period_start", "period_end", "customer_id"),
        (
            "week_period_start", "week_period_end", "month_period_start", "month_period_end",
            "week_purchase_count", "week_score", "month_purchase_count", "month_score",
            "customer_score", "customer_health_status", "state_instructions", "follow_up_action",
        ),
        _youzan_health_select(),
    ))
    changes.append(_sync(
        conn, "youzan", "half_year_product_frequency",
        ("period_start", "period_end", "product_code"),
        (
            "half_year_transaction_amount", "half_year_product_quantity",
            "quantity_rank", "frequency_percentile",
        ),
        _youzan_product_frequency_select(),
    ))
    if len(changes) != 11:
        raise ValueError(f"有赞平台刷新表数异常：{len(changes)} != 11")
    return changes


def refresh_siyu(conn: Connection) -> list[TableChange]:
    changes = [_sync(
        conn, "siyu", "daily_sales", ("transaction_date",),
        (
            "transaction_amount", "year_over_year_rate",
            "rolling_7_day_transaction_amount", "rolling_30_day_transaction_amount",
        ),
        _daily_sales_select(PRIVATE_STORES, "daily_sales", 6),
    )]
    for prefix, rate, interval in (
        ("weekly", "week_over_week_rate", "7 days"),
        ("monthly", "month_over_month_rate", "1 month"),
        ("quarterly", None, None),
        ("half_year", None, None),
    ):
        amount = f"{prefix}_transaction_amount"
        changes.append(_sync(
            conn, "siyu", f"{prefix}_sales", ("period_start", "period_end"),
            (amount, *((rate,) if rate else ())),
            _period_select(
                PRIVATE_STORES, f"{prefix}_sales", amount, rate, interval, 6,
            ),
        ))
    for prefix in ("weekly", "monthly", "quarterly", "half_year"):
        amount = f"{prefix}_refund_amount"
        changes.append(_sync(
            conn, "siyu", f"{prefix}_refunds", ("period_start", "period_end"),
            (amount,), _period_select(PRIVATE_STORES, f"{prefix}_refunds", amount),
        ))
    changes.append(_sync(
        conn, "siyu", "customer_health_detail",
        ("health_grain", "source_platform", "customer_id", "period_start", "period_end"),
        (
            "week_purchase_count", "month_purchase_count",
            "half_year_purchase_count", "half_year_purchase_amount",
            "week_score", "month_score", "customer_score",
            "customer_health_status", "state_instructions", "follow_up_action",
        ),
        '''
            SELECT 'natural_week'::text AS health_grain,
                   'youzan'::text AS source_platform,
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
            FROM youzan.customer_health_detail health
            LEFT JOIN public.private_customer_status_action rules
              ON rules.customer_health_status = health.customer_health_status
        ''',
        "target.health_grain = 'natural_week' AND target.source_platform = 'youzan'",
    ))
    changes.append(_sync(
        conn, "siyu", "half_year_high_frequency_products",
        ("period_start", "period_end", "product_code"),
        (
            "half_year_product_quantity", "half_year_transaction_amount",
            "quantity_rank", "amount_rank", "selection_type",
        ),
        _high_frequency_select(PRIVATE_STORES),
    ))
    if len(changes) != 11:
        raise ValueError(f"私域组刷新表数异常：{len(changes)} != 11")
    return changes


def refresh_qudao(conn: Connection) -> list[TableChange]:
    changes = [_sync(
        conn, "qudao", "daily_sales", ("transaction_date",),
        (
            "daren_transaction_amount", "siyu_transaction_amount",
            "fenxiao_transaction_amount", "transaction_amount",
            "included_group_count", "is_complete", "year_over_year_rate",
            "rolling_7_day_transaction_amount", "rolling_30_day_transaction_amount",
        ),
        _channel_daily_select(),
    )]
    for prefix, rate, interval in (
        ("weekly", "week_over_week_rate", "7 days"),
        ("monthly", "month_over_month_rate", "1 month"),
        ("quarterly", None, None),
        ("half_year", None, None),
    ):
        amount = f"{prefix}_transaction_amount"
        changes.append(_sync(
            conn, "qudao", f"{prefix}_sales", ("period_start", "period_end"),
            (
                f"daren_{amount}", f"siyu_{amount}", f"fenxiao_{amount}",
                amount, "included_group_count", "is_complete",
                *((rate,) if rate else ()),
            ),
            _channel_period_select(prefix, "sales", rate, interval),
        ))
    for prefix in ("weekly", "monthly", "quarterly", "half_year"):
        amount = f"{prefix}_refund_amount"
        changes.append(_sync(
            conn, "qudao", f"{prefix}_refunds", ("period_start", "period_end"),
            (
                f"daren_{amount}", f"siyu_{amount}", f"fenxiao_{amount}",
                amount, "included_group_count", "is_complete",
            ),
            _channel_period_select(prefix, "refunds"),
        ))
    if len(changes) != 9:
        raise ValueError(f"渠道刷新表数异常：{len(changes)} != 9")
    return changes


def refresh_aggregates(conn: Connection) -> list[TableChange]:
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:youzan'))")
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:siyu'))")
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:qudao'))")
    changes = [*refresh_youzan(conn), *refresh_siyu(conn), *refresh_qudao(conn)]
    if len(changes) != 31:
        raise ValueError(f"母婴店上层汇总刷新表数异常：{len(changes)} != 31")
    return changes


def _scope_daily(expected: str, scope_table: str) -> str:
    return f'''SELECT expected.* FROM ({expected}) expected
        JOIN {scope_table} dates USING (transaction_date)'''


def _scope_period(expected: str, grain: str, scope_table: str) -> str:
    return f'''SELECT expected.* FROM ({expected}) expected
        JOIN {scope_table} periods
          ON periods.grain = '{grain}'
         AND periods.period_start = expected.period_start
         AND periods.period_end = expected.period_end'''


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


def _prepare_incremental_aggregate_scopes(conn: Connection) -> None:
    conn.execute('''
        CREATE TEMP TABLE upload_youzan_aggregate_daily_dates ON COMMIT DROP AS
        SELECT DISTINCT current.transaction_date
        FROM siyu.daily_sales current
        WHERE EXISTS (
            SELECT 1 FROM upload_youzan_dates changed
            WHERE current.transaction_date BETWEEN changed.transaction_date
                                               AND changed.transaction_date + 29
               OR current.transaction_date = (changed.transaction_date + INTERVAL '1 year')::date
        )
        UNION
        SELECT transaction_date FROM upload_youzan_dates
    ''')
    conn.execute(
        "CREATE UNIQUE INDEX ON upload_youzan_aggregate_daily_dates (transaction_date)"
    )
    conn.execute('''
        CREATE TEMP TABLE upload_youzan_aggregate_periods ON COMMIT DROP AS
        SELECT grain, period_start, period_end
        FROM upload_youzan_periods
        UNION
        SELECT 'week'::text, period_start + 7, period_end + 7
        FROM upload_youzan_periods
        WHERE grain = 'week'
        UNION
        SELECT 'month'::text,
               (period_start + INTERVAL '1 month')::date,
               (period_end + INTERVAL '1 month')::date
        FROM upload_youzan_periods
        WHERE grain = 'month'
    ''')
    conn.execute(
        "CREATE UNIQUE INDEX ON upload_youzan_aggregate_periods "
        "(grain, period_start, period_end)"
    )


def _prepare_incremental_youzan_health(conn: Connection) -> None:
    conn.execute('''
        CREATE TEMP TABLE upload_youzan_customer_days ON COMMIT DROP AS
        SELECT customer_id, transaction_date FROM qijian.customer_daily_sales
        UNION
        SELECT customer_id, transaction_date FROM muyinqijian.customer_daily_sales
    ''')
    conn.execute('''
        CREATE UNIQUE INDEX ON upload_youzan_customer_days
        (customer_id, transaction_date)
    ''')
    conn.execute('''
        CREATE TEMP TABLE upload_youzan_month_mtd ON COMMIT DROP AS
        SELECT customer_id, transaction_date,
               COUNT(*) OVER (
                   PARTITION BY customer_id, DATE_TRUNC('month', transaction_date)
                   ORDER BY transaction_date
               )::numeric(10,2) AS month_to_date_count
        FROM upload_youzan_customer_days
    ''')
    conn.execute('''
        CREATE UNIQUE INDEX ON upload_youzan_month_mtd
        (customer_id, transaction_date)
    ''')
    conn.execute('''
        CREATE TEMP TABLE upload_youzan_aggregate_health_weeks ON COMMIT DROP AS
        SELECT DISTINCT health.period_start, health.period_end
        FROM youzan.customer_health_detail health
        WHERE EXISTS (
            SELECT 1 FROM upload_youzan_periods months
            WHERE months.grain = 'month'
              AND health.period_start <= months.period_end
              AND health.period_end >= months.period_start
        )
        UNION
        SELECT period_start, period_end
        FROM upload_youzan_periods
        WHERE grain = 'week'
        UNION
        SELECT weeks.week_start::date, (weeks.week_start::date + 6)
        FROM (
            SELECT MAX(period_start) AS previous_latest_week
            FROM youzan.customer_health_detail
        ) previous
        CROSS JOIN (
            SELECT (MAX(transaction_date)
                    - (EXTRACT(ISODOW FROM MAX(transaction_date))::integer - 1))::date
                       AS latest_week
            FROM upload_youzan_customer_days
        ) current
        CROSS JOIN LATERAL generate_series(
            COALESCE(previous.previous_latest_week + 7, current.latest_week),
            current.latest_week,
            INTERVAL '7 days'
        ) weeks(week_start)
        WHERE current.latest_week IS NOT NULL
          AND (previous.previous_latest_week IS NULL
               OR current.latest_week > previous.previous_latest_week)
    ''')
    conn.execute('''
        CREATE UNIQUE INDEX ON upload_youzan_aggregate_health_weeks
        (period_start, period_end)
    ''')
    conn.execute('''
        CREATE TEMP TABLE upload_youzan_aggregate_health_keys ON COMMIT DROP AS
        WITH customer_bounds AS (
            SELECT customer_id,
                   (MIN(transaction_date)
                    - (EXTRACT(ISODOW FROM MIN(transaction_date))::integer - 1))::date
                       AS first_week
            FROM upload_youzan_customer_days
            GROUP BY customer_id
        ), global_bound AS (
            SELECT (MAX(transaction_date)
                    - (EXTRACT(ISODOW FROM MAX(transaction_date))::integer - 1))::date
                       AS latest_week
            FROM upload_youzan_customer_days
        )
        SELECT bounds.customer_id, weeks.period_start, weeks.period_end
        FROM customer_bounds bounds
        CROSS JOIN upload_youzan_aggregate_health_weeks weeks
        WHERE weeks.period_start >= bounds.first_week
        UNION
        SELECT bounds.customer_id,
               weeks.week_start::date AS period_start,
               (weeks.week_start::date + 6) AS period_end
        FROM customer_bounds bounds
        JOIN upload_youzan_customers changed USING (customer_id)
        CROSS JOIN global_bound global
        CROSS JOIN LATERAL generate_series(
            bounds.first_week,
            global.latest_week,
            INTERVAL '7 days'
        ) weeks(week_start)
    ''')
    conn.execute('''
        CREATE UNIQUE INDEX ON upload_youzan_aggregate_health_keys
        (customer_id, period_start, period_end)
    ''')
    conn.execute('''
        CREATE TEMP TABLE upload_youzan_health_counts ON COMMIT DROP AS
        SELECT keys.customer_id, keys.period_start, keys.period_end,
               DATE_TRUNC('month', keys.period_start)::date AS month_period_start,
               (DATE_TRUNC('month', keys.period_end)::date
                    + INTERVAL '1 month - 1 day')::date AS month_period_end,
               COALESCE((
                   SELECT COUNT(*)::integer
                   FROM upload_youzan_customer_days daily
                   WHERE daily.customer_id = keys.customer_id
                     AND daily.transaction_date BETWEEN keys.period_start AND keys.period_end
               ), 0)::integer AS week_purchase_count,
               CASE
                   WHEN DATE_TRUNC('month', keys.period_start)::date
                        = DATE_TRUNC('month', keys.period_end)::date
                       THEN COALESCE((
                           SELECT MAX(mtd.month_to_date_count)
                           FROM upload_youzan_month_mtd mtd
                           WHERE mtd.customer_id = keys.customer_id
                             AND mtd.transaction_date BETWEEN
                                 DATE_TRUNC('month', keys.period_start)::date
                                 AND keys.period_end
                       ), 0)::numeric(10,2)
                   ELSE ROUND((COALESCE((
                           SELECT MAX(mtd.month_to_date_count)
                           FROM upload_youzan_month_mtd mtd
                           WHERE mtd.customer_id = keys.customer_id
                             AND mtd.transaction_date BETWEEN
                                 DATE_TRUNC('month', keys.period_start)::date
                                 AND (DATE_TRUNC('month', keys.period_start)::date
                                      + INTERVAL '1 month - 1 day')::date
                       ), 0) + COALESCE((
                           SELECT MAX(mtd.month_to_date_count)
                           FROM upload_youzan_month_mtd mtd
                           WHERE mtd.customer_id = keys.customer_id
                             AND mtd.transaction_date BETWEEN
                                 DATE_TRUNC('month', keys.period_end)::date
                                 AND keys.period_end
                       ), 0)) / 2.0, 2)::numeric(10,2)
               END AS month_purchase_count
        FROM upload_youzan_aggregate_health_keys keys
    ''')
    conn.execute('''
        CREATE UNIQUE INDEX ON upload_youzan_health_counts
        (customer_id, period_start, period_end)
    ''')
    conn.execute("ANALYZE upload_youzan_customer_days")
    conn.execute("ANALYZE upload_youzan_month_mtd")
    conn.execute("ANALYZE upload_youzan_health_counts")


def refresh_aggregates_incremental(conn: Connection) -> list[TableChange]:
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:youzan'))")
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:siyu'))")
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:qudao'))")
    _prepare_incremental_aggregate_scopes(conn)
    _prepare_incremental_youzan_health(conn)
    changes: list[TableChange] = []
    daily_scope = "target.transaction_date IN (SELECT transaction_date FROM upload_youzan_dates)"
    aggregate_daily_scope = (
        "target.transaction_date IN "
        "(SELECT transaction_date FROM upload_youzan_aggregate_daily_dates)"
    )

    changes.append(_sync_scoped(
        conn, "youzan", "daily_sales", ("transaction_date",),
        ("transaction_amount",),
        _scope_daily(_youzan_daily_sales_select(), "upload_youzan_dates"),
        daily_scope,
    ))
    for prefix, grain in (
        ("weekly", "week"), ("monthly", "month"),
        ("quarterly", "quarter"), ("half_year", "half"),
    ):
        amount = f"{prefix}_transaction_amount"
        changes.append(_sync_scoped(
            conn, "youzan", f"{prefix}_sales", ("period_start", "period_end"),
            (amount,),
            _scope_period(
                _period_select(YOUZAN_STORES, f"{prefix}_sales", amount),
                grain,
                "upload_youzan_periods",
            ),
            f"EXISTS (SELECT 1 FROM upload_youzan_periods p WHERE p.grain='{grain}' AND p.period_start=target.period_start AND p.period_end=target.period_end)",
        ))
    for prefix, grain in (
        ("weekly", "week"), ("monthly", "month"),
        ("quarterly", "quarter"), ("half_year", "half"),
    ):
        amount = f"{prefix}_refund_amount"
        changes.append(_sync_scoped(
            conn, "youzan", f"{prefix}_refunds", ("period_start", "period_end"),
            (amount,),
            _scope_period(
                _period_select(YOUZAN_STORES, f"{prefix}_refunds", amount),
                grain,
                "upload_youzan_periods",
            ),
            f"EXISTS (SELECT 1 FROM upload_youzan_periods p WHERE p.grain='{grain}' AND p.period_start=target.period_start AND p.period_end=target.period_end)",
        ))
    changes.append(_sync_scoped(
        conn, "youzan", "customer_health_detail",
        ("period_start", "period_end", "customer_id"),
        (
            "week_period_start", "week_period_end", "month_period_start", "month_period_end",
            "week_purchase_count", "week_score", "month_purchase_count", "month_score",
            "customer_score", "customer_health_status", "state_instructions", "follow_up_action",
        ),
        _youzan_health_select(),
        '''EXISTS (
            SELECT 1 FROM upload_youzan_aggregate_health_keys keys
            WHERE keys.customer_id = target.customer_id
              AND keys.period_start = target.period_start
              AND keys.period_end = target.period_end
        )''',
    ))
    changes.append(_sync_scoped(
        conn, "youzan", "half_year_product_frequency",
        ("period_start", "period_end", "product_code"),
        (
            "half_year_transaction_amount", "half_year_product_quantity",
            "quantity_rank", "frequency_percentile",
        ),
        _scope_period(
            _youzan_product_frequency_select(), "half", "upload_youzan_periods"
        ),
        "EXISTS (SELECT 1 FROM upload_youzan_periods p WHERE p.grain='half' AND p.period_start=target.period_start AND p.period_end=target.period_end)",
    ))

    changes.append(_sync_scoped(
        conn, "siyu", "daily_sales", ("transaction_date",),
        (
            "transaction_amount", "year_over_year_rate",
            "rolling_7_day_transaction_amount", "rolling_30_day_transaction_amount",
        ),
        _scope_daily(
            _daily_sales_select(PRIVATE_STORES, "daily_sales", 6),
            "upload_youzan_aggregate_daily_dates",
        ),
        aggregate_daily_scope,
    ))
    for prefix, rate, interval, grain in (
        ("weekly", "week_over_week_rate", "7 days", "week"),
        ("monthly", "month_over_month_rate", "1 month", "month"),
        ("quarterly", None, None, "quarter"),
        ("half_year", None, None, "half"),
    ):
        amount = f"{prefix}_transaction_amount"
        values = (amount, *((rate,) if rate else ()))
        changes.append(_sync_scoped(
            conn, "siyu", f"{prefix}_sales", ("period_start", "period_end"),
            values,
            _scope_period(
                _period_select(PRIVATE_STORES, f"{prefix}_sales", amount, rate, interval, 6),
                grain,
                "upload_youzan_aggregate_periods",
            ),
            f"EXISTS (SELECT 1 FROM upload_youzan_aggregate_periods p WHERE p.grain='{grain}' AND p.period_start=target.period_start AND p.period_end=target.period_end)",
        ))
    for prefix, grain in (
        ("weekly", "week"), ("monthly", "month"),
        ("quarterly", "quarter"), ("half_year", "half"),
    ):
        amount = f"{prefix}_refund_amount"
        changes.append(_sync_scoped(
            conn, "siyu", f"{prefix}_refunds", ("period_start", "period_end"),
            (amount,),
            _scope_period(
                _period_select(PRIVATE_STORES, f"{prefix}_refunds", amount),
                grain,
                "upload_youzan_periods",
            ),
            f"EXISTS (SELECT 1 FROM upload_youzan_periods p WHERE p.grain='{grain}' AND p.period_start=target.period_start AND p.period_end=target.period_end)",
        ))
    changes.append(_sync_scoped(
        conn, "siyu", "customer_health_detail",
        ("health_grain", "source_platform", "customer_id", "period_start", "period_end"),
        (
            "week_purchase_count", "month_purchase_count",
            "half_year_purchase_count", "half_year_purchase_amount",
            "week_score", "month_score", "customer_score",
            "customer_health_status", "state_instructions", "follow_up_action",
        ),
        '''
            SELECT 'natural_week'::text AS health_grain,
                   'youzan'::text AS source_platform,
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
            FROM youzan.customer_health_detail health
            JOIN upload_youzan_aggregate_health_keys keys
              USING (customer_id, period_start, period_end)
            LEFT JOIN public.private_customer_status_action rules
              ON rules.customer_health_status = health.customer_health_status
        ''',
        '''target.health_grain = 'natural_week'
           AND target.source_platform = 'youzan'
           AND EXISTS (
               SELECT 1 FROM upload_youzan_aggregate_health_keys keys
               WHERE keys.customer_id = target.customer_id
                 AND keys.period_start = target.period_start
                 AND keys.period_end = target.period_end
           )''',
    ))
    changes.append(_sync_scoped(
        conn, "siyu", "half_year_high_frequency_products",
        ("period_start", "period_end", "product_code"),
        (
            "half_year_product_quantity", "half_year_transaction_amount",
            "quantity_rank", "amount_rank", "selection_type",
        ),
        _scope_period(
            _high_frequency_select(PRIVATE_STORES), "half", "upload_youzan_periods"
        ),
        "EXISTS (SELECT 1 FROM upload_youzan_periods p WHERE p.grain='half' AND p.period_start=target.period_start AND p.period_end=target.period_end)",
    ))

    changes.append(_sync_scoped(
        conn, "qudao", "daily_sales", ("transaction_date",),
        (
            "daren_transaction_amount", "siyu_transaction_amount",
            "fenxiao_transaction_amount", "transaction_amount",
            "included_group_count", "is_complete", "year_over_year_rate",
            "rolling_7_day_transaction_amount", "rolling_30_day_transaction_amount",
        ),
        _scope_daily(_channel_daily_select(), "upload_youzan_aggregate_daily_dates"),
        aggregate_daily_scope,
    ))
    for prefix, rate, interval, grain in (
        ("weekly", "week_over_week_rate", "7 days", "week"),
        ("monthly", "month_over_month_rate", "1 month", "month"),
        ("quarterly", None, None, "quarter"),
        ("half_year", None, None, "half"),
    ):
        amount = f"{prefix}_transaction_amount"
        values = (
            f"daren_{amount}", f"siyu_{amount}", f"fenxiao_{amount}",
            amount, "included_group_count", "is_complete",
            *((rate,) if rate else ()),
        )
        changes.append(_sync_scoped(
            conn, "qudao", f"{prefix}_sales", ("period_start", "period_end"),
            values,
            _scope_period(
                _channel_period_select(prefix, "sales", rate, interval),
                grain,
                "upload_youzan_aggregate_periods",
            ),
            f"EXISTS (SELECT 1 FROM upload_youzan_aggregate_periods p WHERE p.grain='{grain}' AND p.period_start=target.period_start AND p.period_end=target.period_end)",
        ))
    for prefix, grain in (
        ("weekly", "week"), ("monthly", "month"),
        ("quarterly", "quarter"), ("half_year", "half"),
    ):
        amount = f"{prefix}_refund_amount"
        changes.append(_sync_scoped(
            conn, "qudao", f"{prefix}_refunds", ("period_start", "period_end"),
            (
                f"daren_{amount}", f"siyu_{amount}", f"fenxiao_{amount}",
                amount, "included_group_count", "is_complete",
            ),
            _scope_period(
                _channel_period_select(prefix, "refunds"),
                grain,
                "upload_youzan_periods",
            ),
            f"EXISTS (SELECT 1 FROM upload_youzan_periods p WHERE p.grain='{grain}' AND p.period_start=target.period_start AND p.period_end=target.period_end)",
        ))
    if len(changes) != 31:
        raise ValueError(f"有赞上层增量刷新表数异常：{len(changes)} != 31")
    return changes
