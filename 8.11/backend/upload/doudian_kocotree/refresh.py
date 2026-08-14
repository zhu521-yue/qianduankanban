from __future__ import annotations

from contextvars import ContextVar

from psycopg import Connection, sql

from upload.table_sync import TableChange, sync_table


SCHEMA = "doudianKocotree"
_ACTIVE_SCHEMA: ContextVar[str] = ContextVar("doudian_refresh_schema", default=SCHEMA)


def _schema_sql(statement: str) -> str:
    """Retarget the trusted Doudian refresh SQL to the active store schema."""
    schema_name = _ACTIVE_SCHEMA.get()
    quoted_schema = '"' + schema_name.replace('"', '""') + '"'
    return statement.replace(f'"{SCHEMA}"', quoted_schema)


def _period_start(column: str, grain: str) -> str:
    if grain == "week":
        return f"({column} - (EXTRACT(ISODOW FROM {column})::integer - 1))::date"
    if grain == "month":
        return f"DATE_TRUNC('month', {column})::date"
    if grain == "quarter":
        return f"""CASE
            WHEN EXTRACT(MONTH FROM {column})::integer BETWEEN 2 AND 4
                THEN MAKE_DATE(EXTRACT(YEAR FROM {column})::integer, 2, 1)
            WHEN EXTRACT(MONTH FROM {column})::integer BETWEEN 5 AND 7
                THEN MAKE_DATE(EXTRACT(YEAR FROM {column})::integer, 5, 1)
            WHEN EXTRACT(MONTH FROM {column})::integer BETWEEN 8 AND 10
                THEN MAKE_DATE(EXTRACT(YEAR FROM {column})::integer, 8, 1)
            WHEN EXTRACT(MONTH FROM {column})::integer >= 11
                THEN MAKE_DATE(EXTRACT(YEAR FROM {column})::integer, 11, 1)
            ELSE MAKE_DATE(EXTRACT(YEAR FROM {column})::integer - 1, 11, 1)
        END"""
    if grain == "half":
        return f"""CASE
            WHEN EXTRACT(MONTH FROM {column})::integer BETWEEN 2 AND 7
                THEN MAKE_DATE(EXTRACT(YEAR FROM {column})::integer, 2, 1)
            WHEN EXTRACT(MONTH FROM {column})::integer >= 8
                THEN MAKE_DATE(EXTRACT(YEAR FROM {column})::integer, 8, 1)
            ELSE MAKE_DATE(EXTRACT(YEAR FROM {column})::integer - 1, 8, 1)
        END"""
    raise ValueError(f"unsupported grain: {grain}")


def _period_end(start: str, grain: str) -> str:
    intervals = {"week": "7 days", "month": "1 month", "quarter": "3 months", "half": "6 months"}
    return f"({start} + INTERVAL '{intervals[grain]}' - INTERVAL '1 day')::date"


