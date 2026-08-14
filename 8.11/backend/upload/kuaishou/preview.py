from __future__ import annotations

from datetime import date
from typing import Any

from upload.business_preview import (
    GRAINS,
    ZERO,
    _amount,
    _number,
    _period_deltas,
    _rate,
    _schema_tables,
)
from upload.kuaishou.refunds import classify_rows
from upload.models import PreparedRow, StoreUploadConfig
from upload.repository import UploadRepository


def build_preview(
    conn,
    config: StoreUploadConfig,
    rows: list[PreparedRow],
    replacement_dates: set[date],
) -> dict[str, Any]:
    """Preview Kuaishou's configured whole-date replacement semantics."""
    repo = UploadRepository(conn, config)
    file_sales, file_refunds, source_summary = classify_rows(rows)
    old_sales = {
        value: _amount(amount)
        for value, amount in repo.daily_sales_amounts(replacement_dates).items()
    }
    existing_rows = repo.prepared_raw_rows_by_dates(
        replacement_dates,
        ("订单创建时间", "订单状态", "实付款", "售后状态", "订单备注"),
    )
    _, old_refunds, _ = classify_rows(existing_rows)
    all_dates = set(file_sales) | set(file_refunds) | replacement_dates
    sales_daily_delta = {
        value: file_sales.get(value, ZERO) - old_sales.get(value, ZERO)
        for value in all_dates
    }
    refund_daily_delta = {
        value: file_refunds.get(value, ZERO) - old_refunds.get(value, ZERO)
        for value in all_dates
    }

    store_periods: dict[str, list[dict[str, Any]]] = {}
    cascade: dict[str, dict[str, list[dict[str, Any]]]] = {
        schema: {} for schema in config.aggregate_path
    }
    for grain, spec in GRAINS.items():
        bounds = spec["bounds"]
        sales_delta = _period_deltas(sales_daily_delta, bounds)
        refund_delta = _period_deltas(refund_daily_delta, bounds)
        file_sales_periods = _period_deltas(file_sales, bounds)
        old_sales_periods = _period_deltas(old_sales, bounds)
        file_refund_periods = _period_deltas(file_refunds, bounds)
        old_refund_periods = _period_deltas(old_refunds, bounds)
        starts = set(sales_delta) | set(refund_delta)
        previous_start = spec["previous_start"]
        comparison_starts = {
            previous_start(value) for value in starts if previous_start is not None
        }
        store_sales = repo.period_amounts(
            config.schema_name,
            spec["sales_table"],
            spec["sales_column"],
            starts | comparison_starts,
        )
        store_refunds = repo.period_amounts(
            config.schema_name,
            spec["refund_table"],
            spec["refund_column"],
            starts,
        )

        grain_rows: list[dict[str, Any]] = []
        for start in sorted(starts):
            current_sales = _amount(store_sales.get(start, {}).get("amount"))
            current_refunds = _amount(store_refunds.get(start, {}).get("amount"))
            sales_change = sales_delta.get(start, ZERO)
            refund_change = refund_delta.get(start, ZERO)
            item: dict[str, Any] = {
                "period_start": start.isoformat(),
                "period_end": bounds(start)[1].isoformat(),
                "file_sales_amount": _number(file_sales_periods.get(start, ZERO)),
                "replaced_database_sales_amount": _number(old_sales_periods.get(start, ZERO)),
                "sales_delta_amount": _number(sales_change),
                "current_store_sales_amount": _number(current_sales),
                "projected_store_sales_amount": _number(current_sales + sales_change),
                "file_refund_amount": _number(file_refund_periods.get(start, ZERO)),
                "replaced_database_refund_amount": _number(old_refund_periods.get(start, ZERO)),
                "refund_rule_reclassification_amount": "0.00",
                "refund_delta_amount": _number(refund_change),
                "current_store_refund_amount": _number(current_refunds),
                "projected_store_refund_amount": _number(current_refunds + refund_change),
            }
            if previous_start is not None:
                previous = previous_start(start)
                previous_current = _amount(store_sales.get(previous, {}).get("amount"))
                item.update({
                    "comparison_period_start": previous.isoformat(),
                    "current_sales_comparison_rate": _rate(current_sales, previous_current),
                    "projected_sales_comparison_rate": _rate(
                        current_sales + sales_change,
                        previous_current + sales_delta.get(previous, ZERO),
                    ),
                })
            grain_rows.append(item)
        store_periods[grain] = grain_rows

        for schema in config.aggregate_path:
            sales_table, refund_table = _schema_tables(schema, spec)
            schema_sales = repo.period_amounts(
                schema, sales_table, spec["sales_column"], starts | comparison_starts
            )
            schema_refunds = repo.period_amounts(
                schema, refund_table, spec["refund_column"], starts
            )
            schema_rows: list[dict[str, Any]] = []
            for start in sorted(starts):
                current_sales = _amount(schema_sales.get(start, {}).get("amount"))
                current_refunds = _amount(schema_refunds.get(start, {}).get("amount"))
                sales_change = sales_delta.get(start, ZERO)
                refund_change = refund_delta.get(start, ZERO)
                item = {
                    "table_sales": sales_table,
                    "table_refunds": refund_table,
                    "period_start": start.isoformat(),
                    "period_end": bounds(start)[1].isoformat(),
                    "sales_delta_amount": _number(sales_change),
                    "current_sales_amount": _number(current_sales),
                    "projected_sales_amount": _number(current_sales + sales_change),
                    "refund_delta_amount": _number(refund_change),
                    "current_refund_amount": _number(current_refunds),
                    "projected_refund_amount": _number(current_refunds + refund_change),
                }
                if previous_start is not None:
                    previous = previous_start(start)
                    previous_current = _amount(schema_sales.get(previous, {}).get("amount"))
                    item.update({
                        "comparison_period_start": previous.isoformat(),
                        "current_sales_comparison_rate": _rate(current_sales, previous_current),
                        "projected_sales_comparison_rate": _rate(
                            current_sales + sales_change,
                            previous_current + sales_delta.get(previous, ZERO),
                        ),
                    })
                schema_rows.append(item)
            cascade[schema][grain] = schema_rows

    return {
        "source_kind": "kuaishou_sales_snapshot",
        "source_dates": [value.isoformat() for value in sorted(all_dates)],
        "source_classification": source_summary,
        "policies": {
            "sales_file": "replace_each_existing_business_date_and_insert_each_new_business_date",
            "business_date": "订单创建时间",
            "refund_in_sales_file": "record_refund_and_refresh_refund_tables",
            "future_refund_file": "update_existing_raw_records_only",
            "sales_and_refunds_are_separate_metrics": True,
            "daren_group": "recalculate_and_overwrite_existing_business_keys",
        },
        "store_period_changes": store_periods,
        "aggregate_period_changes": cascade,
    }
