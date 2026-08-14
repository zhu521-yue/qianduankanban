from __future__ import annotations

from collections.abc import Iterable

from psycopg import Connection

from upload.table_sync import TableChange, sync_table


DOUDIAN_STORES = ("doudianChildren", "doudianKocotree")
CHANNEL_GROUPS = ("daren", "siyu", "fenxiao")


def _union_rows(schemas: Iterable[str], table: str, columns: Iterable[str]) -> str:
    selected = ", ".join(columns)
    return "\nUNION ALL\n".join(
        f'SELECT {selected} FROM "{schema}"."{table}"' for schema in schemas
    )


def _sync(
    conn: Connection,
    schema: str,
    table: str,
    keys: tuple[str, ...],
    values: tuple[str, ...],
    expected: str,
) -> TableChange:
    return sync_table(
        conn,
        schema_name=schema,
        table_name=table,
        key_columns=keys,
        value_columns=values,
        expected_select=expected,
    )


def _daily_sales_select(schemas: tuple[str, ...], table: str, scale: int) -> str:
    union = _union_rows(schemas, table, ("transaction_date", "transaction_amount"))
    return f'''
        WITH daily AS (
            SELECT transaction_date,
                   SUM(transaction_amount)::numeric(20,2) AS transaction_amount
            FROM ({union}) rows
            GROUP BY transaction_date
        )
        SELECT current.transaction_date, current.transaction_amount,
               CASE WHEN previous.transaction_amount IS NULL OR previous.transaction_amount = 0 THEN 0
                    ELSE ROUND((current.transaction_amount - previous.transaction_amount)
                         / previous.transaction_amount * 100, {scale})
               END::numeric(20,{scale}) AS year_over_year_rate,
               (SELECT COALESCE(SUM(item.transaction_amount), 0)::numeric(20,2)
                FROM daily item
                WHERE item.transaction_date BETWEEN current.transaction_date - 6
                                                AND current.transaction_date)
                    AS rolling_7_day_transaction_amount,
               (SELECT COALESCE(SUM(item.transaction_amount), 0)::numeric(20,2)
                FROM daily item
                WHERE item.transaction_date BETWEEN current.transaction_date - 29
                                                AND current.transaction_date)
                    AS rolling_30_day_transaction_amount
        FROM daily current
        LEFT JOIN daily previous
          ON previous.transaction_date = (current.transaction_date - INTERVAL '1 year')::date
    '''


def _period_select(
    schemas: tuple[str, ...],
    table: str,
    amount: str,
    rate: str | None = None,
    interval: str | None = None,
    scale: int = 2,
) -> str:
    union = _union_rows(schemas, table, ("period_start", "period_end", amount))
    base = f'''
        WITH periods AS (
            SELECT period_start, period_end,
                   SUM({amount})::numeric(20,2) AS {amount}
            FROM ({union}) rows
            GROUP BY period_start, period_end
        )
    '''
    if rate:
        return base + f'''
            SELECT current.period_start, current.period_end, current.{amount},
                   CASE WHEN previous.{amount} IS NULL OR previous.{amount} = 0 THEN 0
                        ELSE ROUND((current.{amount} - previous.{amount})
                             / previous.{amount} * 100, {scale})
                   END::numeric(20,{scale}) AS {rate}
            FROM periods current
            LEFT JOIN periods previous
              ON previous.period_start = (current.period_start - INTERVAL '{interval}')::date
        '''
    return base + f"SELECT period_start, period_end, {amount} FROM periods"