def _prepare_normalized_source(conn: Connection) -> None:
    if _ACTIVE_SCHEMA.get() in {"qijian", "muyinqijian"}:
        conn.execute(_schema_sql(r'''
            CREATE TEMP TABLE upload_dk_source ON COMMIT DROP AS
            WITH cleaned AS (
                SELECT
                    NULLIF(BTRIM(COALESCE("订单创建时间"::text, ''), E' \t\n\r'), '') AS order_time_text,
                    NULLIF(REGEXP_REPLACE(COALESCE("商品单价"::text, ''), '[,￥¥[:space:]]', '', 'g'), '') AS unit_price_text,
                    NULLIF(REGEXP_REPLACE(COALESCE("商品数量"::text, ''), '[,[:space:]]', '', 'g'), '') AS quantity_text,
                    NULLIF(REGEXP_REPLACE(COALESCE("商品已退款金额"::text, ''), '[,￥¥[:space:]]', '', 'g'), '') AS refund_text,
                    "规格编码"::text AS product_code_raw,
                    BTRIM(COALESCE("买家昵称"::text, ''), E' \t\n\r') AS customer_id_text,
                    BTRIM(COALESCE("销售渠道"::text, ''), E' \t\n\r') AS sales_channel,
                    BTRIM(COALESCE("订单状态"::text, ''), E' \t\n\r') AS order_status
                FROM "doudianKocotree".raw_data
            ), typed AS (
                SELECT
                    CASE WHEN pg_input_is_valid(order_time_text, 'timestamp')
                        THEN order_time_text::timestamp::date END AS transaction_date,
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
            )
            SELECT
                transaction_date,
                ROUND(transaction_amount, 2)::numeric(18,2) AS transaction_amount,
                ROUND(refund_amount, 2)::numeric(18,2) AS refund_amount,
                product_quantity::numeric(18,4) AS product_quantity,
                CASE WHEN BTRIM(COALESCE(product_code_raw, ''), E' \t\n\r') NOT IN ('', '-')
                    THEN product_code_raw END AS product_code,
                CASE WHEN sales_channel = '网店'
                           AND customer_id_text NOT IN ('', '-', '0', '0.0')
                    THEN customer_id_text END AS customer_id,
                order_status IN ('已完成', '已关闭', '已发货') AS is_sale,
                refund_amount > 0 AS is_refund
            FROM typed
        '''))
        return
    if _ACTIVE_SCHEMA.get() == "weidian":
        conn.execute(r'''
            CREATE TEMP TABLE upload_dk_source ON COMMIT DROP AS
            WITH cleaned AS (
                SELECT
                    NULLIF(BTRIM(COALESCE("支付时间"::text, ''), E' \t\n\r'), '') AS payment_text,
                    NULLIF(REGEXP_REPLACE(COALESCE("订单实际收款金额"::text, ''), '[,￥¥[:space:]]', '', 'g'), '') AS amount_text,
                    NULLIF(REGEXP_REPLACE(COALESCE("商品已退款金额"::text, ''), '[,￥¥[:space:]]', '', 'g'), '') AS refund_text,
                    NULLIF(REGEXP_REPLACE(COALESCE("商品数量"::text, ''), '[,[:space:]]', '', 'g'), '') AS quantity_text,
                    NULLIF(BTRIM(COALESCE("SKU编码(自定义)"::text, ''), E' \t\n\r'), '') AS product_code_text,
                    REGEXP_REPLACE(BTRIM(COALESCE("带货ID"::text, ''), E' \t\n\r'), '\.0+$', '') AS customer_id_text,
                    BTRIM(COALESCE("订单状态"::text, ''), E' \t\n\r') AS order_status,
                    BTRIM(COALESCE("商品发货"::text, ''), E' \t\n\r') AS shipping_status
                FROM weidian.raw_data
            )
            SELECT
                CASE WHEN pg_input_is_valid(payment_text, 'timestamp')
                    THEN payment_text::timestamp::date END AS transaction_date,
                CASE WHEN pg_input_is_valid(amount_text, 'numeric')
                    THEN amount_text::numeric(18,2) END AS transaction_amount,
                CASE WHEN pg_input_is_valid(refund_text, 'numeric')
                    THEN refund_text::numeric(18,2) END AS refund_amount,
                CASE WHEN pg_input_is_valid(quantity_text, 'numeric')
                    THEN quantity_text::numeric::bigint END AS product_quantity,
                product_code_text AS product_code,
                CASE WHEN customer_id_text NOT IN ('', '-', '0', '0.0')
                    THEN customer_id_text END AS customer_id,
                order_status IN ('已完成', '已发货') AND shipping_status = '已发货' AS is_sale,
                CASE WHEN pg_input_is_valid(refund_text, 'numeric')
                    THEN refund_text::numeric > 0 ELSE FALSE END AS is_refund
            FROM cleaned
        ''')
        return
    if _ACTIVE_SCHEMA.get() == "kuaishouxiaodian":
        conn.execute(r'''
            CREATE TEMP TABLE upload_dk_source ON COMMIT DROP AS
            WITH cleaned AS (
                SELECT
                    NULLIF(BTRIM(COALESCE("订单创建时间"::text, ''), E' \t\n\r'), '') AS order_time_text,
                    NULLIF(REGEXP_REPLACE(COALESCE("实付款"::text, ''), '[,￥¥[:space:]]', '', 'g'), '') AS amount_text,
                    NULLIF(REGEXP_REPLACE(COALESCE("成交数量"::text, ''), '[,[:space:]]', '', 'g'), '') AS quantity_text,
                    NULLIF(BTRIM(COALESCE("SKU编码"::text, ''), E' \t\n\r'), '') AS product_code_text,
                    REGEXP_REPLACE(BTRIM(COALESCE("CPS达人ID"::text, ''), E' \t\n\r'), '\.0+$', '') AS cps_id,
                    REGEXP_REPLACE(BTRIM(COALESCE("团长ID"::text, ''), E' \t\n\r'), '\.0+$', '') AS leader_id,
                    REGEXP_REPLACE(BTRIM(COALESCE("快赚客ID"::text, ''), E' \t\n\r'), '\.0+$', '') AS quick_id,
                    BTRIM(COALESCE("订单状态"::text, ''), E' \t\n\r') AS order_status,
                    BTRIM(COALESCE("渠道"::text, ''), E' \t\n\r') AS channel
                FROM kuaishouxiaodian.raw_data
            )
            SELECT
                CASE WHEN pg_input_is_valid(order_time_text, 'timestamp')
                    THEN order_time_text::timestamp::date END AS transaction_date,
                CASE WHEN pg_input_is_valid(amount_text, 'numeric')
                    THEN amount_text::numeric(18,2) END AS transaction_amount,
                NULL::numeric(18,2) AS refund_amount,
                CASE WHEN pg_input_is_valid(quantity_text, 'numeric')
                    THEN quantity_text::numeric::bigint END AS product_quantity,
                CASE WHEN product_code_text IS NOT NULL AND product_code_text <> '-'
                    THEN product_code_text END AS product_code,
                CASE WHEN channel <> '分销' THEN NULL
                     WHEN cps_id NOT IN ('', '-', '0', '0.0') THEN cps_id
                     WHEN leader_id NOT IN ('', '-', '0', '0.0') THEN leader_id
                     WHEN quick_id NOT IN ('', '-', '0', '0.0') THEN quick_id
                END AS customer_id,
                order_status IN ('交易成功', '已发货', '已收货') AS is_sale,
                FALSE AS is_refund
            FROM cleaned
        ''')
        return
    if _ACTIVE_SCHEMA.get() == "alibaba":
        conn.execute(r'''
            CREATE TEMP TABLE upload_dk_source ON COMMIT DROP AS
            WITH cleaned AS (
                SELECT
                    NULLIF(BTRIM(COALESCE("付款日期"::text, ''), E' \t\n\r'), '') AS payment_text,
                    NULLIF(REGEXP_REPLACE(COALESCE("实发金额"::text, ''), '[,￥¥[:space:]]', '', 'g'), '') AS shipped_amount_text,
                    NULLIF(REGEXP_REPLACE(COALESCE("实退金额"::text, ''), '[,￥¥[:space:]]', '', 'g'), '') AS refund_amount_text,
                    NULLIF(REGEXP_REPLACE(COALESCE("实发数量"::text, ''), '[,[:space:]]', '', 'g'), '') AS shipped_quantity_text,
                    NULLIF(REGEXP_REPLACE(COALESCE("实退数量"::text, ''), '[,[:space:]]', '', 'g'), '') AS refund_quantity_text,
                    NULLIF(BTRIM(COALESCE("商品编码"::text, ''), E' \t\n\r'), '') AS product_code_text,
                    REGEXP_REPLACE(BTRIM(COALESCE("买家ID"::text, ''), E' \t\n\r'), '\.0+$', '') AS customer_id_text,
                    BTRIM(COALESCE("订单状态"::text, ''), E' \t\n\r') AS order_status
                FROM alibaba.raw_data
            ), typed AS (
                SELECT
                    CASE WHEN pg_input_is_valid(payment_text, 'timestamp')
                        THEN payment_text::timestamp::date END AS transaction_date,
                    CASE WHEN pg_input_is_valid(shipped_amount_text, 'numeric')
                        THEN shipped_amount_text::numeric ELSE 0 END AS shipped_amount,
                    CASE WHEN pg_input_is_valid(refund_amount_text, 'numeric')
                        THEN refund_amount_text::numeric ELSE 0 END AS refund_amount,
                    CASE WHEN pg_input_is_valid(shipped_quantity_text, 'numeric')
                        THEN shipped_quantity_text::numeric ELSE 0 END AS shipped_quantity,
                    CASE WHEN pg_input_is_valid(refund_quantity_text, 'numeric')
                        THEN refund_quantity_text::numeric ELSE 0 END AS refund_quantity,
                    product_code_text,
                    customer_id_text,
                    order_status
                FROM cleaned
            )
            SELECT
                transaction_date,
                ROUND(shipped_amount - refund_amount, 2)::numeric(18,2) AS transaction_amount,
                ROUND(refund_amount, 2)::numeric(18,2) AS refund_amount,
                (shipped_quantity - refund_quantity)::numeric(18,4) AS product_quantity,
                CASE WHEN product_code_text IS NOT NULL AND product_code_text <> '-'
                    THEN product_code_text END AS product_code,
                CASE WHEN customer_id_text NOT IN ('', '-', '0', '0.0')
                    THEN customer_id_text END AS customer_id,
                order_status = '已发货' AS is_sale,
                refund_amount > 0 AS is_refund
            FROM typed
        ''')
        return
    conn.execute(
        _schema_sql(r'''
        CREATE TEMP TABLE upload_dk_source ON COMMIT DROP AS
        WITH cleaned AS (
            SELECT
                NULLIF(BTRIM("支付完成时间", E' \t\n\r'), '') AS payment_text,
                NULLIF(REGEXP_REPLACE(COALESCE("订单应付金额", ''), '[,￥¥[:space:]]', '', 'g'), '') AS amount_text,
                NULLIF(REGEXP_REPLACE(COALESCE("商品数量", ''), '[,[:space:]]', '', 'g'), '') AS quantity_text,
                NULLIF(BTRIM("商家编码", E' \t\n\r'), '') AS product_code_text,
                REGEXP_REPLACE(BTRIM(COALESCE("达人ID", ''), E' \t\n\r'), '\.0+$', '') AS customer_id_text,
                BTRIM(COALESCE("订单状态", ''), E' \t\n\r') AS order_status,
                BTRIM(COALESCE("售后状态", ''), E' \t\n\r') AS refund_status,
                BTRIM(COALESCE("流量来源", ''), E' \t\n\r') AS traffic_source
            FROM "doudianKocotree".raw_data
        )
        SELECT
            CASE WHEN pg_input_is_valid(payment_text, 'timestamp')
                THEN payment_text::timestamp::date END AS transaction_date,
            CASE WHEN pg_input_is_valid(amount_text, 'numeric')
                THEN amount_text::numeric(18,2) END AS transaction_amount,
            CASE WHEN pg_input_is_valid(amount_text, 'numeric')
                THEN amount_text::numeric(18,2) END AS refund_amount,
            CASE WHEN pg_input_is_valid(quantity_text, 'numeric')
                THEN quantity_text::numeric::bigint END AS product_quantity,
            CASE WHEN product_code_text IS NOT NULL AND product_code_text <> '-'
                THEN product_code_text END AS product_code,
            CASE WHEN traffic_source = '精选联盟'
                      AND customer_id_text NOT IN ('', '-', '0', '0.0')
                THEN customer_id_text END AS customer_id,
            order_status IN ('已完成', '已发货', '待发货') AS is_sale,
            refund_status NOT IN ('', '-', '换货成功', '换货待收货', '补寄成功') AS is_refund
        FROM cleaned
        ''')
    )


