from __future__ import annotations

from upload.kuaituantuan.aggregate_refresh import refresh_aggregates
from upload.kuaituantuan.refresh import refresh_store_incremental
from upload.writer import apply_base_changes


EXPECTED_STORE_TABLES = 33
EXPECTED_AGGREGATE_TABLES = 20


def _customer_ids(config, analysis) -> tuple[str, ...]:
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


def commit_upload(conn, config, analysis) -> dict:
    base = apply_base_changes(conn, config, analysis)
    affected_dates = tuple(sorted(analysis.affected_dates))
    if not affected_dates:
        return {
            **base,
            "store_tables_refreshed": 0,
            "aggregate_tables_refreshed": 0,
            "changed_tables": 0,
            "derived_inserted_rows": 0,
            "derived_updated_rows": 0,
            "derived_deleted_rows": 0,
            "table_changes": [],
        }
    store_changes = refresh_store_incremental(
        conn,
        affected_dates,
        _customer_ids(config, analysis),
    )
    if len(store_changes) != EXPECTED_STORE_TABLES:
        raise ValueError(
            f"快团团派生表刷新数量异常：{len(store_changes)} != {EXPECTED_STORE_TABLES}"
        )
    aggregate_changes = refresh_aggregates(conn)
    if len(aggregate_changes) != EXPECTED_AGGREGATE_TABLES:
        raise ValueError(
            f"快团团上层汇总刷新数量异常：{len(aggregate_changes)} "
            f"!= {EXPECTED_AGGREGATE_TABLES}"
        )
    changes = [*store_changes, *aggregate_changes]
    return {
        **base,
        "store_tables_refreshed": len(store_changes),
        "aggregate_tables_refreshed": len(aggregate_changes),
        "changed_tables": sum(
            item.inserted_rows > 0 or item.updated_rows > 0 or item.deleted_rows > 0
            for item in changes
        ),
        "derived_inserted_rows": sum(item.inserted_rows for item in changes),
        "derived_updated_rows": sum(item.updated_rows for item in changes),
        "derived_deleted_rows": sum(item.deleted_rows for item in changes),
        "table_changes": [item.as_dict() for item in changes],
    }