def _high_frequency_select(schemas: tuple[str, ...]) -> str:
    union = _union_rows(
        schemas,
        "half_year_product_sales",
        (
            "period_start", "period_end", "product_code",
            "half_year_product_quantity", "half_year_transaction_amount",
        ),
    )
    return f'''
        WITH totals AS (
            SELECT period_start, period_end, product_code,
                   SUM(half_year_product_quantity) AS half_year_product_quantity,
                   SUM(half_year_transaction_amount)::numeric(20,2)
                       AS half_year_transaction_amount
            FROM ({union}) rows
            GROUP BY period_start, period_end, product_code
        ), ranked AS (
            SELECT totals.*,
                   ROW_NUMBER() OVER (
                     PARTITION BY period_start, period_end
                     ORDER BY half_year_product_quantity DESC, product_code ASC
                   )::bigint AS quantity_rank,
                   ROW_NUMBER() OVER (
                     PARTITION BY period_start, period_end
                     ORDER BY half_year_transaction_amount DESC, product_code ASC
                   )::bigint AS amount_rank
            FROM totals
        )
        SELECT period_start, period_end, product_code,
               half_year_product_quantity, half_year_transaction_amount,
               quantity_rank, amount_rank,
               CASE WHEN quantity_rank <= 5 AND amount_rank <= 5 THEN 'both'
                    WHEN quantity_rank <= 5 THEN 'quantity_top5'
                    ELSE 'amount_top5' END AS selection_type
        FROM ranked
        WHERE quantity_rank <= 5 OR amount_rank <= 5
    '''