def _sync(
    conn: Connection,
    table: str,
    keys: tuple[str, ...],
    values: tuple[str, ...],
    select: str,
) -> TableChange:
    return sync_table(
        conn,
        schema_name=_ACTIVE_SCHEMA.get(),
        table_name=table,
        key_columns=keys,
        value_columns=values,
        expected_select=_schema_sql(select),
    )


def refresh_store_for_schema(
    conn: Connection,
    schema_name: str,
    affected_customer_ids: tuple[str, ...] = (),
) -> list[TableChange]:
    """Run the shared Doudian store refresh against one configured schema."""
    token = _ACTIVE_SCHEMA.set(schema_name)
    try:
        return refresh_store(conn, affected_customer_ids)
    finally:
        _ACTIVE_SCHEMA.reset(token)


def _simple_period_select(
    source_table: str,
    date_column: str,
    dimension_columns: tuple[str, ...],
    amount_column: str,
    quantity_column: str | None,
    grain: str,
    amount_alias: str,
    quantity_alias: str | None,
) -> str:
    start = _period_start(date_column, grain)
    end = _period_end("period_start", grain)
    dimensions = ", ".join(dimension_columns)
    dimension_select = f", {dimensions}" if dimensions else ""
    dimension_group = f", {dimensions}" if dimensions else ""
    quantity_type = (
        "numeric(18,4)"
        if _ACTIVE_SCHEMA.get() in {"alibaba", "qijian", "muyinqijian"}
        else "bigint"
    )
    quantity = (
        f", SUM({quantity_column})::{quantity_type} AS {quantity_alias}"
        if quantity_column and quantity_alias
        else ""
    )
    return f"""
        SELECT period_start, {end} AS period_end{dimension_select},
               SUM({amount_column})::numeric(18,2) AS {amount_alias}{quantity}
        FROM (
            SELECT {start} AS period_start{dimension_select}, {amount_column}
                   {f', {quantity_column}' if quantity_column else ''}
            FROM "{SCHEMA}".{source_table}
        ) source_rows
        GROUP BY period_start{dimension_group}
    """


