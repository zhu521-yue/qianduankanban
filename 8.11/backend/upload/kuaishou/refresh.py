from __future__ import annotations

from datetime import date
from decimal import Decimal

from psycopg import Connection

from upload.doudian_kocotree.refresh import refresh_store_for_schema
from upload.periods import half_year_bounds, month_bounds, quarter_bounds, week_bounds
from upload.table_sync import TableChange, sync_table


SCHEMA = "kuaishouxiaodian"


def _refund_period_changes(
    daily_changes: dict[date, Decimal],
    bounds,
) -> dict[tuple[date, date], Decimal]:
    result: dict[tuple[date, date], Decimal] = {}
    for business_date, amount in daily_changes.items():
        key = bounds(business_date)
        result[key] = result.get(key, Decimal("0.00")) + amount
    return {key: value for key, value in result.items() if value != 0}


def _refund_expected_select(
    table: str,
    amount_column: str,
    changes: dict[tuple[date, date], Decimal],
) -> str:
    if not changes:
        return f"SELECT period_start, period_end, {amount_column} FROM {SCHEMA}.{table}"
    values = ",\n".join(
        f"(DATE '{start.isoformat()}', DATE '{end.isoformat()}', {amount})"
        for (start, end), amount in sorted(changes.items())
    )
    return f'''
        WITH additions(period_start, period_end, delta_amount) AS (
            VALUES {values}
        )
        SELECT COALESCE(current.period_start, additions.period_start) AS period_start,
               COALESCE(current.period_end, additions.period_end) AS period_end,
               (COALESCE(current.{amount_column}, 0) +
                COALESCE(additions.delta_amount, 0))::numeric(18,2) AS {amount_column}
        FROM {SCHEMA}.{table} current
        FULL JOIN additions USING (period_start, period_end)
        WHERE COALESCE(current.{amount_column}, 0) +
              COALESCE(additions.delta_amount, 0) > 0
    '''


def refresh_store(
    conn: Connection,
    daily_refund_changes: dict[date, Decimal],
) -> list[TableChange]:
    """Refresh 29 raw-derived tables plus four incrementally maintained refund tables."""
    changes = refresh_store_for_schema(conn, SCHEMA)
    for prefix, bounds in (
        ("weekly", week_bounds),
        ("monthly", month_bounds),
        ("quarterly", quarter_bounds),
        ("half_year", half_year_bounds),
    ):
        table = f"{prefix}_refunds"
        amount = f"{prefix}_refund_amount"
        changes.append(sync_table(
            conn,
            schema_name=SCHEMA,
            table_name=table,
            key_columns=("period_start", "period_end"),
            value_columns=(amount,),
            expected_select=_refund_expected_select(
                table,
                amount,
                _refund_period_changes(daily_refund_changes, bounds),
            ),
        ))
    return changes

