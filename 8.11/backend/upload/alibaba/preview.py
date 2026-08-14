from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from upload.business_preview import (
    GRAINS,
    ZERO,
    _amount,
    _money,
    _number,
    _period_deltas,
    _rate,
    _schema_tables,
    _text,
)
from upload.models import PreparedRow, StoreUploadConfig
from upload.repository import UploadRepository


def classify_rows(
    rows: Iterable[PreparedRow],
) -> tuple[dict[date, Decimal], dict[date, Decimal], dict[str, Any]]:
    sales_by_date: dict[date, Decimal] = defaultdict(lambda: ZERO)
    refunds_by_date: dict[date, Decimal] = defaultdict(lambda: ZERO)
    counts = {
        "dated_rows": 0,
        "shipped_rows": 0,
        "refund_rows": 0,
        "invalid_amount_rows": 0,
        "invalid_quantity_rows": 0,
        "valid_customer_rows": 0,
        "valid_product_rows": 0,
    }
    gross_amount = ZERO
    refund_amount = ZERO
    gross_quantity = Decimal("0")
    refund_quantity = Decimal("0")

    for item in rows:
        if item.business_date is None:
            continue
        counts["dated_rows"] += 1
        values = item.values
        if _text(values.get("订单状态")) != "已发货":
            continue
        counts["shipped_rows"] += 1
        shipped = _money(values.get("实发金额"))
        refunded = _money(values.get("实退金额")) or ZERO
        shipped_qty = _money(values.get("实发数量"))
        refunded_qty = _money(values.get("实退数量")) or ZERO
        if shipped is None:
            counts["invalid_amount_rows"] += 1
            shipped = ZERO
        if shipped_qty is None:
            counts["invalid_quantity_rows"] += 1
            shipped_qty = ZERO
        sales_by_date[item.business_date] += shipped
        gross_amount += shipped
        refund_amount += refunded
        gross_quantity += shipped_qty
        refund_quantity += refunded_qty
        if refunded > ZERO or refunded_qty > ZERO:
            counts["refund_rows"] += 1
            refunds_by_date[item.business_date] += refunded
        if _text(values.get("买家ID")) not in {"", "-", "0", "0.0"}:
            counts["valid_customer_rows"] += 1
        if _text(values.get("商品编码")) not in {"", "-"}:
            counts["valid_product_rows"] += 1

    summary = {
        **counts,
        "gross_shipped_amount": _number(gross_amount),
        "refund_amount": _number(refund_amount),
        "gross_shipped_quantity": format(gross_quantity, "f"),
        "refund_quantity": format(refund_quantity, "f"),
        "net_product_quantity": format(gross_quantity - refund_quantity, "f"),
        "sales_amount_is_gross_before_refund": True,
        "refund_is_also_recorded_separately": True,
    }
    return dict(sales_by_date), dict(refunds_by_date), summary


def build_preview(
    conn,
    config: StoreUploadConfig,
    rows: list[PreparedRow],
    replacement_dates: set[date],
) -> dict[str, Any]:
    repo = UploadRepository(conn, config)
    file_sales, file_refunds, source_summary = classify_rows(rows)
    all_dates = set(file_sales) | set(file_refunds)
    store_periods: dict[str, list[dict[str, Any]]] = {}
    cascade: dict[str, dict[str, list[dict[str, Any]]]] = {
        schema: {} for schema in config.aggregate_path
    }
    for grain, spec in GRAINS.items():
        bounds = spec["bounds"]
        file_sales_periods = _period_deltas(file_sales, bounds)
        file_refund_periods = _period_deltas(file_refunds, bounds)
        starts = set(file_sales_periods) | set(file_refund_periods)
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
        rows_for_grain: list[dict[str, Any]] = []
        for start in sorted(starts):
            current_sales = _amount(store_sales.get(start, {}).get("amount"))
            current_refunds = _amount(store_refunds.get(start, {}).get("amount"))
            sales_change = file_sales_periods.get(start, ZERO)
            refund_change = file_refund_periods.get(start, ZERO)
            projected_sales = current_sales + sales_change
            projected_refunds = current_refunds + refund_change
            item: dict[str, Any] = {
                "period_start": start.isoformat(),
                "period_end": bounds(start)[1].isoformat(),
                "file_sales_amount": _number(sales_change),
                "sales_delta_amount": _number(sales_change),
                "current_store_sales_amount": _number(current_sales),
                "projected_store_sales_amount": _number(projected_sales),
                "file_refund_amount": _number(file_refund_periods.get(start, ZERO)),
                "refund_delta_amount": _number(refund_change),
                "current_store_refund_amount": _number(current_refunds),
                "projected_store_refund_amount": _number(projected_refunds),
            }
            if previous_start is not None:
                previous = previous_start(start)
                previous_current = _amount(store_sales.get(previous, {}).get("amount"))
                item.update({
                    "comparison_period_start": previous.isoformat(),
                    "current_sales_comparison_rate": _rate(current_sales, previous_current),
                    "projected_sales_comparison_rate": _rate(projected_sales, previous_current),
                })
            rows_for_grain.append(item)
        store_periods[grain] = rows_for_grain

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
                sales_change = file_sales_periods.get(start, ZERO)
                refund_change = file_refund_periods.get(start, ZERO)
                projected_sales = current_sales + sales_change
                projected_refunds = current_refunds + refund_change
                item = {
                    "table_sales": sales_table,
                    "table_refunds": refund_table,
                    "period_start": start.isoformat(),
                    "period_end": bounds(start)[1].isoformat(),
                    "sales_delta_amount": _number(sales_change),
                    "current_sales_amount": _number(current_sales),
                    "projected_sales_amount": _number(projected_sales),
                    "refund_delta_amount": _number(refund_change),
                    "current_refund_amount": _number(current_refunds),
                    "projected_refund_amount": _number(projected_refunds),
                }
                if previous_start is not None:
                    previous = previous_start(start)
                    previous_current = _amount(schema_sales.get(previous, {}).get("amount"))
                    item.update({
                        "comparison_period_start": previous.isoformat(),
                        "current_sales_comparison_rate": _rate(current_sales, previous_current),
                        "projected_sales_comparison_rate": _rate(projected_sales, previous_current),
                    })
                schema_rows.append(item)
            cascade[schema][grain] = schema_rows

    return {
        "source_kind": "alibaba_sales_snapshot",
        "source_dates": [value.isoformat() for value in sorted(all_dates)],
        "source_classification": {
            **source_summary,
            "valid_sales_rows": source_summary["shipped_rows"],
            "sales_with_refund_rows": source_summary["refund_rows"],
            "refund_only_rows": 0,
            "gross_sales_amount": source_summary["gross_shipped_amount"],
        },
        "policies": {
            "business_date": "付款日期",
            "sales_file": "skip_each_business_date_that_already_exists_and_insert_new_dates_only",
            "sales_amount": "实发金额（毛销售额，退款金额单独统计）",
            "product_quantity": "实发数量减实退数量",
            "refund_amount": "实退金额",
            "customer_filter": "订单状态为已发货且买家ID有效",
            "future_refund_file": "update_existing_raw_records_only",
            "historical_recalculation": "none; new business dates are added to current period values",
        },
        "store_period_changes": store_periods,
        "aggregate_period_changes": cascade,
    }