def refresh_store(
    conn: Connection,
    affected_customer_ids: tuple[str, ...] = (),
) -> list[TableChange]:
    _prepare_normalized_source(conn)
    changes: list[TableChange] = []
    product_quantity_type = (
        "numeric(18,4)"
        if _ACTIVE_SCHEMA.get() in {"alibaba", "qijian", "muyinqijian"}
        else "bigint"
    )

    changes.append(_sync(conn, "daily_sales", ("transaction_date",), ("transaction_amount",), '''
        SELECT transaction_date, SUM(transaction_amount)::numeric(18,2) AS transaction_amount
        FROM upload_dk_source
        WHERE is_sale AND transaction_date IS NOT NULL AND transaction_amount IS NOT NULL
        GROUP BY transaction_date
    '''))
    changes.append(_sync(conn, "daily_product_sales", ("transaction_date", "product_code"), ("transaction_amount", "product_quantity"), f'''
        SELECT transaction_date, product_code,
               SUM(transaction_amount)::numeric(18,2) AS transaction_amount,
               SUM(product_quantity)::{product_quantity_type} AS product_quantity
        FROM upload_dk_source
        WHERE is_sale AND transaction_date IS NOT NULL AND transaction_amount IS NOT NULL
          AND product_quantity IS NOT NULL AND product_code IS NOT NULL
        GROUP BY transaction_date, product_code
    '''))
    changes.append(_sync(conn, "daily_customer_sales", ("transaction_date", "customer_id"), ("transaction_amount",), '''
        SELECT transaction_date, customer_id,
               SUM(transaction_amount)::numeric(18,2) AS transaction_amount
        FROM upload_dk_source
        WHERE is_sale AND transaction_date IS NOT NULL AND transaction_amount IS NOT NULL
          AND customer_id IS NOT NULL
        GROUP BY transaction_date, customer_id
    '''))

    for grain, prefix in (("week", "weekly"), ("month", "monthly"), ("quarter", "quarterly"), ("half", "half_year")):
        changes.append(_sync(
            conn,
            f"{prefix}_sales",
            ("period_start", "period_end"),
            (f"{prefix}_transaction_amount",),
            _simple_period_select(
                "daily_sales", "transaction_date", (), "transaction_amount", None,
                grain, f"{prefix}_transaction_amount", None,
            ),
        ))
        start = _period_start("transaction_date", grain)
        end = _period_end("period_start", grain)
        if _ACTIVE_SCHEMA.get() != "kuaishouxiaodian":
            changes.append(_sync(conn, f"{prefix}_refunds", ("period_start", "period_end"), (f"{prefix}_refund_amount",), f'''
                SELECT period_start, {end} AS period_end,
                       SUM(refund_amount)::numeric(18,2) AS {prefix}_refund_amount
                FROM (
                    SELECT {start} AS period_start, refund_amount
                    FROM upload_dk_source
                    WHERE is_refund AND transaction_date IS NOT NULL AND refund_amount IS NOT NULL
                ) source_rows
                GROUP BY period_start
            '''))
        changes.append(_sync(
            conn,
            f"{prefix}_product_sales",
            ("period_start", "period_end", "product_code"),
            (f"{prefix}_transaction_amount", f"{prefix}_product_quantity"),
            _simple_period_select(
                "daily_product_sales", "transaction_date", ("product_code",),
                "transaction_amount", "product_quantity", grain,
                f"{prefix}_transaction_amount", f"{prefix}_product_quantity",
            ),
        ))
        changes.append(_sync(
            conn,
            f"{prefix}_customer_sales",
            ("period_start", "period_end", "customer_id"),
            (f"{prefix}_transaction_amount",),
            _simple_period_select(
                "daily_customer_sales", "transaction_date", ("customer_id",),
                "transaction_amount", None, grain,
                f"{prefix}_transaction_amount", None,
            ),
        ))

    rate_scale = 6 if _ACTIVE_SCHEMA.get() == "weidian" else 2
    daily_rate_factor = "" if _ACTIVE_SCHEMA.get() == "weidian" else "* 100"
    period_rate_factor = (
        "" if _ACTIVE_SCHEMA.get() in {"weidian", "kuaishouxiaodian"} else "* 100"
    )
    changes.append(_sync(conn, "daily_sales_metrics", ("transaction_date",), (
        "transaction_amount", "year_over_year_rate",
        "rolling_7_day_transaction_amount", "rolling_30_day_transaction_amount",
    ), f'''
        SELECT current.transaction_date, current.transaction_amount,
               CASE WHEN previous.transaction_amount IS NULL OR previous.transaction_amount = 0 THEN 0.00
                    ELSE ROUND((current.transaction_amount - previous.transaction_amount)
                         / previous.transaction_amount {daily_rate_factor}, {rate_scale}) END::numeric(12,{rate_scale}) AS year_over_year_rate,
               (SELECT COALESCE(SUM(d.transaction_amount), 0)::numeric(18,2)
                FROM "doudianKocotree".daily_sales d
                WHERE d.transaction_date BETWEEN current.transaction_date - 6 AND current.transaction_date)
                    AS rolling_7_day_transaction_amount,
               (SELECT COALESCE(SUM(d.transaction_amount), 0)::numeric(18,2)
                FROM "doudianKocotree".daily_sales d
                WHERE d.transaction_date BETWEEN current.transaction_date - 29 AND current.transaction_date)
                    AS rolling_30_day_transaction_amount
        FROM "doudianKocotree".daily_sales current
        LEFT JOIN "doudianKocotree".daily_sales previous
          ON previous.transaction_date = (current.transaction_date - INTERVAL '1 year')::date
    '''))
    changes.append(_sync(conn, "weekly_sales_metrics", ("period_start", "period_end"), (
        "weekly_transaction_amount", "week_over_week_rate",
    ), f'''
        SELECT current.period_start, current.period_end, current.weekly_transaction_amount,
               CASE WHEN previous.weekly_transaction_amount IS NULL OR previous.weekly_transaction_amount = 0 THEN 0.00
                    ELSE ROUND((current.weekly_transaction_amount - previous.weekly_transaction_amount)
                         / previous.weekly_transaction_amount {period_rate_factor}, {rate_scale}) END::numeric(12,{rate_scale}) AS week_over_week_rate
        FROM "doudianKocotree".weekly_sales current
        LEFT JOIN "doudianKocotree".weekly_sales previous
          ON previous.period_start = current.period_start - 7
    '''))
    changes.append(_sync(conn, "monthly_sales_metrics", ("period_start", "period_end"), (
        "monthly_transaction_amount", "month_over_month_rate",
    ), f'''
        SELECT current.period_start, current.period_end, current.monthly_transaction_amount,
               CASE WHEN previous.monthly_transaction_amount IS NULL OR previous.monthly_transaction_amount = 0 THEN 0.00
                    ELSE ROUND((current.monthly_transaction_amount - previous.monthly_transaction_amount)
                         / previous.monthly_transaction_amount {period_rate_factor}, {rate_scale}) END::numeric(12,{rate_scale}) AS month_over_month_rate
        FROM "doudianKocotree".monthly_sales current
        LEFT JOIN "doudianKocotree".monthly_sales previous
          ON previous.period_start = (current.period_start - INTERVAL '1 month')::date
    '''))

    changes.append(_sync(conn, "customer_daily_sales", ("customer_id", "transaction_date"), ("transaction_amount",), '''
        SELECT customer_id, transaction_date, transaction_amount
        FROM "doudianKocotree".daily_customer_sales
    '''))
    changes.append(_sync(conn, "customer_daily_sales_metrics", ("customer_id", "transaction_date"), (
        "transaction_amount", "rolling_7_day_transaction_amount", "rolling_30_day_transaction_amount",
    ), '''
        SELECT current.customer_id, current.transaction_date, current.transaction_amount,
               (SELECT COALESCE(SUM(d.transaction_amount), 0)::numeric(18,2)
                FROM "doudianKocotree".customer_daily_sales d
                WHERE d.customer_id = current.customer_id
                  AND d.transaction_date BETWEEN current.transaction_date - 6 AND current.transaction_date)
                    AS rolling_7_day_transaction_amount,
               (SELECT COALESCE(SUM(d.transaction_amount), 0)::numeric(18,2)
                FROM "doudianKocotree".customer_daily_sales d
                WHERE d.customer_id = current.customer_id
                  AND d.transaction_date BETWEEN current.transaction_date - 29 AND current.transaction_date)
                    AS rolling_30_day_transaction_amount
        FROM "doudianKocotree".customer_daily_sales current
    '''))

    for grain, prefix in (("week", "weekly"), ("month", "monthly"), ("quarter", "quarterly"), ("half", "half_year")):
        start = _period_start("transaction_date", grain)
        end = _period_end("period_start", grain)
        changes.append(_sync(conn, f"customer_{prefix}_sales", ("customer_id", "period_start", "period_end"), (
            f"{prefix}_transaction_amount", f"{prefix}_purchase_count",
        ), f'''
            SELECT customer_id, period_start, {end} AS period_end,
                   SUM(transaction_amount)::numeric(18,2) AS {prefix}_transaction_amount,
                   COUNT(*)::bigint AS {prefix}_purchase_count
            FROM (
                SELECT customer_id, {start} AS period_start, transaction_amount
                FROM "doudianKocotree".customer_daily_sales
            ) source_rows
            GROUP BY customer_id, period_start
        '''))

    changes.append(_sync(conn, "customer_daily_product_sales", ("customer_id", "transaction_date", "product_code"), (
        "transaction_amount", "product_quantity",
    ), f'''
        SELECT customer_id, transaction_date, product_code,
               SUM(transaction_amount)::numeric(18,2) AS transaction_amount,
               SUM(product_quantity)::{product_quantity_type} AS product_quantity
        FROM upload_dk_source
        WHERE is_sale AND transaction_date IS NOT NULL AND transaction_amount IS NOT NULL
          AND product_quantity IS NOT NULL AND customer_id IS NOT NULL AND product_code IS NOT NULL
        GROUP BY customer_id, transaction_date, product_code
    '''))
    for grain, prefix in (("month", "monthly"), ("quarter", "quarterly"), ("half", "half_year")):
        start = _period_start("transaction_date", grain)
        end = _period_end("period_start", grain)
        changes.append(_sync(conn, f"customer_{prefix}_product_sales", (
            "customer_id", "period_start", "period_end", "product_code",
        ), (f"{prefix}_transaction_amount", f"{prefix}_product_quantity"), f'''
            SELECT customer_id, period_start, {end} AS period_end, product_code,
                   SUM(transaction_amount)::numeric(18,2) AS {prefix}_transaction_amount,
                   SUM(product_quantity)::{product_quantity_type} AS {prefix}_product_quantity
            FROM (
                SELECT customer_id, {start} AS period_start, product_code,
                       transaction_amount, product_quantity
                FROM "doudianKocotree".customer_daily_product_sales
            ) source_rows
            GROUP BY customer_id, period_start, product_code
        '''))

    if _ACTIVE_SCHEMA.get() in {"qijian", "muyinqijian"}:
        changes.append(_sync(conn, "customer_health_detail", (
            "customer_id", "period_start", "period_end",
        ), (
            "week_period_start", "week_period_end", "month_period_start", "month_period_end",
            "week_purchase_count", "week_score", "month_purchase_count", "month_score",
            "customer_score", "customer_health_status", "state_instructions", "follow_up_action",
        ), '''
            WITH global_bound AS (
                SELECT MAX(period_start) AS latest_week
                FROM "doudianKocotree".customer_weekly_sales
            ), customer_bounds AS (
                SELECT customer_id, MIN(period_start) AS first_week
                FROM "doudianKocotree".customer_weekly_sales
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
                LEFT JOIN "doudianKocotree".customer_daily_sales daily
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
                LEFT JOIN "doudianKocotree".customer_weekly_sales weekly
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
            SELECT classified.customer_id,
                   classified.period_start,
                   classified.period_end,
                   classified.period_start AS week_period_start,
                   classified.period_end AS week_period_end,
                   classified.month_period_start,
                   classified.month_period_end,
                   classified.week_purchase_count,
                   classified.week_score,
                   classified.month_purchase_count,
                   classified.month_score,
                   classified.customer_score,
                   classified.customer_health_status,
                   rules.state_instructions,
                   rules.follow_up_action
            FROM classified
            LEFT JOIN public.private_customer_status_action rules
              ON rules.customer_health_status = classified.customer_health_status
        '''))
        return changes

    if _ACTIVE_SCHEMA.get() == "alibaba":
        conn.execute('''
            CREATE TEMP TABLE upload_alibaba_health_customers (
                customer_id text PRIMARY KEY
            ) ON COMMIT DROP
        ''')
        if affected_customer_ids:
            conn.execute(
                "INSERT INTO upload_alibaba_health_customers (customer_id) "
                "SELECT DISTINCT UNNEST(%s::text[])",
                (list(affected_customer_ids),),
            )
        conn.execute('''
            CREATE TEMP TABLE upload_alibaba_health_meta ON COMMIT DROP AS
            SELECT MAX(period_start) AS previous_latest_week
            FROM alibaba.customer_health_detail
        ''')
        health_select = (
            "week_period_start", "week_period_end", "month_period_start", "month_period_end",
            "week_purchase_count", "week_score", "month_purchase_count", "month_score",
            "customer_score", "customer_health_status", "state_instructions", "follow_up_action",
        )
        health_expected = '''
            WITH global_bound AS (
                SELECT MAX(period_start) AS latest_week
                FROM alibaba.customer_weekly_sales
            ), customer_bounds AS (
                SELECT customer_id, MIN(period_start) AS first_week
                FROM alibaba.customer_weekly_sales
                GROUP BY customer_id
            ), changed_customer_calendar AS (
                SELECT bounds.customer_id,
                       weeks.week_start::date AS period_start,
                       (weeks.week_start::date + 6) AS period_end
                FROM customer_bounds bounds
                JOIN upload_alibaba_health_customers changed
                  ON changed.customer_id = bounds.customer_id
                CROSS JOIN global_bound global
                CROSS JOIN LATERAL generate_series(
                    bounds.first_week,
                    global.latest_week,
                    INTERVAL '7 days'
                ) AS weeks(week_start)
            ), new_global_weeks AS (
                SELECT bounds.customer_id,
                       weeks.week_start::date AS period_start,
                       (weeks.week_start::date + 6) AS period_end
                FROM customer_bounds bounds
                CROSS JOIN global_bound global
                CROSS JOIN upload_alibaba_health_meta meta
                CROSS JOIN LATERAL generate_series(
                    GREATEST(
                        bounds.first_week,
                        COALESCE(meta.previous_latest_week + 7, bounds.first_week)
                    ),
                    global.latest_week,
                    INTERVAL '7 days'
                ) AS weeks(week_start)
                WHERE meta.previous_latest_week IS NULL
                   OR global.latest_week > meta.previous_latest_week
            ), calendar AS (
                SELECT * FROM changed_customer_calendar
                UNION
                SELECT * FROM new_global_weeks
            ), counts AS (
                SELECT calendar.*,
                       DATE_TRUNC('month', calendar.period_start)::date AS month_period_start,
                       (DATE_TRUNC('month', calendar.period_end)::date
                           + INTERVAL '1 month - 1 day')::date AS month_period_end,
                       COALESCE(weekly.weekly_purchase_count, 0)::integer AS week_purchase_count,
                       CASE
                           WHEN DATE_TRUNC('month', calendar.period_start)::date
                                = DATE_TRUNC('month', calendar.period_end)::date
                               THEN COALESCE(month_one.monthly_purchase_count, 0)::numeric(10,2)
                           ELSE ROUND((COALESCE(month_one.monthly_purchase_count, 0)
                                     + COALESCE(month_two.monthly_purchase_count, 0)) / 2.0, 2)::numeric(10,2)
                       END AS month_purchase_count
                FROM calendar
                LEFT JOIN alibaba.customer_weekly_sales weekly
                  ON weekly.customer_id = calendar.customer_id
                 AND weekly.period_start = calendar.period_start
                LEFT JOIN alibaba.customer_monthly_sales month_one
                  ON month_one.customer_id = calendar.customer_id
                 AND month_one.period_start = DATE_TRUNC('month', calendar.period_start)::date
                LEFT JOIN alibaba.customer_monthly_sales month_two
                  ON month_two.customer_id = calendar.customer_id
                 AND month_two.period_start = DATE_TRUNC('month', calendar.period_end)::date
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
            SELECT classified.customer_id,
                   classified.period_start,
                   classified.period_end,
                   classified.period_start AS week_period_start,
                   classified.period_end AS week_period_end,
                   classified.month_period_start,
                   classified.month_period_end,
                   classified.week_purchase_count,
                   classified.week_score,
                   classified.month_purchase_count,
                   classified.month_score,
                   classified.customer_score,
                   classified.customer_health_status,
                   rules.state_instructions,
                   rules.follow_up_action
            FROM classified
            LEFT JOIN public.distribution_customer_status_action rules
              ON rules.customer_health_status = classified.customer_health_status
        '''
        health_change = sync_table(
            conn,
            schema_name="alibaba",
            table_name="customer_health_detail",
            key_columns=("customer_id", "period_start", "period_end"),
            value_columns=health_select,
            expected_select=health_expected,
            delete_scope_sql='''
                target.customer_id IN (
                    SELECT customer_id FROM upload_alibaba_health_customers
                )
                OR target.period_start > COALESCE(
                    (SELECT previous_latest_week FROM upload_alibaba_health_meta),
                    DATE '-infinity'
                )
            ''',
        )
        changes.append(health_change)
        return changes

    changes.append(_sync(conn, "customer_health_detail", ("customer_id", "period_start", "period_end"), (
        "half_year_purchase_count", "half_year_purchase_amount", "customer_health_score",
        "customer_health_status", "state_instructions", "follow_up_action",
    ), '''
        WITH components AS (
            SELECT source.*,
                   CASE WHEN half_year_purchase_count >= 4 THEN 100.00
                        WHEN half_year_purchase_count = 3 THEN 80.00
                        WHEN half_year_purchase_count BETWEEN 1 AND 2 THEN 60.00
                        ELSE 20.00 END::numeric(5,2) AS count_score,
                   CASE WHEN half_year_transaction_amount >= 550000 THEN 100.00
                        WHEN half_year_transaction_amount >= 400000 THEN 80.00
                        WHEN half_year_transaction_amount >= 200000 THEN 70.00
                        WHEN half_year_transaction_amount >= 100000 THEN 60.00
                        WHEN half_year_transaction_amount >= 50000 THEN 40.00
                        WHEN half_year_transaction_amount >= 10000 THEN 20.00
                        ELSE 10.00 END::numeric(5,2) AS amount_score
            FROM "doudianKocotree".customer_half_year_sales source
        ), scored AS (
            SELECT *, ROUND(count_score * 0.40 + amount_score * 0.60, 2)::numeric(5,2) AS score
            FROM components
        ), classified AS (
            SELECT *, CASE WHEN score >= 90 THEN '高活跃' WHEN score >= 80 THEN '活跃'
                           WHEN score >= 70 THEN '稳定' WHEN score >= 50 THEN '观察'
                           WHEN score >= 40 THEN '风险' WHEN score >= 20 THEN '流失预警'
                           ELSE '流失' END AS status
            FROM scored
        )
        SELECT customer_id, period_start, period_end, half_year_purchase_count,
               half_year_transaction_amount AS half_year_purchase_amount,
               score AS customer_health_score, status AS customer_health_status,
               rules.state_instructions, rules.follow_up_action
        FROM classified
        LEFT JOIN public.talent_customer_status_action rules
          ON rules.customer_health_status = classified.status
    '''))
    return changes
