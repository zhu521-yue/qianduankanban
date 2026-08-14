from __future__ import annotations

from typing import Any

from psycopg import Connection

from upload.alibaba.aggregate_refresh import refresh_aggregates
from upload.alibaba.incremental_refresh import refresh_store_incremental
from upload.models import StoreUploadConfig, UploadAnalysis
from upload.writer import apply_base_changes


EXPECTED_STORE_TABLES = 33
EXPECTED_AGGREGATE_TABLES = 20


def commit_upload(
    conn: Connection,
    config: StoreUploadConfig,
    analysis: UploadAnalysis,
) -> dict[str, Any]:
    if config.store_key != "alibaba":
        raise ValueError("当前原子刷新器只支持阿里巴巴")

    base = apply_base_changes(conn, config, analysis)
    affected_customer_ids = tuple(sorted({
        customer["customer_id"]
        for customer in analysis.customer_candidates
        if customer.get("customer_id")
    }))
    affected_dates = tuple(sorted(analysis.affected_dates))
    if not affected_dates:
        raise ValueError("阿里巴巴上传没有可刷新的业务日期")
    store_changes = refresh_store_incremental(conn, affected_dates)
    aggregate_changes = refresh_aggregates(conn, affected_customer_ids)
    if len(store_changes) != EXPECTED_STORE_TABLES:
        raise ValueError(
            f"阿里巴巴派生表刷新数量异常：{len(store_changes)} != {EXPECTED_STORE_TABLES}"
        )
    if len(aggregate_changes) != EXPECTED_AGGREGATE_TABLES:
        raise ValueError(
            f"分销组和渠道刷新数量异常：{len(aggregate_changes)} != {EXPECTED_AGGREGATE_TABLES}"
        )

    changes = [*store_changes, *aggregate_changes]
    changed = [
        item.as_dict()
        for item in changes
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
        "table_changes": changed,
    }