def refresh_doudian(conn: Connection) -> list[TableChange]:
    changes = [_sync(
        conn, "doudian", "daily_sales_summary", ("transaction_date",),
        (
            "transaction_amount", "year_over_year_rate",
            "rolling_7_day_transaction_amount", "rolling_30_day_transaction_amount",
        ),
        _daily_sales_select(DOUDIAN_STORES, "daily_sales", 2),
    )]
    for target, source, amount, rate, interval in (
        ("weekly_sales_summary", "weekly_sales", "weekly_transaction_amount", "week_over_week_rate", "7 days"),
        ("monthly_sales_summary", "monthly_sales", "monthly_transaction_amount", "month_over_month_rate", "1 month"),
        ("quarterly_sales_summary", "quarterly_sales", "quarterly_transaction_amount", None, None),
        ("half_year_sales_summary", "half_year_sales", "half_year_transaction_amount", None, None),
    ):
        changes.append(_sync(
            conn, "doudian", target, ("period_start", "period_end"),
            (amount, rate) if rate else (amount,),
            _period_select(DOUDIAN_STORES, source, amount, rate, interval, 2),
        ))
    for prefix in ("weekly", "monthly", "quarterly", "half_year"):
        amount = f"{prefix}_refund_amount"
        changes.append(_sync(
            conn, "doudian", f"{prefix}_refunds_summary",
            ("period_start", "period_end"), (amount,),
            _period_select(DOUDIAN_STORES, f"{prefix}_refunds", amount),
        ))

    amounts = _union_rows(
        DOUDIAN_STORES, "customer_half_year_sales",
        (
            "period_start", "period_end", "customer_id",
            "half_year_transaction_amount",
        ),
    )
    customer_days = _union_rows(
        DOUDIAN_STORES, "customer_daily_sales",
        ("customer_id", "transaction_date"),
    )
    changes.append(_sync(
        conn, "doudian", "half_year_customer_health",
        ("period_start", "period_end", "customer_id"),
        (
            "half_year_purchase_count", "half_year_purchase_amount",
            "customer_health_score", "customer_health_status",
            "state_instructions", "follow_up_action",
        ),
        f'''
            WITH purchase_counts AS (
                SELECT period_start, period_end, customer_id,
                       COUNT(*)::bigint AS half_year_purchase_count
                FROM (
                    SELECT DISTINCT customer_id, transaction_date,
                           CASE WHEN EXTRACT(MONTH FROM transaction_date)::integer BETWEEN 2 AND 7
                                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::integer, 2, 1)
                                WHEN EXTRACT(MONTH FROM transaction_date)::integer >= 8
                                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::integer, 8, 1)
                                ELSE MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::integer - 1, 8, 1)
                           END AS period_start,
                           CASE WHEN EXTRACT(MONTH FROM transaction_date)::integer BETWEEN 2 AND 7
                                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::integer, 7, 31)
                                ELSE MAKE_DATE(
                                    EXTRACT(YEAR FROM transaction_date)::integer
                                      + CASE WHEN EXTRACT(MONTH FROM transaction_date)::integer >= 8 THEN 1 ELSE 0 END,
                                    1, 31
                                )
                           END AS period_end
                    FROM ({customer_days}) day_rows
                ) distinct_days
                GROUP BY period_start, period_end, customer_id
            ), purchase_amounts AS (
                SELECT period_start, period_end, customer_id,
                       SUM(half_year_transaction_amount)::numeric(18,2)
                           AS half_year_purchase_amount
                FROM ({amounts}) rows
                GROUP BY period_start, period_end, customer_id
            ), totals AS (
                SELECT amounts.period_start, amounts.period_end, amounts.customer_id,
                       counts.half_year_purchase_count,
                       amounts.half_year_purchase_amount
                FROM purchase_amounts amounts
                JOIN purchase_counts counts USING (period_start, period_end, customer_id)
            ), components AS (
                SELECT totals.*,
                       CASE WHEN half_year_purchase_count >= 4 THEN 100.00
                            WHEN half_year_purchase_count = 3 THEN 80.00
                            WHEN half_year_purchase_count BETWEEN 1 AND 2 THEN 60.00
                            ELSE 20.00 END::numeric(5,2) AS count_score,
                       CASE WHEN half_year_purchase_amount >= 550000 THEN 100.00
                            WHEN half_year_purchase_amount >= 400000 THEN 80.00
                            WHEN half_year_purchase_amount >= 200000 THEN 70.00
                            WHEN half_year_purchase_amount >= 100000 THEN 60.00
                            WHEN half_year_purchase_amount >= 50000 THEN 40.00
                            WHEN half_year_purchase_amount >= 10000 THEN 20.00
                            ELSE 10.00 END::numeric(5,2) AS amount_score
                FROM totals
            ), scored AS (
                SELECT components.*,
                       ROUND(count_score * 0.40 + amount_score * 0.60, 2)::numeric(5,2)
                           AS customer_health_score
                FROM components
            ), classified AS (
                SELECT scored.*,
                       CASE WHEN customer_health_score >= 90 THEN '高活跃'
                            WHEN customer_health_score >= 80 THEN '活跃'
                            WHEN customer_health_score >= 70 THEN '稳定'
                            WHEN customer_health_score >= 50 THEN '观察'
                            WHEN customer_health_score >= 40 THEN '风险'
                            WHEN customer_health_score >= 20 THEN '流失预警'
                            ELSE '流失' END AS customer_health_status
                FROM scored
            )
            SELECT classified.period_start, classified.period_end,
                   classified.customer_id, classified.half_year_purchase_count,
                   classified.half_year_purchase_amount,
                   classified.customer_health_score, classified.customer_health_status,
                   rules.state_instructions, rules.follow_up_action
            FROM classified
            LEFT JOIN public.talent_customer_status_action rules
              ON rules.customer_health_status = classified.customer_health_status
        ''',
    ))
    changes.append(_sync(
        conn, "doudian", "half_year_high_frequency_products",
        ("period_start", "period_end", "product_code"),
        (
            "half_year_product_quantity", "half_year_transaction_amount",
            "quantity_rank", "amount_rank", "selection_type",
        ),
        _high_frequency_select(DOUDIAN_STORES),
    ))
    return changes


