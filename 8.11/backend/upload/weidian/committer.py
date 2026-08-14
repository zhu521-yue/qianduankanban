from __future__ import annotations

from typing import Any

from psycopg import Connection

from upload.doudian_kocotree.aggregate_refresh import refresh_daren, refresh_qudao
from upload.models import StoreUploadConfig, UploadAnalysis
from upload.weidian.refresh import refresh_store
from upload.writer import apply_base_changes


EXPECTED_STORE_TABLES = 36
EXPECTED_AGGREGATE_TABLES = 20


def commit_upload(
    conn: Connection,
    config: StoreUploadConfig,
    analysis: UploadAnalysis,
) -> dict[str, Any]:
    """Execute the complete Weidian refresh inside the caller-owned transaction."""
    if config.store_key != "weidian":
        raise ValueError("当前原子刷新器只支持微店")

    base = apply_base_changes(conn, config, analysis)
    store_changes = refresh_store(conn)
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:daren'))")
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('upload:qudao'))")
    aggregate_changes = [*refresh_daren(conn), *refresh_qudao(conn)]

    if len(store_changes) != EXPECTED_STORE_TABLES:
        raise ValueError(
            f"店铺派生表刷新数量异常：{len(store_changes)} != {EXPECTED_STORE_TABLES}"
        )
    if len(aggregate_changes) != EXPECTED_AGGREGATE_TABLES:
        raise ValueError(
            f"上层汇总表刷新数量异常：{len(aggregate_changes)} != {EXPECTED_AGGREGATE_TABLES}"
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
