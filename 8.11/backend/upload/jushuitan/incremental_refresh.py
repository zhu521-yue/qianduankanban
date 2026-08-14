from __future__ import annotations

from datetime import date

from psycopg import Connection

from upload.periods import half_year_bounds, month_bounds, quarter_bounds, week_bounds
from upload.table_sync import TableChange, sync_table


GRAINS = {
    "weekly": ("week", week_bounds),
    "monthly": ("month", month_bounds),
    "quarterly": ("quarter", quarter_bounds),
    "half_year": ("half", half_year_bounds),
}


def _sync(
    conn: Connection,
    table: str,
    keys: tuple[str, ...],
    values: tuple[str, ...],
    expected: str,
    scope: str,
) -> TableChange:
    return sync_table(
        conn,
        schema_name="jushuitan",
        table_name=table,
        key_columns=keys,
        value_columns=values,
        expected_select=expected,
        delete_scope_sql=scope,
    )


def _prepare_scopes(conn: Connection, affected_dates: tuple[date, ...]) -> None:
    conn.execute('''
        CREATE TEMP TABLE upload_jushuitan_dates (
            transaction_date date PRIMARY KEY
        ) ON COMMIT DROP
    ''')
    conn.execute(
        "INSERT INTO upload_jushuitan_dates (transaction_date) SELECT DISTINCT UNNEST(%s::date[])",
        (list(affected_dates),),
    )
    conn.execute('''
        CREATE TEMP TABLE upload_jushuitan_periods (
            grain text NOT NULL,
            period_start date NOT NULL,
            period_end date NOT NULL,
            PRIMARY KEY (grain, period_start, period_end)
        ) ON COMMIT DROP
    ''')
    period_rows: list[tuple[str, date, date]] = []
    for prefix, (grain, bounds) in GRAINS.items():
        del prefix
        period_rows.extend((grain, *bounds(value)) for value in affected_dates)
    with conn.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO upload_jushuitan_periods (grain, period_start, period_end) "
            "VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
            period_rows,
        )