def refresh_daren(conn: Connection) -> list[TableChange]:
    daily = "\nUNION ALL\n".join((
        "SELECT transaction_date, transaction_amount FROM weidian.daily_sales",
        "SELECT transaction_date, transaction_amount FROM doudian.daily_sales_summary",
        "SELECT transaction_date, transaction_amount FROM kuaishouxiaodian.daily_sales",
    ))
    changes = [_sync(
        conn, "daren", "daily_sales", ("transaction_date",),
        (
            "transaction_amount", "year_over_year_rate",
            "rolling_7_day_transaction_amount", "rolling_30_day_transaction_amount",
        ),
        f'''
            WITH daily AS (
                SELECT transaction_date,
                       SUM(transaction_amount)::numeric(20,2) AS transaction_amount
                FROM ({daily}) rows GROUP BY transaction_date
            )
            SELECT current.transaction_date, current.transaction_amount,
                   CASE WHEN previous.transaction_amount IS NULL OR previous.transaction_amount = 0 THEN 0
                        ELSE ROUND((current.transaction_amount - previous.transaction_amount)
                             / previous.transaction_amount * 100, 6)
                   END::numeric(20,6) AS year_over_year_rate,
                   (SELECT COALESCE(SUM(item.transaction_amount), 0)::numeric(20,2)
                    FROM daily item
                    WHERE item.transaction_date BETWEEN current.transaction_date - 6
                                                    AND current.transaction_date)
                        AS rolling_7_day_transaction_amount,
                   (SELECT COALESCE(SUM(item.transaction_amount), 0)::numeric(20,2)
                    FROM daily item
                    WHERE item.transaction_date BETWEEN current.transaction_date - 29
                                                    AND current.transaction_date)
                        AS rolling_30_day_transaction_amount
            FROM daily current
            LEFT JOIN daily previous
              ON previous.transaction_date = (current.transaction_date - INTERVAL '1 year')::date
        ''',
    )]

    for prefix, rate, interval in (
        ("weekly", "week_over_week_rate", "7 days"),
        ("monthly", "month_over_month_rate", "1 month"),
        ("quarterly", None, None),
        ("half_year", None, None),
    ):
        amount = f"{prefix}_transaction_amount"
        union = "\nUNION ALL\n".join((
            f"SELECT period_start, period_end, {amount} FROM weidian.{prefix}_sales",
            f"SELECT period_start, period_end, {amount} FROM doudian.{prefix}_sales_summary",
            f"SELECT period_start, period_end, {amount} FROM kuaishouxiaodian.{prefix}_sales",
        ))
        base = f'''
            WITH periods AS (
                SELECT period_start, period_end,
                       SUM({amount})::numeric(20,2) AS {amount}
                FROM ({union}) rows GROUP BY period_start, period_end
            )
        '''
        if rate:
            expected = base + f'''
                SELECT current.period_start, current.period_end, current.{amount},
                       CASE WHEN previous.{amount} IS NULL OR previous.{amount} = 0 THEN 0
                            ELSE ROUND((current.{amount} - previous.{amount})
                                 / previous.{amount} * 100, 6)
                       END::numeric(20,6) AS {rate}
                FROM periods current
                LEFT JOIN periods previous
                  ON previous.period_start = (current.period_start - INTERVAL '{interval}')::date
            '''
            values = (amount, rate)
        else:
            expected = base + f"SELECT period_start, period_end, {amount} FROM periods"
            values = (amount,)
        changes.append(_sync(
            conn, "daren", f"{prefix}_sales", ("period_start", "period_end"),
            values, expected,
        ))

    for prefix in ("weekly", "monthly", "quarterly", "half_year"):
        amount = f"{prefix}_refund_amount"
        union = "\nUNION ALL\n".join((
            f"SELECT period_start, period_end, {amount} FROM weidian.{prefix}_refunds",
            f"SELECT period_start, period_end, {amount} FROM doudian.{prefix}_refunds_summary",
            f"SELECT period_start, period_end, {amount} FROM kuaishouxiaodian.{prefix}_refunds",
        ))
        changes.append(_sync(
            conn, "daren", f"{prefix}_refunds", ("period_start", "period_end"),
            (amount,),
            f'''
                SELECT period_start, period_end,
                       SUM({amount})::numeric(20,2) AS {amount}
                FROM ({union}) rows GROUP BY period_start, period_end
            ''',
        ))

    changes.append(_sync(
        conn, "daren", "customer_health_detail",
        ("health_grain", "source_platform", "customer_id", "period_start", "period_end"),
        (
            "week_purchase_count", "month_purchase_count",
            "half_year_purchase_count", "half_year_purchase_amount",
            "week_score", "month_score", "customer_score",
            "customer_health_status", "state_instructions", "follow_up_action",
        ),
        '''
            WITH health_rows AS (
                SELECT 'business_half_year'::text AS health_grain,
                       'weidian'::text AS source_platform,
                       period_start, period_end, customer_id,
                       NULL::numeric(20,4) AS week_purchase_count,
                       NULL::numeric(20,4) AS month_purchase_count,
                       half_year_purchase_count, half_year_purchase_amount,
                       NULL::numeric(10,2) AS week_score,
                       NULL::numeric(10,2) AS month_score,
                       customer_health_score::numeric(10,2) AS customer_score,
                       customer_health_status
                FROM weidian.customer_health_detail
                UNION ALL
                SELECT 'business_half_year', 'doudian', period_start, period_end,
                       customer_id, NULL, NULL, half_year_purchase_count,
                       half_year_purchase_amount, NULL, NULL,
                       customer_health_score, customer_health_status
                FROM doudian.half_year_customer_health
                UNION ALL
                SELECT 'business_half_year', 'kuaishouxiaodian', period_start, period_end,
                       customer_id, NULL, NULL, half_year_purchase_count,
                       half_year_purchase_amount, NULL, NULL,
                       customer_health_score, customer_health_status
                FROM kuaishouxiaodian.customer_health_detail
            )
            SELECT health_rows.*,
                   rules.state_instructions, rules.follow_up_action
            FROM health_rows
            LEFT JOIN public.talent_customer_status_action rules
              ON rules.customer_health_status = health_rows.customer_health_status
        ''',
    ))
    changes.append(_sync(
        conn, "daren", "half_year_high_frequency_products",
        ("period_start", "period_end", "product_code"),
        (
            "half_year_product_quantity", "half_year_transaction_amount",
            "quantity_rank", "amount_rank", "selection_type",
        ),
        _high_frequency_select((
            "weidian", "doudianChildren", "doudianKocotree", "kuaishouxiaodian",
        )),
    ))
    return changes


