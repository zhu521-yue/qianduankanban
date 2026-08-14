from __future__ import annotations

from typing import Any

from app.responses import ApiError
from upload.business_preview import aggregate_refresh_tables, build_mixed_sales_preview
from upload.models import ComparedRow, PreparedRow, StoreUploadConfig, UploadAnalysis
from upload.normalization import (
    database_value,
    find_order_key_columns,
    make_business_key,
    normalized_business_date,
    row_digest,
)
from upload.parsing import read_file
from upload.periods import impact_summary
from upload.repository import UploadRepository


def _deduplicate(prepared: list[PreparedRow], analysis: UploadAnalysis) -> list[PreparedRow]:
    """Legacy key-based deduplication kept for later non-sales upload flows.

    Sales snapshots deliberately do not call this helper: multiple rows with the
    same order number can be legitimate product details and must be preserved.
    """
    by_key: dict[str, PreparedRow] = {}
    for item in prepared:
        previous = by_key.get(item.business_key)
        if previous is None:
            by_key[item.business_key] = item
        elif previous.row_hash == item.row_hash:
            analysis.duplicate_identical_rows += 1
        else:
            by_key[item.business_key] = item
            analysis.same_key_updated_rows += 1
    return list(by_key.values())


def analyse_upload(
    conn,
    config: StoreUploadConfig,
    file_name: str,
    content: bytes,
    *,
    include_business_preview: bool = True,
) -> UploadAnalysis:
    """Build a platform-configured sales-upload preview.

    ``replace`` treats every file date as an authoritative whole-day snapshot;
    ``skip`` keeps existing database dates immutable and accepts only new dates.
    ``upsert`` compares configured product-detail business keys and keeps the
    latest file values without dropping other rows from the same date.
    """
    parsed = read_file(file_name, content)
    repo = UploadRepository(conn, config)
    raw_column_types = repo.raw_column_types()
    raw_columns = tuple(raw_column_types)
    if not raw_columns:
        raise ApiError(409, "RAW_TABLE_MISSING", f"{config.schema_name}.raw_data不存在或没有业务字段。")

    ignored_headers = tuple(
        header for header in parsed.headers if header in config.ignored_upload_columns
    )
    effective_headers = tuple(
        header for header in parsed.headers if header not in ignored_headers
    )
    missing = [header for header in effective_headers if header not in raw_columns]
    if missing:
        raise ApiError(
            422,
            "RAW_COLUMN_MISMATCH",
            f"以下上传字段不在{config.schema_name}.raw_data中：{', '.join(missing[:20])}",
        )
    if config.transaction_time_column not in parsed.headers:
        raise ApiError(
            422,
            "TRANSACTION_TIME_MISSING",
            f"文件缺少交易时间字段：{config.transaction_time_column}",
        )
    if config.existing_date_policy == "upsert":
        missing_keys = [column for column in config.row_key_columns if column not in effective_headers]
        if not config.row_key_columns or missing_keys:
            raise ApiError(
                422,
                "ROW_KEY_MISSING",
                f"明细增量上传缺少业务键字段：{', '.join(missing_keys) if missing_keys else '未配置'}",
            )

    analysis = UploadAnalysis(
        store_key=config.store_key,
        schema_name=config.schema_name,
        headers=effective_headers,
        order_key_columns=(
            config.row_key_columns
            if config.existing_date_policy == "upsert"
            else find_order_key_columns(effective_headers)
        ),
        refresh_tables=config.downstream_tables,
        aggregate_path=config.aggregate_path,
        raw_columns_missing_from_file=tuple(column for column in raw_columns if column not in parsed.headers),
        ignored_upload_columns=ignored_headers,
        existing_date_policy=config.existing_date_policy,
    )

    prepared: list[PreparedRow] = []
    for source_row, row in enumerate(parsed.rows, start=2):
        try:
            raw_time = row.get(config.transaction_time_column)
            if raw_time in (None, "", "-", "--"):
                analysis.excluded_undated_rows += 1
                continue
            business_date = normalized_business_date(raw_time, config.date_year_replacements)
            values = {
                header: database_value(
                    row.get(header),
                    raw_column_types.get(header, "text"),
                )
                for header in effective_headers
            }
            business_key = (
                make_business_key(values, config.row_key_columns)
                if config.existing_date_policy == "upsert"
                else f"source_row={source_row}"
            )
            prepared.append(
                PreparedRow(
                    source_row=source_row,
                    values=values,
                    business_date=business_date,
                    business_key=business_key,
                    row_hash=row_digest(values, effective_headers, raw_column_types),
                )
            )
        except ValueError as exc:
            analysis.errors.append({"row": source_row, "code": "ROW_INVALID", "message": str(exc)})

    if analysis.errors:
        raise ApiError(
            422,
            "UPLOAD_ROW_INVALID",
            "上传文件存在无法处理的销售记录。",
            analysis.errors[:100],
        )
    if not prepared:
        raise ApiError(422, "SALES_DATE_MISSING", "上传文件中没有可用的交易日期。")

    # Date-snapshot platforms keep every product detail.  Explicit row-upsert
    # platforms deduplicate only their configured product-detail key.
    analysis.file_dates = {item.business_date for item in prepared if item.business_date is not None}
    analysis.existing_dates = repo.existing_dates(analysis.file_dates)
    analysis.database_rows_by_date = repo.raw_row_counts_by_date(analysis.existing_dates)
    if config.existing_date_policy == "replace":
        accepted = prepared
        preview_replacement_dates = analysis.existing_dates
    elif config.existing_date_policy == "skip":
        accepted = [item for item in prepared if item.business_date not in analysis.existing_dates]
        analysis.skipped_existing_rows = len(prepared) - len(accepted)
        preview_replacement_dates = set()
    elif config.existing_date_policy == "upsert":
        prepared = _deduplicate(prepared, analysis)
        existing_rows = repo.rows_by_keys(
            config.row_key_columns,
            prepared,
            effective_headers,
            raw_column_types,
            None,
        )
        compared: list[ComparedRow] = []
        for item in prepared:
            previous = existing_rows.get(item.business_key)
            if previous is None:
                compared.append(ComparedRow(item, "insert"))
            elif previous["hash"] == item.row_hash:
                compared.append(ComparedRow(
                    item,
                    "unchanged",
                    existing_id=previous["id"],
                    previous_values=previous["values"],
                    previous_business_date=previous["business_date"],
                ))
            else:
                compared.append(ComparedRow(
                    item,
                    "update",
                    existing_id=previous["id"],
                    previous_values=previous["values"],
                    previous_business_date=previous["business_date"],
                ))
        analysis.compared_rows = compared
        accepted = prepared
        preview_replacement_dates = set()
    else:
        raise ApiError(
            500,
            "UPLOAD_DATE_POLICY_INVALID",
            f"未知销售日期处理规则：{config.existing_date_policy}",
        )
    if config.existing_date_policy != "upsert":
        analysis.compared_rows = [ComparedRow(item, "insert") for item in accepted]
    if not include_business_preview:
        analysis.business_preview = {}
    elif config.analysis_preview_builder is not None:
        analysis.business_preview = config.analysis_preview_builder(conn, config, analysis)
    elif config.business_preview_builder is not None:
        analysis.business_preview = config.business_preview_builder(
            conn,
            config,
            accepted,
            preview_replacement_dates,
        )
    else:
        analysis.business_preview = build_mixed_sales_preview(
            conn,
            config,
            accepted,
            preview_replacement_dates,
        )

    candidates: dict[str, dict[str, str]] = {}
    for item in analysis.compared_rows:
        customer = config.customer_resolver(item.prepared.values)
        if customer and customer.get("customer_id"):
            candidates.setdefault(customer["customer_id"], dict(customer))
    analysis.customer_candidates = list(candidates.values())
    existing_customers = repo.existing_customer_ids(candidates)
    analysis.missing_customers = [
        customer
        for customer_id, customer in candidates.items()
        if customer_id not in existing_customers
    ]
    missing_customer_ids = {customer["customer_id"] for customer in analysis.missing_customers}
    analysis.customer_mapping_affected_dates = {
        item.prepared.business_date
        for item in analysis.compared_rows
        if item.prepared.business_date is not None
        and (customer := config.customer_resolver(item.prepared.values)) is not None
        and customer.get("customer_id") in missing_customer_ids
    }
    return analysis