def _prepare_fact(conn: Connection) -> None:
    conn.execute(r'''
        CREATE TEMP TABLE upload_jushuitan_fact ON COMMIT DROP AS
        WITH cleaned AS (
            SELECT
                NULLIF(BTRIM(COALESCE(raw."付款日期"::text, ''), E' \t\n\r'), '') AS payment_text,
                NULLIF(REGEXP_REPLACE(COALESCE(raw."销售金额"::text, ''), '[,￥¥[:space:]]', '', 'g'), '') AS sales_amount_text,
                NULLIF(REGEXP_REPLACE(COALESCE(raw."销售数量"::text, ''), '[,[:space:]]', '', 'g'), '') AS sales_quantity_text,
                NULLIF(REGEXP_REPLACE(COALESCE(raw."实退数量"::text, ''), '[,[:space:]]', '', 'g'), '') AS refund_quantity_text,
                NULLIF(REGEXP_REPLACE(COALESCE(raw."实退金额"::text, ''), '[,￥¥[:space:]]', '', 'g'), '') AS refund_amount_text,
                NULLIF(BTRIM(COALESCE(raw."商品编码"::text, ''), E' \t\n\r'), '') AS product_code_text,
                BTRIM(COALESCE(raw."分销商"::text, ''), E' \t\n\r') AS distributor_text,
                BTRIM(COALESCE(raw."店铺"::text, ''), E' \t\n\r') AS shop_text,
                BTRIM(COALESCE(raw."订单状态"::text, ''), E' \t\n\r') AS order_status
            FROM jushuitan.raw_data raw
            JOIN upload_jushuitan_dates dates
              ON REGEXP_REPLACE(
                     REGEXP_REPLACE(
                         REPLACE(LEFT(BTRIM(COALESCE(raw."付款日期"::text, '')), 10), '/', '-'),
                         '^2525', '2025'
                     ), '^2024', '2026'
                 ) = dates.transaction_date::text
            WHERE REGEXP_REPLACE(
                      REGEXP_REPLACE(
                          REPLACE(LEFT(BTRIM(COALESCE(raw."付款日期"::text, '')), 10), '/', '-'),
                          '^2525', '2025'
                      ), '^2024', '2026'
                  ) ~ '^\d{4}-\d{2}-\d{2}$'
              AND BTRIM(COALESCE(raw."订单状态"::text, ''), E' \t\n\r') = '已发货'
        ), typed AS (
            SELECT
                REGEXP_REPLACE(
                    REGEXP_REPLACE(REPLACE(LEFT(payment_text, 10), '/', '-'), '^2525', '2025'),
                    '^2024', '2026'
                )::date AS transaction_date,
                CASE WHEN pg_input_is_valid(sales_amount_text, 'numeric')
                    THEN sales_amount_text::numeric ELSE 0 END AS sales_amount,
                CASE WHEN pg_input_is_valid(sales_quantity_text, 'numeric')
                    THEN sales_quantity_text::numeric ELSE 0 END AS sales_quantity,
                CASE WHEN pg_input_is_valid(refund_amount_text, 'numeric')
                    THEN refund_amount_text::numeric ELSE 0 END AS refund_amount,
                CASE WHEN pg_input_is_valid(refund_quantity_text, 'numeric')
                    THEN refund_quantity_text::numeric ELSE 0 END AS refund_quantity,
                product_code_text,
                distributor_text,
                shop_text,
                order_status
            FROM cleaned
        )
        SELECT transaction_date,
               ROUND(sales_quantity * sales_amount, 2)::numeric(18,2) AS transaction_amount,
               ROUND(refund_quantity * refund_amount, 2)::numeric(18,2) AS refund_amount,
               sales_quantity::numeric(18,4) AS product_quantity,
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
               order_status IN ('已发货', '已取消') AS is_sale,
               refund_quantity <> 0 OR refund_amount <> 0 AS is_refund
        FROM typed
    ''')
    conn.execute("CREATE INDEX ON upload_jushuitan_fact (transaction_date)")
    conn.execute("CREATE INDEX ON upload_jushuitan_fact (customer_id, transaction_date)")
    conn.execute("CREATE INDEX ON upload_jushuitan_fact (product_code, transaction_date)")
    conn.execute("ANALYZE upload_jushuitan_fact")


def _additive_period_expected(
    table: str,
    grain: str,
    prefix: str,
    dimension: str = "",
    include_quantity: bool = False,
) -> str:
    amount = f"{prefix}_transaction_amount"
    dimension_select = f", fact.{dimension}" if dimension else ""
    dimension_target = f", target.{dimension}" if dimension else ""
    dimension_group = f", fact.{dimension}" if dimension else ""
    join_keys = f"period_start, period_end{', ' + dimension if dimension else ''}"
    key_select = (
        f", COALESCE(current.{dimension}, delta.{dimension}) AS {dimension}"
        if dimension else ""
    )
    quantity_delta = (
        f", SUM(fact.product_quantity)::numeric(18,4) AS {prefix}_product_quantity"
        if include_quantity else ""
    )
    quantity_current = (
        f", target.{prefix}_product_quantity" if include_quantity else ""
    )
    quantity_result = (
        f", (COALESCE(current.{prefix}_product_quantity, 0) "
        f"+ COALESCE(delta.{prefix}_product_quantity, 0))::numeric(18,4) "
        f"AS {prefix}_product_quantity"
        if include_quantity else ""
    )
    return f'''
        WITH delta AS (
            SELECT periods.period_start, periods.period_end{dimension_select},
                   SUM(fact.transaction_amount)::numeric(18,2) AS {amount}
                   {quantity_delta}
            FROM upload_jushuitan_periods periods
            JOIN upload_jushuitan_fact fact
              ON fact.transaction_date BETWEEN periods.period_start AND periods.period_end
             AND fact.is_sale
            WHERE periods.grain = '{grain}' {{extra_filter}}
            GROUP BY periods.period_start, periods.period_end{dimension_group}
        ), current AS (
            SELECT target.period_start, target.period_end{dimension_target},
                   target.{amount}{quantity_current}
            FROM jushuitan.{table} target
            JOIN upload_jushuitan_periods periods
              ON periods.grain = '{grain}'
             AND periods.period_start = target.period_start
             AND periods.period_end = target.period_end
        )
        SELECT COALESCE(current.period_start, delta.period_start) AS period_start,
               COALESCE(current.period_end, delta.period_end) AS period_end{key_select},
               (COALESCE(current.{amount}, 0) + COALESCE(delta.{amount}, 0))::numeric(18,2)
                   AS {amount}{quantity_result}
        FROM current FULL OUTER JOIN delta USING ({join_keys})
    '''


