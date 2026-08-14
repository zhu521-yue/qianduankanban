from __future__ import annotations

from psycopg import Connection

from upload.doudian_kocotree.aggregate_refresh import (
    _daily_sales_select,
    _high_frequency_select,
    _period_select,
    _channel_daily_select,
    _channel_period_select,
)
from upload.table_sync import TableChange, sync_table


DISTRIBUTION_STORES = ("alibaba", "jushuitan")


def _scope_daily(expected: str) -> str:
    return f"SELECT expected.* FROM ({expected}) expected JOIN upload_alibaba_dates dates USING (transaction_date)"


def _scope_period(expected: str, grain: str) -> str:
    return f'''SELECT expected.* FROM ({expected}) expected
        JOIN upload_alibaba_periods periods
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


def refresh_fenxiao(
    conn: Connection,
    affected_customer_ids: tuple[str, ...] = (),
    *,
    include_health: bool = True,
) -> list[TableChange]:
    changes = [_sync_scoped(
        conn, "fenxiao",
        "daily_sales",
        ("transaction_date",),
        (
            "transaction_amount",
            "year_over_year_rate",
            "rolling_7_day_transaction_amount",
            "rolling_30_day_transaction_amount",
        ),
        _scope_daily(_daily_sales_select(DISTRIBUTION_STORES, "daily_sales", 2)),
        "target.transaction_date IN (SELECT transaction_date FROM upload_alibaba_dates)",
    )]

    for prefix, rate, interval in (
        ("weekly", "week_over_week_rate", "7 days"),
        ("monthly", "month_over_month_rate", "1 month"),
        ("quarterly", None, None),
        ("half_year", None, None),
    ):
        amount = f"{prefix}_transaction_amount"
        values = (amount, *((rate,) if rate else ()))
        grain = {"weekly": "week", "monthly": "month", "quarterly": "quarter", "half_year": "half"}[prefix]
        changes.append(_sync_scoped(
            conn, "fenxiao",
            f"{prefix}_sales",
            ("period_start", "period_end"),
            values,
            _scope_period(_period_select(
                DISTRIBUTION_STORES,
                f"{prefix}_sales",
                amount,
                rate,
                interval,
                2,
            ), grain),
            f"EXISTS (SELECT 1 FROM upload_alibaba_periods p WHERE p.grain='{grain}' AND p.period_start=target.period_start AND p.period_end=target.period_end)",
        ))

    for prefix in ("weekly", "monthly", "quarterly", "half_year"):
        amount = f"{prefix}_refund_amount"
        grain = {"weekly": "week", "monthly": "month", "quarterly": "quarter", "half_year": "half"}[prefix]
        changes.append(_sync_scoped(
            conn, "fenxiao",
            f"{prefix}_refunds",
            ("period_start", "period_end"),
            (amount,),
            _scope_period(_period_select(
                DISTRIBUTION_STORES,
                f"{prefix}_refunds",
                amount,
            ), grain),
            f"EXISTS (SELECT 1 FROM upload_alibaba_periods p WHERE p.grain='{grain}' AND p.period_start=target.period_start AND p.period_end=target.period_end)",
        ))

    fenxiao_health_values = (
            "week_purchase_count",
            "month_purchase_count",
            "half_year_purchase_count",
            "half_year_purchase_amount",
            "week_score",
            "month_score",
            "customer_score",
            "customer_health_status",
            "state_instructions",
            "follow_up_action",
    )
    fenxiao_health_expected = '''
        SELECT 'natural_week'::text AS health_grain,
               'alibaba'::text AS source_platform,
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
        FROM alibaba.customer_health_detail health
        LEFT JOIN public.distribution_customer_status_action rules
          ON rules.customer_health_status = health.customer_health_status
        WHERE health.customer_id IN (
                  SELECT customer_id FROM upload_alibaba_health_customers
              )
          AND EXISTS (
                  SELECT 1 FROM upload_alibaba_health_weeks weeks
                  WHERE weeks.period_start = health.period_start
                    AND weeks.period_end = health.period_end
              )
    '''
    if include_health:
        changes.append(sync_table(
            conn,
            schema_name="fenxiao",
            table_name="customer_health_detail",
            key_columns=("health_grain", "source_platform", "customer_id", "period_start", "period_end"),
            value_columns=fenxiao_health_values,
            expected_select=fenxiao_health_expected,
            delete_scope_sql='''
                target.health_grain = 'natural_week'
                AND target.source_platform = 'alibaba'
                AND target.customer_id IN (
                    SELECT customer_id FROM upload_alibaba_health_customers
                )
                AND EXISTS (
                    SELECT 1 FROM upload_alibaba_health_weeks weeks
                    WHERE weeks.period_start = target.period_start
                      AND weeks.period_end = target.period_end
                )
            ''',
        ))
    changes.append(_sync_scoped(
        conn, "fenxiao",
        "half_year_high_frequency_products",
        ("period_start", "period_end", "product_code"),
        (
            "half_year_product_quantity",
            "half_year_transaction_amount",
            "quantity_rank",
            "amount_rank",
            "selection_type",
        ),
        _scope_period(_high_frequency_select(DISTRIBUTION_STORES), "half"),
        "EXISTS (SELECT 1 FROM upload_alibaba_periods p WHERE p.grain='half' AND p.period_start=target.period_start AND p.period_end=target.period_end)",
    ))
    return changes


def refresh_qudao_scoped(conn: Connection) -> list[TableChange]:
    changes = [_sync_scoped(
        conn, "qudao", "daily_sales", ("transaction_date",),
        (
            "daren_transaction_amount", "siyu_transaction_amount",
            "fenxiao_transaction_amount", "transaction_amount",
            "included_group_count", "is_complete", "year_over_year_rate",
            "rolling_7_day_transaction_amount", "rolling_30_day_transaction_amount",
        ),
        _scope_daily(_channel_daily_select()),
        "target.transaction_date IN (SELECT transaction_date FROM upload_alibaba_dates)",
    )]
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
            _scope_period(_channel_period_select(prefix, "sales", rate, interval), grain),
            f"EXISTS (SELECT 1 FROM upload_alibaba_periods p WHERE p.grain='{grain}' AND p.period_start=target.period_start AND p.period_end=target.period_end)",
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
            _scope_period(_channel_period_select(prefix, "refunds"), grain),
            f"EXISTS (SELECT 1 FROM upload_alibaba_periods p WHERE p.grain='{grain}' AND p.period_start=target.period_start AND p.period_end=target.period_end)",
        ))
    return changes


def refresh_aggregates(
    conn: Connection,
    affected_customer_ids: tuple[str, ...] = (),
    *,
    include_health: bool = True,
) -> list[TableChange]:
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:fenxiao'))")
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:qudao'))")
    return [
        *refresh_fenxiao(
            conn,
            affected_customer_ids,
            include_health=include_health,
        ),
        *refresh_qudao_scoped(conn),
    ]