def analysis_payload(analysis: UploadAnalysis) -> dict[str, Any]:
    counts = analysis.counts
    new_dates = analysis.file_dates - analysis.existing_dates
    replacement_dates = (
        analysis.existing_dates if analysis.existing_date_policy == "replace" else set()
    )
    existing_file_dates = analysis.existing_dates
    return {
        "store_key": analysis.store_key,
        "schema_name": analysis.schema_name,
        "upload_strategy": (
            "replace_existing_dates"
            if analysis.existing_date_policy == "replace"
            else "upsert_business_keys"
            if analysis.existing_date_policy == "upsert"
            else "skip_existing_dates"
        ),
        "total_rows": (
            len(analysis.compared_rows)
            + analysis.skipped_existing_rows
            + analysis.excluded_undated_rows
        ),
        "valid_rows": len(analysis.compared_rows),
        "invalid_rows": analysis.excluded_undated_rows,
        "errors": [],
        "order_key_columns": list(analysis.order_key_columns),
        "raw_columns_missing_from_file": list(analysis.raw_columns_missing_from_file),
        "ignored_upload_columns": list(analysis.ignored_upload_columns),
        "total_sales_rows": len(analysis.compared_rows),
        # Legacy response fields remain for compatibility with existing clients.
        "total_rows_after_file_dedup": len(analysis.compared_rows),
        "file_duplicate_identical_rows": analysis.duplicate_identical_rows,
        "file_same_key_updated_rows": analysis.same_key_updated_rows,
        "new_date_rows": sum(
            1 for item in analysis.compared_rows if item.prepared.business_date in new_dates
        ),
        "existing_date_rows": (
            sum(
                1 for item in analysis.compared_rows
                if item.prepared.business_date in (
                    existing_file_dates if analysis.existing_date_policy == "upsert" else replacement_dates
                )
            )
            if replacement_dates
            else analysis.skipped_existing_rows
        ),
        "skipped_existing_date_rows": analysis.skipped_existing_rows,
        "replacement_date_rows": sum(
            1 for item in analysis.compared_rows
            if item.prepared.business_date in replacement_dates
        ),
        "undated_rows": 0,
        "excluded_undated_rows": analysis.excluded_undated_rows,
        "rows_to_delete": analysis.rows_to_delete,
        "rows_to_insert": counts["insert"],
        "insert_rows": counts["insert"],
        "update_rows": counts["update"],
        "unchanged_rows": counts["unchanged"],
        "new_customer_rows": len(analysis.missing_customers),
        "dates": {
            "file": [value.isoformat() for value in sorted(analysis.file_dates)],
            "new": [value.isoformat() for value in sorted(new_dates)],
            "existing": [value.isoformat() for value in sorted(existing_file_dates)],
            "replacement": [value.isoformat() for value in sorted(replacement_dates)],
            "changed_existing": [
                value.isoformat()
                for value in sorted(analysis.affected_dates & existing_file_dates)
            ],
        },
        "database_rows_by_date": {
            value.isoformat(): count
            for value, count in sorted(analysis.database_rows_by_date.items())
        },
        "impact": impact_summary(analysis.affected_dates),
        "refresh": {
            "store_tables": list(analysis.refresh_tables),
            "aggregate_schemas": list(analysis.aggregate_path),
            "aggregate_tables": aggregate_refresh_tables(analysis.aggregate_path),
        },
        "business_preview": analysis.business_preview,
        "new_customer_sample": analysis.missing_customers[:20],
        "changed_row_sample": [
            {
                "source_row": item.prepared.source_row,
                "business_date": (
                    item.prepared.business_date.isoformat()
                    if item.prepared.business_date
                    else None
                ),
                "business_key": item.prepared.business_key,
                "action": (
                    "replace_date"
                    if item.prepared.business_date in replacement_dates
                    else item.action
                    if analysis.existing_date_policy == "upsert"
                    else "insert_date"
                ),
            }
            for item in analysis.changed_rows[:20]
        ],
    }
