from __future__ import annotations

from datetime import date

from psycopg import Connection

from upload.models import StoreUploadConfig, UploadAnalysis
from upload.periods import half_year_bounds, month_bounds, quarter_bounds, week_bounds
from upload.table_sync import TableChange, sync_table


SUPPORTED_SCHEMAS = frozenset({"qijian", "muyinqijian"})
GRAINS = {
    "weekly": ("week", week_bounds),
    "monthly": ("month", month_bounds),
    "quarterly": ("quarter", quarter_bounds),
    "half_year": ("half", half_year_bounds),
}


def affected_customer_ids(
    config: StoreUploadConfig,
    analysis: UploadAnalysis,
) -> tuple[str, ...]:
    values: set[str] = set()
    for item in analysis.changed_rows:
        current = config.customer_resolver(item.prepared.values)
        previous = (
            config.customer_resolver(item.previous_values)
            if item.previous_values is not None
            else None
        )
        for customer in (current, previous):
            if customer and customer.get("customer_id"):
                values.add(customer["customer_id"])
    values.update(customer["customer_id"] for customer in analysis.missing_customers)
    return tuple(sorted(values))


def _quoted_schema(schema_name: str) -> str:
    if schema_name not in SUPPORTED_SCHEMAS:
        raise ValueError(f"有赞增量刷新不支持schema：{schema_name}")
    return '"' + schema_name.replace('"', '""') + '"'


def _sync(
    conn: Connection,
    schema_name: str,
    table: str,
    keys: tuple[str, ...],
    values: tuple[str, ...],
    expected: str,
    scope: str,
) -> TableChange:
    return sync_table(
        conn,
        schema_name=schema_name,
        table_name=table,
        key_columns=keys,
        value_columns=values,
        expected_select=expected,
        delete_scope_sql=scope,
    )


def _prepare_scopes(
    conn: Connection,
    affected_dates: tuple[date, ...],
    customer_ids: tuple[str, ...],
) -> None:
    conn.execute('''
        CREATE TEMP TABLE upload_youzan_dates (
            transaction_date date PRIMARY KEY
        ) ON COMMIT DROP
    ''')
    conn.execute(
        "INSERT INTO upload_youzan_dates (transaction_date) "
        "SELECT DISTINCT UNNEST(%s::date[])",
        (list(affected_dates),),
    )
    conn.execute('''
        CREATE TEMP TABLE upload_youzan_periods (
            grain text NOT NULL,
            period_start date NOT NULL,
            period_end date NOT NULL,
            PRIMARY KEY (grain, period_start, period_end)
        ) ON COMMIT DROP
    ''')
    period_rows: list[tuple[str, date, date]] = []
    for _, (grain, bounds) in GRAINS.items():
        period_rows.extend((grain, *bounds(value)) for value in affected_dates)
    with conn.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO upload_youzan_periods (grain, period_start, period_end) "
            "VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
            period_rows,
        )
    conn.execute('''
        CREATE TEMP TABLE upload_youzan_customers (
            customer_id text PRIMARY KEY
        ) ON COMMIT DROP
    ''')
    if customer_ids:
        conn.execute(
            "INSERT INTO upload_youzan_customers (customer_id) "
            "SELECT DISTINCT NULLIF(BTRIM(value), '') FROM UNNEST(%s::text[]) value "
            "WHERE NULLIF(BTRIM(value), '') IS NOT NULL",
            (list(customer_ids),),
        )