def _period_scope(grain: str) -> str:
    return f'''EXISTS (
        SELECT 1 FROM upload_jushuitan_periods periods
        WHERE periods.grain = '{grain}'
          AND periods.period_start = target.period_start
          AND periods.period_end = target.period_end
    )'''


def _refresh_health(conn: Connection) -> TableChange:
    conn.execute('''
        CREATE TEMP TABLE upload_jushuitan_health_customers ON COMMIT DROP AS
        SELECT DISTINCT daily.customer_id
        FROM jushuitan.customer_daily_sales daily
        JOIN upload_jushuitan_dates dates USING (transaction_date)
    ''')
    conn.execute("CREATE UNIQUE INDEX ON upload_jushuitan_health_customers (customer_id)")
    conn.execute('''
        CREATE TEMP TABLE upload_jushuitan_health_weeks ON COMMIT DROP AS
        SELECT DISTINCT weekly.period_start, weekly.period_end
        FROM jushuitan.customer_weekly_sales weekly
        JOIN upload_jushuitan_periods monthly
          ON monthly.grain = 'month'
         AND weekly.period_start <= monthly.period_end
         AND weekly.period_end >= monthly.period_start
    ''')
    conn.execute(
        "CREATE UNIQUE INDEX ON upload_jushuitan_health_weeks (period_start, period_end)"
    )
    conn.execute('''
        INSERT INTO upload_jushuitan_health_weeks (period_start, period_end)
        SELECT period_start, period_end
        FROM upload_jushuitan_periods
        WHERE grain = 'week'
        ON CONFLICT DO NOTHING
    ''')
    values = (
        "week_period_start", "week_period_end", "month_period_start", "month_period_end",
        "week_purchase_count", "week_score", "month_purchase_count", "month_score",
        "customer_score", "customer_health_status", "state_instructions", "follow_up_action",
    )
    expected = '''
        WITH calendar AS (
            SELECT customers.customer_id, weeks.period_start, weeks.period_end
            FROM upload_jushuitan_health_customers customers
            CROSS JOIN upload_jushuitan_health_weeks weeks
        ), counts AS (
            SELECT calendar.*,
                   DATE_TRUNC('month', calendar.period_start)::date AS month_period_start,
                   (DATE_TRUNC('month', calendar.period_end)::date
                       + INTERVAL '1 month - 1 day')::date AS month_period_end,
                   COALESCE(weekly.weekly_purchase_count, 0)::integer AS week_purchase_count,
                   CASE WHEN DATE_TRUNC('month', calendar.period_start)::date
                                  = DATE_TRUNC('month', calendar.period_end)::date
                        THEN COALESCE(month_one.monthly_purchase_count, 0)::numeric(10,2)
                        ELSE ROUND((COALESCE(month_one.monthly_purchase_count, 0)
                                  + COALESCE(month_two.monthly_purchase_count, 0)) / 2.0, 2)::numeric(10,2)
                   END AS month_purchase_count
            FROM calendar
            LEFT JOIN jushuitan.customer_weekly_sales weekly
              ON weekly.customer_id = calendar.customer_id
             AND weekly.period_start = calendar.period_start
            LEFT JOIN jushuitan.customer_monthly_sales month_one
              ON month_one.customer_id = calendar.customer_id
             AND month_one.period_start = DATE_TRUNC('month', calendar.period_start)::date
            LEFT JOIN jushuitan.customer_monthly_sales month_two
              ON month_two.customer_id = calendar.customer_id
             AND month_two.period_start = DATE_TRUNC('month', calendar.period_end)::date
        ), scores AS (
            SELECT counts.*,
                   CASE WHEN week_purchase_count >= 7 THEN 100 WHEN week_purchase_count >= 6 THEN 90
                        WHEN week_purchase_count >= 5 THEN 80 WHEN week_purchase_count >= 4 THEN 70
                        WHEN week_purchase_count >= 3 THEN 50 WHEN week_purchase_count >= 2 THEN 30
                        WHEN week_purchase_count >= 1 THEN 10 ELSE 0 END::numeric(5,2) AS week_score,
                   CASE WHEN month_purchase_count >= 30 THEN 100 WHEN month_purchase_count >= 20 THEN 80
                        WHEN month_purchase_count >= 15 THEN 60 WHEN month_purchase_count >= 10 THEN 40
                        WHEN month_purchase_count >= 5 THEN 20 ELSE 10 END::numeric(5,2) AS month_score
            FROM counts
        ), final AS (
            SELECT scores.*,
                   ROUND(0.7 * week_score + 0.3 * month_score, 2)::numeric(5,2) AS customer_score
            FROM scores
        ), classified AS (
            SELECT final.*,
                   CASE WHEN customer_score >= 90 THEN '高活跃' WHEN customer_score >= 80 THEN '活跃'
                        WHEN customer_score >= 70 THEN '稳定' WHEN customer_score >= 60 THEN '观察'
                        WHEN customer_score >= 50 THEN '风险' WHEN customer_score >= 40 THEN '流失预警'
                        ELSE '流失' END AS customer_health_status
            FROM final
        )
        SELECT classified.customer_id, classified.period_start, classified.period_end,
               classified.period_start AS week_period_start,
               classified.period_end AS week_period_end,
               classified.month_period_start, classified.month_period_end,
               classified.week_purchase_count, classified.week_score,
               classified.month_purchase_count, classified.month_score,
               classified.customer_score, classified.customer_health_status,
               rules.state_instructions, rules.follow_up_action
        FROM classified
        LEFT JOIN public.distribution_customer_status_action rules
          ON rules.customer_health_status = classified.customer_health_status
    '''
    scope = '''
        target.customer_id IN (SELECT customer_id FROM upload_jushuitan_health_customers)
        AND EXISTS (
            SELECT 1 FROM upload_jushuitan_health_weeks weeks
            WHERE weeks.period_start = target.period_start
              AND weeks.period_end = target.period_end
        )
    '''
    return _sync(
        conn,
        "customer_health_detail",
        ("customer_id", "period_start", "period_end"),
        values,
        expected,
        scope,
    )


