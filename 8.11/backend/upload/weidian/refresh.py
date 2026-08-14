from __future__ import annotations

from psycopg import Connection

from upload.doudian_kocotree.refresh import (
    _period_end,
    _period_start,
    refresh_store_for_schema,
)
from upload.table_sync import TableChange, sync_table


SCHEMA = "weidian"


def _prepare_presale_source(conn: Connection) -> None:
    conn.execute(r'''
        CREATE TEMP TABLE upload_weidian_presale_source ON COMMIT DROP AS
        WITH cleaned AS (
            SELECT
                NULLIF(BTRIM(COALESCE("订单下单时间"::text, ''), E' \t\n\r'), '') AS order_time_text,
                NULLIF(REGEXP_REPLACE(COALESCE("订单实际收款金额"::text, ''), '[,￥¥[:space:]]', '', 'g'), '') AS amount_text,
                NULLIF(REGEXP_REPLACE(COALESCE("商品数量"::text, ''), '[,[:space:]]', '', 'g'), '') AS quantity_text,
                NULLIF(BTRIM(COALESCE("SKU编码(自定义)"::text, ''), E' \t\n\r'), '') AS product_code,
                BTRIM(COALESCE("是否预售"::text, ''), E' \t\n\r') AS presale_status
            FROM weidian.raw_data
        )
        SELECT
            CASE WHEN pg_input_is_valid(order_time_text, 'timestamp')
                THEN order_time_text::timestamp::date END AS order_date,
            CASE WHEN pg_input_is_valid(amount_text, 'numeric')
                THEN amount_text::numeric(18,2) END AS transaction_amount,
            CASE WHEN pg_input_is_valid(quantity_text, 'numeric')
                THEN quantity_text::numeric::bigint END AS product_quantity,
            product_code,
            presale_status NOT IN ('', '-', '现货') AS is_presale
        FROM cleaned
    ''')


def _sync_presales(conn: Connection, grain: str, prefix: str) -> TableChange:
    start = _period_start("order_date", grain)
    end = _period_end("period_start", grain)
    quantity_column = f"{prefix}_presale_quantity"
    amount_column = f"{prefix}_presale_transaction_amount"
    return sync_table(
        conn,
        schema_name=SCHEMA,
        table_name=f"{prefix}_product_presales",
        key_columns=("period_start", "period_end", "product_code", "is_presale"),
        value_columns=(quantity_column, amount_column),
        expected_select=f'''
            SELECT period_start, {end} AS period_end, product_code, TRUE AS is_presale,
                   SUM(product_quantity)::bigint AS {quantity_column},
                   SUM(transaction_amount)::numeric(18,2) AS {amount_column}
            FROM (
                SELECT {start} AS period_start, product_code,
                       product_quantity, transaction_amount
                FROM upload_weidian_presale_source
                WHERE is_presale AND order_date IS NOT NULL
                  AND product_code IS NOT NULL
                  AND product_quantity IS NOT NULL
                  AND transaction_amount IS NOT NULL
            ) source_rows
            GROUP BY period_start, product_code
        ''',
    )


def refresh_store(conn: Connection) -> list[TableChange]:
    """Refresh the 33 common store tables plus Weidian's three presale tables."""
    changes = refresh_store_for_schema(conn, SCHEMA)
    _prepare_presale_source(conn)
    changes.extend(
        (
            _sync_presales(conn, "month", "monthly"),
            _sync_presales(conn, "quarter", "quarterly"),
            _sync_presales(conn, "half", "half_year"),
        )
    )
    return changes