def _prepare_fact(conn: Connection, schema_name: str) -> None:
    schema = _quoted_schema(schema_name)
    conn.execute(f'''
        CREATE TEMP TABLE upload_youzan_fact ON COMMIT DROP AS
        WITH cleaned AS (
            SELECT
                NULLIF(BTRIM(COALESCE(raw."订单创建时间"::text, ''), E' \\t\\n\\r'), '') AS order_time_text,
                NULLIF(REGEXP_REPLACE(COALESCE(raw."商品单价"::text, ''), '[,￥¥[:space:]]', '', 'g'), '') AS unit_price_text,
                NULLIF(REGEXP_REPLACE(COALESCE(raw."商品数量"::text, ''), '[,[:space:]]', '', 'g'), '') AS quantity_text,
                NULLIF(REGEXP_REPLACE(COALESCE(raw."商品已退款金额"::text, ''), '[,￥¥[:space:]]', '', 'g'), '') AS refund_text,
                raw."规格编码"::text AS product_code_raw,
                BTRIM(COALESCE(raw."买家昵称"::text, ''), E' \\t\\n\\r') AS customer_id_text,
                BTRIM(COALESCE(raw."销售渠道"::text, ''), E' \\t\\n\\r') AS sales_channel,
                BTRIM(COALESCE(raw."订单状态"::text, ''), E' \\t\\n\\r') AS order_status
            FROM {schema}.raw_data raw
            WHERE pg_input_is_valid(
                NULLIF(BTRIM(COALESCE(raw."订单创建时间"::text, ''), E' \\t\\n\\r'), ''),
                'timestamp'
            )
        ), typed AS (
            SELECT
                order_time_text::timestamp::date AS transaction_date,
                CASE WHEN pg_input_is_valid(unit_price_text, 'numeric')
                          AND pg_input_is_valid(quantity_text, 'numeric')
                     THEN unit_price_text::numeric * quantity_text::numeric END AS transaction_amount,
                CASE WHEN pg_input_is_valid(refund_text, 'numeric')
                     THEN refund_text::numeric ELSE 0 END AS refund_amount,
                CASE WHEN pg_input_is_valid(quantity_text, 'numeric')
                     THEN quantity_text::numeric END AS product_quantity,
                product_code_raw,
                customer_id_text,
                sales_channel,
                order_status
            FROM cleaned
        ), normalized AS (
            SELECT
                transaction_date,
                ROUND(transaction_amount, 2)::numeric(18,2) AS transaction_amount,
                ROUND(refund_amount, 2)::numeric(18,2) AS refund_amount,
                product_quantity::numeric(18,4) AS product_quantity,
                CASE WHEN BTRIM(COALESCE(product_code_raw, ''), E' \\t\\n\\r') NOT IN ('', '-')
                     THEN product_code_raw END AS product_code,
                CASE WHEN sales_channel = '网店'
                           AND customer_id_text NOT IN ('', '-', '0', '0.0')
                     THEN customer_id_text END AS customer_id,
                order_status IN ('已完成', '已关闭', '已发货') AS is_sale,
                refund_amount > 0 AS is_refund
            FROM typed
        )
        SELECT normalized.*
        FROM normalized
        WHERE EXISTS (
            SELECT 1
            FROM upload_youzan_periods periods
            WHERE periods.grain = 'half'
              AND normalized.transaction_date BETWEEN periods.period_start AND periods.period_end
        )
    ''')
    conn.execute("CREATE INDEX ON upload_youzan_fact (transaction_date)")
    conn.execute("CREATE INDEX ON upload_youzan_fact (customer_id, transaction_date)")
    conn.execute("CREATE INDEX ON upload_youzan_fact (product_code, transaction_date)")
    conn.execute("ANALYZE upload_youzan_fact")
    conn.execute('''
        INSERT INTO upload_youzan_customers (customer_id)
        SELECT DISTINCT fact.customer_id
        FROM upload_youzan_fact fact
        JOIN upload_youzan_dates dates USING (transaction_date)
        WHERE fact.is_sale AND fact.customer_id IS NOT NULL
        ON CONFLICT DO NOTHING
    ''')


def _period_scope(grain: str) -> str:
    return f'''EXISTS (
        SELECT 1 FROM upload_youzan_periods periods
        WHERE periods.grain = '{grain}'
          AND periods.period_start = target.period_start
          AND periods.period_end = target.period_end
    )'''