def refresh_store_incremental(
    conn: Connection,
    affected_dates: tuple[date, ...],
) -> list[TableChange]:
    _prepare_scopes(conn, affected_dates)
    _prepare_fact(conn)
    changes: list[TableChange] = []
    day_scope = "target.transaction_date IN (SELECT transaction_date FROM upload_jushuitan_dates)"

    changes.append(_sync(conn, "daily_sales", ("transaction_date",), ("transaction_amount",), '''
        SELECT fact.transaction_date,
               SUM(fact.transaction_amount)::numeric(18,2) AS transaction_amount
        FROM upload_jushuitan_fact fact
        JOIN upload_jushuitan_dates dates USING (transaction_date)
        WHERE fact.is_sale
        GROUP BY fact.transaction_date
    ''', day_scope))
    changes.append(_sync(conn, "daily_product_sales", ("transaction_date", "product_code"), (
        "transaction_amount", "product_quantity",
    ), '''
        SELECT fact.transaction_date, fact.product_code,
               SUM(fact.transaction_amount)::numeric(18,2) AS transaction_amount,
               SUM(fact.product_quantity)::numeric(18,4) AS product_quantity
        FROM upload_jushuitan_fact fact
        JOIN upload_jushuitan_dates dates USING (transaction_date)
        WHERE fact.is_sale AND fact.product_code IS NOT NULL
        GROUP BY fact.transaction_date, fact.product_code
    ''', day_scope))
    changes.append(_sync(conn, "daily_customer_sales", ("transaction_date", "customer_id"), (
        "transaction_amount",
    ), '''
        SELECT fact.transaction_date, fact.customer_id,
               SUM(fact.transaction_amount)::numeric(18,2) AS transaction_amount
        FROM upload_jushuitan_fact fact
        JOIN upload_jushuitan_dates dates USING (transaction_date)
        WHERE fact.is_sale AND fact.customer_id IS NOT NULL
        GROUP BY fact.transaction_date, fact.customer_id
    ''', day_scope))

    for prefix, (grain, _) in GRAINS.items():
        scope = _period_scope(grain)
        sales_expected = _additive_period_expected(
            f"{prefix}_sales", grain, prefix,
        ).format(extra_filter="")
        changes.append(_sync(conn, f"{prefix}_sales", ("period_start", "period_end"), (
            f"{prefix}_transaction_amount",
        ), sales_expected, scope))
        changes.append(_sync(conn, f"{prefix}_refunds", ("period_start", "period_end"), (
            f"{prefix}_refund_amount",
        ), f'''
            WITH delta AS (
                SELECT periods.period_start, periods.period_end,
                       SUM(fact.refund_amount)::numeric(18,2) AS {prefix}_refund_amount
                FROM upload_jushuitan_periods periods
                JOIN upload_jushuitan_fact fact
                  ON fact.transaction_date BETWEEN periods.period_start AND periods.period_end
                 AND fact.is_sale AND fact.is_refund
                WHERE periods.grain = '{grain}'
                GROUP BY periods.period_start, periods.period_end
            ), current AS (
                SELECT target.period_start, target.period_end,
                       target.{prefix}_refund_amount
                FROM jushuitan.{prefix}_refunds target
                JOIN upload_jushuitan_periods periods
                  ON periods.grain = '{grain}'
                 AND periods.period_start = target.period_start
                 AND periods.period_end = target.period_end
            )
            SELECT COALESCE(current.period_start, delta.period_start) AS period_start,
                   COALESCE(current.period_end, delta.period_end) AS period_end,
                   (COALESCE(current.{prefix}_refund_amount, 0)
                    + COALESCE(delta.{prefix}_refund_amount, 0))::numeric(18,2)
                       AS {prefix}_refund_amount
            FROM current FULL OUTER JOIN delta USING (period_start, period_end)
        ''', scope))
        product_expected = _additive_period_expected(
            f"{prefix}_product_sales", grain, prefix, "product_code", True,
        ).format(
            extra_filter="AND fact.product_code IS NOT NULL",
        )
        changes.append(_sync(conn, f"{prefix}_product_sales", (
            "period_start", "period_end", "product_code",
        ), (f"{prefix}_transaction_amount", f"{prefix}_product_quantity"), product_expected, scope))
        customer_expected = _additive_period_expected(
            f"{prefix}_customer_sales", grain, prefix, "customer_id",
        ).format(
            extra_filter="AND fact.customer_id IS NOT NULL",
        )
        changes.append(_sync(conn, f"{prefix}_customer_sales", (
            "period_start", "period_end", "customer_id",
        ), (f"{prefix}_transaction_amount",), customer_expected, scope))

    conn.execute('''
        CREATE TEMP TABLE upload_jushuitan_daily_metric_dates ON COMMIT DROP AS
        SELECT DISTINCT current.transaction_date
        FROM jushuitan.daily_sales current
        WHERE EXISTS (
            SELECT 1 FROM upload_jushuitan_dates changed
            WHERE current.transaction_date BETWEEN changed.transaction_date
                                               AND changed.transaction_date + 29
               OR current.transaction_date = (changed.transaction_date + INTERVAL '1 year')::date
        )
    ''')
    daily_metric_scope = "target.transaction_date IN (SELECT transaction_date FROM upload_jushuitan_daily_metric_dates)"
    changes.append(_sync(conn, "daily_sales_metrics", ("transaction_date",), (
        "transaction_amount", "year_over_year_rate",
        "rolling_7_day_transaction_amount", "rolling_30_day_transaction_amount",
    ), '''
        SELECT current.transaction_date, current.transaction_amount,
               CASE WHEN previous.transaction_amount IS NULL OR previous.transaction_amount = 0 THEN 0.00
                    ELSE ROUND((current.transaction_amount - previous.transaction_amount)
                         / previous.transaction_amount * 100, 2) END::numeric(12,2) AS year_over_year_rate,
               (SELECT COALESCE(SUM(item.transaction_amount),0)::numeric(18,2)
                FROM jushuitan.daily_sales item
                WHERE item.transaction_date BETWEEN current.transaction_date - 6 AND current.transaction_date)
                    AS rolling_7_day_transaction_amount,
               (SELECT COALESCE(SUM(item.transaction_amount),0)::numeric(18,2)
                FROM jushuitan.daily_sales item
                WHERE item.transaction_date BETWEEN current.transaction_date - 29 AND current.transaction_date)
                    AS rolling_30_day_transaction_amount
        FROM jushuitan.daily_sales current
        JOIN upload_jushuitan_daily_metric_dates dates USING (transaction_date)
        LEFT JOIN jushuitan.daily_sales previous
          ON previous.transaction_date = (current.transaction_date - INTERVAL '1 year')::date
    ''', daily_metric_scope))

    for prefix, rate, interval, grain in (
        ("weekly", "week_over_week_rate", "7 days", "week"),
        ("monthly", "month_over_month_rate", "1 month", "month"),
    ):
        conn.execute(f'''
            CREATE TEMP TABLE upload_jushuitan_{prefix}_metric_periods ON COMMIT DROP AS
            SELECT sales.period_start, sales.period_end
            FROM jushuitan.{prefix}_sales sales
            WHERE EXISTS (
                SELECT 1 FROM upload_jushuitan_periods changed
                WHERE changed.grain = '{grain}'
                  AND (sales.period_start = changed.period_start
                       OR sales.period_start = (changed.period_start + INTERVAL '{interval}')::date)
            )
        ''')
        metric_scope = f'''EXISTS (
            SELECT 1 FROM upload_jushuitan_{prefix}_metric_periods periods
            WHERE periods.period_start = target.period_start
              AND periods.period_end = target.period_end
        )'''
        amount = f"{prefix}_transaction_amount"
        changes.append(_sync(conn, f"{prefix}_sales_metrics", ("period_start", "period_end"), (
            amount, rate,
        ), f'''
            SELECT current.period_start, current.period_end, current.{amount},
                   CASE WHEN previous.{amount} IS NULL OR previous.{amount} = 0 THEN 0.00
                        ELSE ROUND((current.{amount} - previous.{amount})
                             / previous.{amount} * 100, 2) END::numeric(12,2) AS {rate}
            FROM jushuitan.{prefix}_sales current
            JOIN upload_jushuitan_{prefix}_metric_periods periods
              USING (period_start, period_end)
            LEFT JOIN jushuitan.{prefix}_sales previous
              ON previous.period_start = (current.period_start - INTERVAL '{interval}')::date
        ''', metric_scope))

    changes.append(_sync(conn, "customer_daily_sales", ("customer_id", "transaction_date"), (
        "transaction_amount",
    ), '''
        SELECT customer_id, transaction_date, transaction_amount
        FROM jushuitan.daily_customer_sales
        WHERE transaction_date IN (SELECT transaction_date FROM upload_jushuitan_dates)
    ''', day_scope))
    conn.execute('''
        CREATE TEMP TABLE upload_jushuitan_customer_metric_keys ON COMMIT DROP AS
        SELECT DISTINCT current.customer_id, current.transaction_date
        FROM jushuitan.customer_daily_sales current
        WHERE EXISTS (
            SELECT 1 FROM upload_jushuitan_dates changed
            WHERE current.transaction_date BETWEEN changed.transaction_date
                                               AND changed.transaction_date + 29
        )
          AND current.customer_id IN (
              SELECT DISTINCT customer_id FROM upload_jushuitan_fact
              WHERE customer_id IS NOT NULL
                AND transaction_date IN (SELECT transaction_date FROM upload_jushuitan_dates)
          )
    ''')
    customer_metric_scope = '''EXISTS (
        SELECT 1 FROM upload_jushuitan_customer_metric_keys keys
        WHERE keys.customer_id = target.customer_id
          AND keys.transaction_date = target.transaction_date
    )'''
    changes.append(_sync(conn, "customer_daily_sales_metrics", ("customer_id", "transaction_date"), (
        "transaction_amount", "rolling_7_day_transaction_amount", "rolling_30_day_transaction_amount",
    ), '''
        SELECT current.customer_id, current.transaction_date, current.transaction_amount,
               (SELECT COALESCE(SUM(item.transaction_amount),0)::numeric(18,2)
                FROM jushuitan.customer_daily_sales item
                WHERE item.customer_id = current.customer_id
                  AND item.transaction_date BETWEEN current.transaction_date - 6 AND current.transaction_date)
                    AS rolling_7_day_transaction_amount,
               (SELECT COALESCE(SUM(item.transaction_amount),0)::numeric(18,2)
                FROM jushuitan.customer_daily_sales item
                WHERE item.customer_id = current.customer_id
                  AND item.transaction_date BETWEEN current.transaction_date - 29 AND current.transaction_date)
                    AS rolling_30_day_transaction_amount
        FROM jushuitan.customer_daily_sales current
        JOIN upload_jushuitan_customer_metric_keys keys USING (customer_id, transaction_date)
    ''', customer_metric_scope))

    for prefix, (grain, _) in GRAINS.items():
        scope = _period_scope(grain)
        changes.append(_sync(conn, f"customer_{prefix}_sales", (
            "customer_id", "period_start", "period_end",
        ), (f"{prefix}_transaction_amount", f"{prefix}_purchase_count"), f'''
            WITH delta AS (
                SELECT fact.customer_id, periods.period_start, periods.period_end,
                       SUM(fact.transaction_amount)::numeric(18,2) AS {prefix}_transaction_amount,
                       COUNT(DISTINCT fact.transaction_date)::integer AS {prefix}_purchase_count
                FROM upload_jushuitan_periods periods
                JOIN upload_jushuitan_fact fact
                  ON fact.transaction_date BETWEEN periods.period_start AND periods.period_end
                 AND fact.is_sale AND fact.customer_id IS NOT NULL
                WHERE periods.grain = '{grain}'
                GROUP BY fact.customer_id, periods.period_start, periods.period_end
            ), current AS (
                SELECT target.customer_id, target.period_start, target.period_end,
                       target.{prefix}_transaction_amount, target.{prefix}_purchase_count
                FROM jushuitan.customer_{prefix}_sales target
                JOIN upload_jushuitan_periods periods
                  ON periods.grain = '{grain}'
                 AND periods.period_start = target.period_start
                 AND periods.period_end = target.period_end
            )
            SELECT COALESCE(current.customer_id, delta.customer_id) AS customer_id,
                   COALESCE(current.period_start, delta.period_start) AS period_start,
                   COALESCE(current.period_end, delta.period_end) AS period_end,
                   (COALESCE(current.{prefix}_transaction_amount, 0)
                    + COALESCE(delta.{prefix}_transaction_amount, 0))::numeric(18,2)
                       AS {prefix}_transaction_amount,
                   (COALESCE(current.{prefix}_purchase_count, 0)
                    + COALESCE(delta.{prefix}_purchase_count, 0))::integer
                       AS {prefix}_purchase_count
            FROM current FULL OUTER JOIN delta
              USING (customer_id, period_start, period_end)
        ''', scope))

    changes.append(_sync(conn, "customer_daily_product_sales", (
        "customer_id", "transaction_date", "product_code",
    ), ("transaction_amount", "product_quantity"), '''
        SELECT fact.customer_id, fact.transaction_date, fact.product_code,
               SUM(fact.transaction_amount)::numeric(18,2) AS transaction_amount,
               SUM(fact.product_quantity)::numeric(18,4) AS product_quantity
        FROM upload_jushuitan_fact fact
        JOIN upload_jushuitan_dates dates USING (transaction_date)
        WHERE fact.is_sale AND fact.customer_id IS NOT NULL AND fact.product_code IS NOT NULL
        GROUP BY fact.customer_id, fact.transaction_date, fact.product_code
    ''', day_scope))
    for prefix, grain in (("monthly", "month"), ("quarterly", "quarter"), ("half_year", "half")):
        scope = _period_scope(grain)
        changes.append(_sync(conn, f"customer_{prefix}_product_sales", (
            "customer_id", "period_start", "period_end", "product_code",
        ), (f"{prefix}_transaction_amount", f"{prefix}_product_quantity"), f'''
            WITH delta AS (
                SELECT fact.customer_id, periods.period_start, periods.period_end, fact.product_code,
                       SUM(fact.transaction_amount)::numeric(18,2) AS {prefix}_transaction_amount,
                       SUM(fact.product_quantity)::numeric(18,4) AS {prefix}_product_quantity
                FROM upload_jushuitan_periods periods
                JOIN upload_jushuitan_fact fact
                  ON fact.transaction_date BETWEEN periods.period_start AND periods.period_end
                 AND fact.is_sale AND fact.customer_id IS NOT NULL AND fact.product_code IS NOT NULL
                WHERE periods.grain = '{grain}'
                GROUP BY fact.customer_id, periods.period_start, periods.period_end, fact.product_code
            ), current AS (
                SELECT target.customer_id, target.period_start, target.period_end,
                       target.product_code, target.{prefix}_transaction_amount,
                       target.{prefix}_product_quantity
                FROM jushuitan.customer_{prefix}_product_sales target
                JOIN upload_jushuitan_periods periods
                  ON periods.grain = '{grain}'
                 AND periods.period_start = target.period_start
                 AND periods.period_end = target.period_end
            )
            SELECT COALESCE(current.customer_id, delta.customer_id) AS customer_id,
                   COALESCE(current.period_start, delta.period_start) AS period_start,
                   COALESCE(current.period_end, delta.period_end) AS period_end,
                   COALESCE(current.product_code, delta.product_code) AS product_code,
                   (COALESCE(current.{prefix}_transaction_amount, 0)
                    + COALESCE(delta.{prefix}_transaction_amount, 0))::numeric(18,2)
                       AS {prefix}_transaction_amount,
                   (COALESCE(current.{prefix}_product_quantity, 0)
                    + COALESCE(delta.{prefix}_product_quantity, 0))::numeric(18,4)
                       AS {prefix}_product_quantity
            FROM current FULL OUTER JOIN delta
              USING (customer_id, period_start, period_end, product_code)
        ''', scope))

    changes.append(_refresh_health(conn))
    if len(changes) != 33:
        raise ValueError(f"聚水潭增量刷新表数异常：{len(changes)} != 33")
    return changes