def _channel_daily_select() -> str:
    union = "\nUNION ALL\n".join(
        f"SELECT '{schema}'::text AS group_key, transaction_date, transaction_amount "
        f"FROM {schema}.daily_sales"
        for schema in CHANNEL_GROUPS
    )
    return f'''
        WITH daily AS (
            SELECT transaction_date,
                   SUM(transaction_amount) FILTER (WHERE group_key = 'daren')::numeric(20,2)
                       AS daren_transaction_amount,
                   SUM(transaction_amount) FILTER (WHERE group_key = 'siyu')::numeric(20,2)
                       AS siyu_transaction_amount,
                   SUM(transaction_amount) FILTER (WHERE group_key = 'fenxiao')::numeric(20,2)
                       AS fenxiao_transaction_amount,
                   SUM(transaction_amount)::numeric(20,2) AS transaction_amount,
                   COUNT(DISTINCT group_key)::smallint AS included_group_count,
                   (COUNT(DISTINCT group_key) = 3) AS is_complete
            FROM ({union}) rows GROUP BY transaction_date
        )
        SELECT current.transaction_date,
               current.daren_transaction_amount, current.siyu_transaction_amount,
               current.fenxiao_transaction_amount, current.transaction_amount,
               current.included_group_count, current.is_complete,
               CASE WHEN NOT current.is_complete
                          OR previous.transaction_amount IS NULL
                          OR previous.transaction_amount = 0 THEN NULL
                    ELSE ROUND((current.transaction_amount - previous.transaction_amount)
                         / previous.transaction_amount * 100, 6)
               END::numeric(20,6) AS year_over_year_rate,
               CASE WHEN current.is_complete
                          AND (SELECT COUNT(*) FROM daily item
                               WHERE item.transaction_date BETWEEN current.transaction_date - 6
                                                               AND current.transaction_date) = 7
                    THEN (SELECT COALESCE(SUM(item.transaction_amount), 0)::numeric(20,2)
                FROM daily item
                WHERE item.transaction_date BETWEEN current.transaction_date - 6
                                                AND current.transaction_date) END
                    AS rolling_7_day_transaction_amount,
               CASE WHEN current.is_complete
                          AND (SELECT COUNT(*) FROM daily item
                               WHERE item.transaction_date BETWEEN current.transaction_date - 29
                                                               AND current.transaction_date) = 30
                    THEN (SELECT COALESCE(SUM(item.transaction_amount), 0)::numeric(20,2)
                FROM daily item
                WHERE item.transaction_date BETWEEN current.transaction_date - 29
                                                AND current.transaction_date) END
                    AS rolling_30_day_transaction_amount
        FROM daily current
        LEFT JOIN daily previous
          ON previous.transaction_date = (current.transaction_date - INTERVAL '1 year')::date
    '''