def _period_sales_expected(grain: str, prefix: str) -> str:
    return f'''
        SELECT periods.period_start, periods.period_end,
               SUM(fact.transaction_amount)::numeric(18,2)
                   AS {prefix}_transaction_amount
        FROM upload_youzan_periods periods
        JOIN upload_youzan_fact fact
          ON fact.transaction_date BETWEEN periods.period_start AND periods.period_end
         AND fact.is_sale
        WHERE periods.grain = '{grain}'
        GROUP BY periods.period_start, periods.period_end
    '''


def _period_refunds_expected(grain: str, prefix: str) -> str:
    return f'''
        SELECT periods.period_start, periods.period_end,
               SUM(fact.refund_amount)::numeric(18,2)
                   AS {prefix}_refund_amount
        FROM upload_youzan_periods periods
        JOIN upload_youzan_fact fact
          ON fact.transaction_date BETWEEN periods.period_start AND periods.period_end
         AND fact.is_refund
        WHERE periods.grain = '{grain}'
        GROUP BY periods.period_start, periods.period_end
    '''


def _period_product_expected(grain: str, prefix: str) -> str:
    return f'''
        SELECT periods.period_start, periods.period_end, fact.product_code,
               SUM(fact.transaction_amount)::numeric(18,2) AS {prefix}_transaction_amount,
               SUM(fact.product_quantity)::numeric(18,4) AS {prefix}_product_quantity
        FROM upload_youzan_periods periods
        JOIN upload_youzan_fact fact
          ON fact.transaction_date BETWEEN periods.period_start AND periods.period_end
         AND fact.is_sale AND fact.product_code IS NOT NULL
        WHERE periods.grain = '{grain}'
        GROUP BY periods.period_start, periods.period_end, fact.product_code
    '''


def _period_customer_expected(grain: str, prefix: str) -> str:
    return f'''
        SELECT periods.period_start, periods.period_end, fact.customer_id,
               SUM(fact.transaction_amount)::numeric(18,2) AS {prefix}_transaction_amount
        FROM upload_youzan_periods periods
        JOIN upload_youzan_fact fact
          ON fact.transaction_date BETWEEN periods.period_start AND periods.period_end
         AND fact.is_sale AND fact.customer_id IS NOT NULL
        WHERE periods.grain = '{grain}'
        GROUP BY periods.period_start, periods.period_end, fact.customer_id
    '''


