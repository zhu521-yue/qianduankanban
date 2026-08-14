from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
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


def _quantity(value: Any) -> int | None:
    text = _text(value).replace(",", "")
    if not text or text in {"-", "--"}:
        return None
    try:
        return int(Decimal(text))
    except (InvalidOperation, ValueError):
        return None


def classify_rows(
    rows: Iterable[PreparedRow],
) -> tuple[dict[date, Decimal], dict[date, Decimal], dict[str, Any]]:
    sales_by_date: dict[date, Decimal] = defaultdict(lambda: ZERO)
    refunds_by_date: dict[date, Decimal] = defaultdict(lambda: ZERO)
    counts = {
        "dated_rows": 0,
        "valid_sales_rows": 0,
        "refund_rows": 0,
        "sales_with_refund_rows": 0,
        "refund_only_rows": 0,
        "invalid_sales_amount_rows": 0,
        "invalid_refund_amount_rows": 0,
        "presale_rows": 0,
        "presale_quantity": 0,
    }
    gross_sales = ZERO
    refund_amount = ZERO
    presale_amount = ZERO

    for item in rows:
        if item.business_date is None:
            continue
        counts["dated_rows"] += 1
        values = item.values
        sales_amount = _money(values.get("订单实际收款金额"))
        raw_refund_amount = _money(values.get("商品已退款金额"))
        order_status = _text(values.get("订单状态"))
        shipping_status = _text(values.get("商品发货"))
        presale_status = _text(values.get("是否预售"))
        is_sale = order_status in {"已完成", "已发货"} and shipping_status == "已发货"
        is_refund = raw_refund_amount is not None and raw_refund_amount > ZERO
        is_presale = presale_status not in {"", "-", "现货"}

        if is_sale:
            if sales_amount is None:
                counts["invalid_sales_amount_rows"] += 1
            else:
                counts["valid_sales_rows"] += 1
                sales_by_date[item.business_date] += sales_amount
                gross_sales += sales_amount
        if is_refund:
            counts["refund_rows"] += 1
            refunds_by_date[item.business_date] += raw_refund_amount
            refund_amount += raw_refund_amount
        elif raw_refund_amount is None:
            counts["invalid_refund_amount_rows"] += 1
        if is_sale and is_refund:
            counts["sales_with_refund_rows"] += 1
        elif is_refund:
            counts["refund_only_rows"] += 1
        if is_presale:
            counts["presale_rows"] += 1
            quantity = _quantity(values.get("商品数量"))
            if quantity is not None:
                counts["presale_quantity"] += quantity
            if sales_amount is not None:
                presale_amount += sales_amount

    summary = {
        **counts,
        "gross_sales_amount": _number(gross_sales),
        "refund_amount": _number(refund_amount),
        "net_amount_for_reference_only": _number(gross_sales - refund_amount),
        "presale_transaction_amount": _number(presale_amount),
        "sales_amount_is_gross": True,
        "refund_is_recorded_separately": True,
        "presale_period_uses_order_time": True,
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
    old_sales = {
        value: _amount(amount)
        for value, amount in repo.daily_sales_amounts(replacement_dates).items()
    }
    old_refunds = {
        value: _amount(amount)
        for value, amount in repo.daily_raw_amounts(
            replacement_dates,
            "商品已退款金额",
            positive_only=True,
        ).items()
    }
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
        file_refund_periods = _period_deltas(file_refunds, bounds)
        replaced_refund_periods = _period_deltas(old_refunds, bounds)
        starts = set(sales_delta) | set(refund_delta)
        previous_start = spec["previous_start"]
        comparison_starts = {
            previous_start(value)
            for value in starts
            if previous_start is not None
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
                "file_sales_amount": _number(sum(
                    (amount for day, amount in file_sales.items() if bounds(day)[0] == start),
                    ZERO,
                )),
                "replaced_database_sales_amount": _number(sum(
                    (amount for day, amount in old_sales.items() if bounds(day)[0] == start),
                    ZERO,
                )),
                "sales_delta_amount": _number(sales_change),
                "current_store_sales_amount": _number(current_sales),
                "projected_store_sales_amount": _number(current_sales + sales_change),
                "file_refund_amount": _number(file_refund_periods.get(start, ZERO)),
                "replaced_database_refund_amount": _number(
                    replaced_refund_periods.get(start, ZERO)
                ),
                "refund_rule_reclassification_amount": "0.00",
                "refund_delta_amount": _number(refund_change),
                "current_store_refund_amount": _number(current_refunds),
                "projected_store_refund_amount": _number(current_refunds + refund_change),
            }
            if previous_start is not None:
                previous = previous_start(start)
                previous_current = _amount(store_sales.get(previous, {}).get("amount"))
                previous_projected = previous_current + sales_delta.get(previous, ZERO)
                item.update({
                    "comparison_period_start": previous.isoformat(),
                    "current_sales_comparison_rate": _rate(current_sales, previous_current),
                    "projected_sales_comparison_rate": _rate(
                        current_sales + sales_change,
                        previous_projected,
                    ),
                })
            grain_rows.append(item)
        store_periods[grain] = grain_rows

        for schema in config.aggregate_path:
            sales_table, refund_table = _schema_tables(schema, spec)
            schema_sales = repo.period_amounts(
                schema,
                sales_table,
                spec["sales_column"],
                starts | comparison_starts,
            )
            schema_refunds = repo.period_amounts(
                schema,
                refund_table,
                spec["refund_column"],
                starts,
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
                    previous_projected = previous_current + sales_delta.get(previous, ZERO)
                    item.update({
                        "comparison_period_start": previous.isoformat(),
                        "current_sales_comparison_rate": _rate(current_sales, previous_current),
                        "projected_sales_comparison_rate": _rate(
                            current_sales + sales_change,
                            previous_projected,
                        ),
                    })
                schema_rows.append(item)
            cascade[schema][grain] = schema_rows

    return {
        "source_kind": "weidian_sales_snapshot",
        "source_classification": source_summary,
        "policies": {
            "sales_file": "replace_each_existing_business_date_and_insert_each_new_business_date",
            "refund_in_sales_file": "persist_product_refund_amount_and_refresh_refund_tables",
            "future_refund_file": "update_existing_raw_records_only",
            "sales_and_refunds_are_separate_metrics": True,
            "presale_period": "order_time",
        },
        "store_period_changes": store_periods,
        "aggregate_period_changes": cascade,
    }