def _channel_period_select(
    prefix: str,
    kind: str,
    rate: str | None = None,
    interval: str | None = None,
) -> str:
    suffix = "transaction_amount" if kind == "sales" else "refund_amount"
    amount = f"{prefix}_{suffix}"
    union = "\nUNION ALL\n".join(
        f"SELECT '{schema}'::text AS group_key, period_start, period_end, {amount} "
        f"FROM {schema}.{prefix}_{kind}"
        for schema in CHANNEL_GROUPS
    )
    pivots = ",\n                   ".join(
        f"SUM({amount}) FILTER (WHERE group_key = '{schema}')::numeric(20,2) "
        f"AS {schema}_{amount}"
        for schema in CHANNEL_GROUPS
    )
    base = f'''
        WITH periods AS (
            SELECT period_start, period_end,
                   {pivots},
                   SUM({amount})::numeric(20,2) AS {amount},
                   COUNT(DISTINCT group_key)::smallint AS included_group_count,
                   (COUNT(DISTINCT group_key) = 3) AS is_complete
            FROM ({union}) rows GROUP BY period_start, period_end
        )
    '''
    columns = ", ".join(f"current.{schema}_{amount}" for schema in CHANNEL_GROUPS)
    if rate:
        return base + f'''
            SELECT current.period_start, current.period_end, {columns},
                   current.{amount}, current.included_group_count, current.is_complete,
                   CASE WHEN NOT current.is_complete
                              OR previous.{amount} IS NULL
                              OR previous.{amount} = 0 THEN NULL
                        ELSE ROUND((current.{amount} - previous.{amount})
                             / previous.{amount} * 100, 6)
                   END::numeric(20,6) AS {rate}
            FROM periods current
            LEFT JOIN periods previous
              ON previous.period_start = (current.period_start - INTERVAL '{interval}')::date
        '''
    return base + f'''
        SELECT current.period_start, current.period_end, {columns},
               current.{amount}, current.included_group_count, current.is_complete
        FROM periods current
    '''


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
        values = (
            f"daren_{amount}", f"siyu_{amount}", f"fenxiao_{amount}",
            amount, "included_group_count", "is_complete",
            *((rate,) if rate else ()),
        )
        changes.append(_sync(
            conn, "qudao", f"{prefix}_sales", ("period_start", "period_end"),
            values, _channel_period_select(prefix, "sales", rate, interval),
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
    return changes


def refresh_aggregates(conn: Connection) -> list[TableChange]:
    """Refresh all upper layers affected by a Kocotree store upload."""
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:doudian'))")
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:daren'))")
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:qudao'))")
    return [*refresh_doudian(conn), *refresh_daren(conn), *refresh_qudao(conn)]