def _refresh_health(conn: Connection, schema_name: str) -> TableChange:
    schema = _quoted_schema(schema_name)
    conn.execute(f'''
        CREATE TEMP TABLE upload_youzan_health_weeks ON COMMIT DROP AS
        SELECT DISTINCT health.period_start, health.period_end
        FROM {schema}.customer_health_detail health
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
            FROM {schema}.customer_health_detail
        ) previous
        CROSS JOIN (
            SELECT MAX(period_start) AS latest_week
            FROM {schema}.customer_weekly_sales
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
    conn.execute(
        "CREATE UNIQUE INDEX ON upload_youzan_health_weeks (period_start, period_end)"
    )
    conn.execute(f'''
        CREATE TEMP TABLE upload_youzan_health_keys ON COMMIT DROP AS
        WITH customer_bounds AS (
            SELECT customer_id, MIN(period_start) AS first_week
            FROM {schema}.customer_weekly_sales
            GROUP BY customer_id
        ), global_bound AS (
            SELECT MAX(period_start) AS latest_week
            FROM {schema}.customer_weekly_sales
        )
        SELECT bounds.customer_id, weeks.period_start, weeks.period_end
        FROM customer_bounds bounds
        CROSS JOIN upload_youzan_health_weeks weeks
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
    conn.execute(
        "CREATE UNIQUE INDEX ON upload_youzan_health_keys "
        "(customer_id, period_start, period_end)"
    )
    expected = f'''
        WITH calendar AS (
            SELECT customer_id, period_start, period_end
            FROM upload_youzan_health_keys
        ), month_counts AS (
            SELECT calendar.customer_id, calendar.period_start, calendar.period_end,
                   COUNT(daily.transaction_date) FILTER (
                       WHERE DATE_TRUNC('month', calendar.period_start)::date
                                 = DATE_TRUNC('month', calendar.period_end)::date
                          OR daily.transaction_date
                                 < DATE_TRUNC('month', calendar.period_end)::date
                   )::numeric(10,2) AS month_one_count,
                   COUNT(daily.transaction_date) FILTER (
                       WHERE DATE_TRUNC('month', calendar.period_start)::date
                                 <> DATE_TRUNC('month', calendar.period_end)::date
                         AND daily.transaction_date
                                 >= DATE_TRUNC('month', calendar.period_end)::date
                   )::numeric(10,2) AS month_two_count
            FROM calendar
            LEFT JOIN {schema}.customer_daily_sales daily
              ON daily.customer_id = calendar.customer_id
             AND daily.transaction_date BETWEEN
                 DATE_TRUNC('month', calendar.period_start)::date
                 AND calendar.period_end
            GROUP BY calendar.customer_id, calendar.period_start, calendar.period_end
        ), counts AS (
            SELECT month_counts.*,
                   DATE_TRUNC('month', month_counts.period_start)::date AS month_period_start,
                   (DATE_TRUNC('month', month_counts.period_end)::date
                       + INTERVAL '1 month - 1 day')::date AS month_period_end,
                   COALESCE(weekly.weekly_purchase_count, 0)::integer AS week_purchase_count,
                   CASE
                       WHEN DATE_TRUNC('month', month_counts.period_start)::date
                            = DATE_TRUNC('month', month_counts.period_end)::date
                           THEN month_counts.month_one_count
                       ELSE ROUND((month_counts.month_one_count
                                 + month_counts.month_two_count) / 2.0, 2)::numeric(10,2)
                   END AS month_purchase_count
            FROM month_counts
            LEFT JOIN {schema}.customer_weekly_sales weekly
              ON weekly.customer_id = month_counts.customer_id
             AND weekly.period_start = month_counts.period_start
        ), sub_scores AS (
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
            FROM counts
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
        SELECT classified.customer_id, classified.period_start, classified.period_end,
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
    scope = '''EXISTS (
        SELECT 1 FROM upload_youzan_health_keys keys
        WHERE keys.customer_id = target.customer_id
          AND keys.period_start = target.period_start
          AND keys.period_end = target.period_end
    )'''
    return _sync(
        conn,
        schema_name,
        "customer_health_detail",
        ("customer_id", "period_start", "period_end"),
        (
            "week_period_start", "week_period_end", "month_period_start", "month_period_end",
            "week_purchase_count", "week_score", "month_purchase_count", "month_score",
            "customer_score", "customer_health_status", "state_instructions", "follow_up_action",
        ),
        expected,
        scope,
    )


def refresh_store_incremental(
    conn: Connection,
    schema_name: str,
    affected_dates: tuple[date, ...],
    customer_ids: tuple[str, ...] = (),
) -> list[TableChange]:
    if not affected_dates:
        return []
    _quoted_schema(schema_name)
    _prepare_scopes(conn, affected_dates, customer_ids)
    _prepare_fact(conn, schema_name)
    schema = _quoted_schema(schema_name)
    changes: list[TableChange] = []
    day_scope = "target.transaction_date IN (SELECT transaction_date FROM upload_youzan_dates)"

    changes.append(_sync(conn, schema_name, "daily_sales", ("transaction_date",), (
        "transaction_amount",
    ), '''
        SELECT fact.transaction_date,
               SUM(fact.transaction_amount)::numeric(18,2) AS transaction_amount
        FROM upload_youzan_fact fact
        JOIN upload_youzan_dates dates USING (transaction_date)
        WHERE fact.is_sale AND fact.transaction_amount IS NOT NULL
        GROUP BY fact.transaction_date
    ''', day_scope))
    changes.append(_sync(conn, schema_name, "daily_product_sales", (
        "transaction_date", "product_code",
    ), ("transaction_amount", "product_quantity"), '''
        SELECT fact.transaction_date, fact.product_code,
               SUM(fact.transaction_amount)::numeric(18,2) AS transaction_amount,
               SUM(fact.product_quantity)::numeric(18,4) AS product_quantity
        FROM upload_youzan_fact fact
        JOIN upload_youzan_dates dates USING (transaction_date)
        WHERE fact.is_sale AND fact.transaction_amount IS NOT NULL
          AND fact.product_quantity IS NOT NULL AND fact.product_code IS NOT NULL
        GROUP BY fact.transaction_date, fact.product_code
    ''', day_scope))
    changes.append(_sync(conn, schema_name, "daily_customer_sales", (
        "transaction_date", "customer_id",
    ), ("transaction_amount",), '''
        SELECT fact.transaction_date, fact.customer_id,
               SUM(fact.transaction_amount)::numeric(18,2) AS transaction_amount
        FROM upload_youzan_fact fact
        JOIN upload_youzan_dates dates USING (transaction_date)
        WHERE fact.is_sale AND fact.transaction_amount IS NOT NULL
          AND fact.customer_id IS NOT NULL
        GROUP BY fact.transaction_date, fact.customer_id
    ''', day_scope))

    for prefix, (grain, _) in GRAINS.items():
        scope = _period_scope(grain)
        changes.append(_sync(conn, schema_name, f"{prefix}_sales", (
            "period_start", "period_end",
        ), (f"{prefix}_transaction_amount",),
            _period_sales_expected(grain, prefix), scope))
        changes.append(_sync(conn, schema_name, f"{prefix}_refunds", (
            "period_start", "period_end",
        ), (f"{prefix}_refund_amount",),
            _period_refunds_expected(grain, prefix), scope))
        changes.append(_sync(conn, schema_name, f"{prefix}_product_sales", (
            "period_start", "period_end", "product_code",
        ), (f"{prefix}_transaction_amount", f"{prefix}_product_quantity"),
            _period_product_expected(grain, prefix), scope))
        changes.append(_sync(conn, schema_name, f"{prefix}_customer_sales", (
            "period_start", "period_end", "customer_id",
        ), (f"{prefix}_transaction_amount",),
            _period_customer_expected(grain, prefix), scope))

    conn.execute(f'''
        CREATE TEMP TABLE upload_youzan_daily_metric_dates ON COMMIT DROP AS
        SELECT DISTINCT current.transaction_date
        FROM {schema}.daily_sales current
        WHERE EXISTS (
            SELECT 1 FROM upload_youzan_dates changed
            WHERE current.transaction_date BETWEEN changed.transaction_date
                                               AND changed.transaction_date + 29
               OR current.transaction_date = (changed.transaction_date + INTERVAL '1 year')::date
        )
    ''')
    daily_metric_scope = (
        "target.transaction_date IN (SELECT transaction_date "
        "FROM upload_youzan_daily_metric_dates)"
    )
    changes.append(_sync(conn, schema_name, "daily_sales_metrics", (
        "transaction_date",
    ), (
        "transaction_amount", "year_over_year_rate",
        "rolling_7_day_transaction_amount", "rolling_30_day_transaction_amount",
    ), f'''
        SELECT current.transaction_date, current.transaction_amount,
               CASE WHEN previous.transaction_amount IS NULL OR previous.transaction_amount = 0 THEN 0.00
                    ELSE ROUND((current.transaction_amount - previous.transaction_amount)
                         / previous.transaction_amount * 100, 2) END::numeric(12,2) AS year_over_year_rate,
               (SELECT COALESCE(SUM(item.transaction_amount),0)::numeric(18,2)
                FROM {schema}.daily_sales item
                WHERE item.transaction_date BETWEEN current.transaction_date - 6 AND current.transaction_date)
                   AS rolling_7_day_transaction_amount,
               (SELECT COALESCE(SUM(item.transaction_amount),0)::numeric(18,2)
                FROM {schema}.daily_sales item
                WHERE item.transaction_date BETWEEN current.transaction_date - 29 AND current.transaction_date)
                   AS rolling_30_day_transaction_amount
        FROM {schema}.daily_sales current
        JOIN upload_youzan_daily_metric_dates dates USING (transaction_date)
        LEFT JOIN {schema}.daily_sales previous
          ON previous.transaction_date = (current.transaction_date - INTERVAL '1 year')::date
    ''', daily_metric_scope))

    for prefix, rate, interval, grain in (
        ("weekly", "week_over_week_rate", "7 days", "week"),
        ("monthly", "month_over_month_rate", "1 month", "month"),
    ):
        conn.execute(f'''
            CREATE TEMP TABLE upload_youzan_{prefix}_metric_periods ON COMMIT DROP AS
            SELECT sales.period_start, sales.period_end
            FROM {schema}.{prefix}_sales sales
            WHERE EXISTS (
                SELECT 1 FROM upload_youzan_periods changed
                WHERE changed.grain = '{grain}'
                  AND (sales.period_start = changed.period_start
                       OR sales.period_start = (changed.period_start + INTERVAL '{interval}')::date)
            )
        ''')
        metric_scope = f'''EXISTS (
            SELECT 1 FROM upload_youzan_{prefix}_metric_periods periods
            WHERE periods.period_start = target.period_start
              AND periods.period_end = target.period_end
        )'''
        amount = f"{prefix}_transaction_amount"
        changes.append(_sync(conn, schema_name, f"{prefix}_sales_metrics", (
            "period_start", "period_end",
        ), (amount, rate), f'''
            SELECT current.period_start, current.period_end, current.{amount},
                   CASE WHEN previous.{amount} IS NULL OR previous.{amount} = 0 THEN 0.00
                        ELSE ROUND((current.{amount} - previous.{amount})
                             / previous.{amount} * 100, 2) END::numeric(12,2) AS {rate}
            FROM {schema}.{prefix}_sales current
            JOIN upload_youzan_{prefix}_metric_periods periods
              USING (period_start, period_end)
            LEFT JOIN {schema}.{prefix}_sales previous
              ON previous.period_start = (current.period_start - INTERVAL '{interval}')::date
        ''', metric_scope))

    changes.append(_sync(conn, schema_name, "customer_daily_sales", (
        "customer_id", "transaction_date",
    ), ("transaction_amount",), f'''
        SELECT customer_id, transaction_date, transaction_amount
        FROM {schema}.daily_customer_sales
        WHERE transaction_date IN (SELECT transaction_date FROM upload_youzan_dates)
    ''', day_scope))
    conn.execute(f'''
        CREATE TEMP TABLE upload_youzan_customer_metric_keys ON COMMIT DROP AS
        SELECT DISTINCT current.customer_id, current.transaction_date
        FROM {schema}.customer_daily_sales current
        WHERE current.customer_id IN (SELECT customer_id FROM upload_youzan_customers)
          AND EXISTS (
              SELECT 1 FROM upload_youzan_dates changed
              WHERE current.transaction_date BETWEEN changed.transaction_date
                                                 AND changed.transaction_date + 29
          )
    ''')
    customer_metric_scope = '''EXISTS (
        SELECT 1 FROM upload_youzan_customer_metric_keys keys
        WHERE keys.customer_id = target.customer_id
          AND keys.transaction_date = target.transaction_date
    )'''
    changes.append(_sync(conn, schema_name, "customer_daily_sales_metrics", (
        "customer_id", "transaction_date",
    ), (
        "transaction_amount", "rolling_7_day_transaction_amount",
        "rolling_30_day_transaction_amount",
    ), f'''
        SELECT current.customer_id, current.transaction_date, current.transaction_amount,
               (SELECT COALESCE(SUM(item.transaction_amount),0)::numeric(18,2)
                FROM {schema}.customer_daily_sales item
                WHERE item.customer_id = current.customer_id
                  AND item.transaction_date BETWEEN current.transaction_date - 6 AND current.transaction_date)
                   AS rolling_7_day_transaction_amount,
               (SELECT COALESCE(SUM(item.transaction_amount),0)::numeric(18,2)
                FROM {schema}.customer_daily_sales item
                WHERE item.customer_id = current.customer_id
                  AND item.transaction_date BETWEEN current.transaction_date - 29 AND current.transaction_date)
                   AS rolling_30_day_transaction_amount
        FROM {schema}.customer_daily_sales current
        JOIN upload_youzan_customer_metric_keys keys USING (customer_id, transaction_date)
    ''', customer_metric_scope))

    for prefix, (grain, _) in GRAINS.items():
        scope = _period_scope(grain)
        changes.append(_sync(conn, schema_name, f"customer_{prefix}_sales", (
            "customer_id", "period_start", "period_end",
        ), (f"{prefix}_transaction_amount", f"{prefix}_purchase_count"), f'''
            SELECT fact.customer_id, periods.period_start, periods.period_end,
                   SUM(fact.transaction_amount)::numeric(18,2) AS {prefix}_transaction_amount,
                   COUNT(DISTINCT fact.transaction_date)::bigint AS {prefix}_purchase_count
            FROM upload_youzan_periods periods
            JOIN upload_youzan_fact fact
              ON fact.transaction_date BETWEEN periods.period_start AND periods.period_end
             AND fact.is_sale AND fact.customer_id IS NOT NULL
            WHERE periods.grain = '{grain}'
            GROUP BY fact.customer_id, periods.period_start, periods.period_end
        ''', scope))

    changes.append(_sync(conn, schema_name, "customer_daily_product_sales", (
        "customer_id", "transaction_date", "product_code",
    ), ("transaction_amount", "product_quantity"), '''
        SELECT fact.customer_id, fact.transaction_date, fact.product_code,
               SUM(fact.transaction_amount)::numeric(18,2) AS transaction_amount,
               SUM(fact.product_quantity)::numeric(18,4) AS product_quantity
        FROM upload_youzan_fact fact
        JOIN upload_youzan_dates dates USING (transaction_date)
        WHERE fact.is_sale AND fact.transaction_amount IS NOT NULL
          AND fact.product_quantity IS NOT NULL
          AND fact.customer_id IS NOT NULL AND fact.product_code IS NOT NULL
        GROUP BY fact.customer_id, fact.transaction_date, fact.product_code
    ''', day_scope))
    for prefix, grain in (
        ("monthly", "month"),
        ("quarterly", "quarter"),
        ("half_year", "half"),
    ):
        scope = _period_scope(grain)
        changes.append(_sync(conn, schema_name, f"customer_{prefix}_product_sales", (
            "customer_id", "period_start", "period_end", "product_code",
        ), (f"{prefix}_transaction_amount", f"{prefix}_product_quantity"), f'''
            SELECT fact.customer_id, periods.period_start, periods.period_end, fact.product_code,
                   SUM(fact.transaction_amount)::numeric(18,2) AS {prefix}_transaction_amount,
                   SUM(fact.product_quantity)::numeric(18,4) AS {prefix}_product_quantity
            FROM upload_youzan_periods periods
            JOIN upload_youzan_fact fact
              ON fact.transaction_date BETWEEN periods.period_start AND periods.period_end
             AND fact.is_sale AND fact.transaction_amount IS NOT NULL
             AND fact.product_quantity IS NOT NULL
             AND fact.customer_id IS NOT NULL AND fact.product_code IS NOT NULL
            WHERE periods.grain = '{grain}'
            GROUP BY fact.customer_id, periods.period_start, periods.period_end, fact.product_code
        ''', scope))

    changes.append(_refresh_health(conn, schema_name))
    if len(changes) != 33:
        raise ValueError(f"有赞店铺增量刷新表数异常：{len(changes)} != 33")
    return changes
