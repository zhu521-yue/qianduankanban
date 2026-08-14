from __future__ import annotations

from typing import Any

from psycopg import Connection

from upload.models import StoreUploadConfig, UploadAnalysis
from upload.writer import apply_base_changes
from upload.youzan_muying.aggregate_refresh import refresh_aggregates_incremental
from upload.youzan_muying.incremental_refresh import (
    affected_customer_ids,
    refresh_store_incremental,
)


EXPECTED_STORE_TABLES = 33
EXPECTED_AGGREGATE_TABLES = 31


def commit_upload(
    conn: Connection,
    config: StoreUploadConfig,
    analysis: UploadAnalysis,
) -> dict[str, Any]:
    if config.store_key != "youzan_muying":
        raise ValueError("当前原子刷新器只支持母婴旗舰店")

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
        config.schema_name,
        affected_dates,
        affected_customer_ids(config, analysis),
    )
    aggregate_changes = refresh_aggregates_incremental(conn)
    if len(store_changes) != EXPECTED_STORE_TABLES:
        raise ValueError(
            f"母婴店派生表刷新数量异常：{len(store_changes)} != {EXPECTED_STORE_TABLES}"
        )
    if len(aggregate_changes) != EXPECTED_AGGREGATE_TABLES:
        raise ValueError(
            f"有赞、私域组和渠道刷新数量异常：{len(aggregate_changes)} "
            f"!= {EXPECTED_AGGREGATE_TABLES}"
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
