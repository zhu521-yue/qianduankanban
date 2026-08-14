from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from psycopg import Connection

from upload.doudian_kocotree.aggregate_refresh import refresh_daren, refresh_qudao
from upload.kuaishou.refunds import classify_rows
from upload.kuaishou.refresh import refresh_store
from upload.models import StoreUploadConfig, UploadAnalysis
from upload.repository import UploadRepository
from upload.writer import apply_base_changes


EXPECTED_STORE_TABLES = 33
EXPECTED_AGGREGATE_TABLES = 20


def _refund_daily_changes(
    conn: Connection,
    config: StoreUploadConfig,
    analysis: UploadAnalysis,
) -> dict[date, Decimal]:
    new_rows = [item.prepared for item in analysis.compared_rows]
    _, new_refunds, _ = classify_rows(new_rows)
    old_rows = UploadRepository(conn, config).prepared_raw_rows_by_dates(
        analysis.existing_dates,
        ("订单创建时间", "订单状态", "实付款", "售后状态", "订单备注"),
    )
    _, old_refunds, _ = classify_rows(old_rows)
    dates = set(new_refunds) | set(old_refunds) | analysis.existing_dates
    return {
        value: new_refunds.get(value, Decimal("0.00"))
        - old_refunds.get(value, Decimal("0.00"))
        for value in dates
    }


def commit_upload(
    conn: Connection,
    config: StoreUploadConfig,
    analysis: UploadAnalysis,
) -> dict[str, Any]:
    if config.store_key != "kuaishou":
        raise ValueError("当前原子刷新器只支持快手小店")

    refund_changes = _refund_daily_changes(conn, config, analysis)
    base = apply_base_changes(conn, config, analysis)
    store_changes = refresh_store(conn, refund_changes)

    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:daren'))")
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:qudao'))")
    aggregate_changes = [*refresh_daren(conn), *refresh_qudao(conn)]
    if len(store_changes) != EXPECTED_STORE_TABLES:
        raise ValueError(
            f"店铺派生表刷新数量异常：{len(store_changes)} != {EXPECTED_STORE_TABLES}"
        )
    if len(aggregate_changes) != EXPECTED_AGGREGATE_TABLES:
        raise ValueError(
            f"达人组及渠道刷新数量异常：{len(aggregate_changes)} != {EXPECTED_AGGREGATE_TABLES}"
        )

    store_order = {table: index for index, table in enumerate(config.downstream_tables)}
    ordered_store_changes = sorted(
        store_changes,
        key=lambda item: store_order.get(item.table_name, len(store_order)),
    )
    changes = [*ordered_store_changes, *aggregate_changes]
    changed = [
        item for item in changes
        if item.inserted_rows or item.updated_rows or item.deleted_rows
    ]
    return {
        **base,
        "store_tables_refreshed": len(store_changes),
        "aggregate_tables_refreshed": len(aggregate_changes),
        "changed_tables": len(changed),
        "derived_inserted_rows": sum(item.inserted_rows for item in changes),
        "derived_updated_rows": sum(item.updated_rows for item in changes),
        "derived_deleted_rows": sum(item.deleted_rows for item in changes),
        "table_changes": [item.as_dict() for item in changes],
    }
