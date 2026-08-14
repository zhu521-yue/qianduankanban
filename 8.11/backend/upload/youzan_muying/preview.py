from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable

from upload.business_preview import (
    GRAINS,
    ZERO,
    _amount,
    _number,
    _period_deltas,
    _rate,
    _schema_tables,
    _text,
)
from upload.models import PreparedRow, StoreUploadConfig
from upload.repository import UploadRepository


VALID_SALES_STATUSES = frozenset({"已完成", "已关闭", "已发货"})


def _decimal(value: Any) -> Decimal | None:
    text = _text(value).replace(",", "").replace("¥", "").replace("￥", "")
    if not text or text in {"-", "--"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _is_valid_customer(values: dict[str, Any] | Any) -> bool:
    customer_id = _text(values.get("买家昵称"))
    return (
        _text(values.get("销售渠道")) == "网店"
        and customer_id not in {"", "-", "0", "0.0"}
    )


def classify_rows(
    rows: Iterable[PreparedRow],
) -> tuple[dict[date, Decimal], dict[date, Decimal], dict[str, Any]]:
    """Classify one Youzan sales export using the confirmed gross-sales rules."""
    sales_by_date: dict[date, Decimal] = defaultdict(lambda: ZERO)
    refunds_by_date: dict[date, Decimal] = defaultdict(lambda: ZERO)
    counts = {
        "dated_rows": 0,
        "valid_sales_rows": 0,
        "excluded_sales_status_rows": 0,
        "refund_rows": 0,
        "sales_with_refund_rows": 0,
        "refund_only_rows": 0,
        "invalid_amount_rows": 0,
        "invalid_quantity_rows": 0,
        "invalid_refund_amount_rows": 0,
        "valid_customer_rows": 0,
        "valid_product_rows": 0,
    }
    gross_sales = ZERO
    refund_amount = ZERO
    gross_quantity = ZERO

    for item in rows:
        if item.business_date is None:
            continue
        counts["dated_rows"] += 1
        values = item.values
        order_status = _text(values.get("订单状态"))
        unit_price = _decimal(values.get("商品单价"))
        quantity = _decimal(values.get("商品数量"))
        raw_refund = _decimal(values.get("商品已退款金额"))
        is_sale = order_status in VALID_SALES_STATUSES
        is_refund = raw_refund is not None and raw_refund > ZERO

        if is_refund:
            current_refund = raw_refund.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            counts["refund_rows"] += 1
            refunds_by_date[item.business_date] += current_refund
            refund_amount += current_refund
        elif raw_refund is None:
            counts["invalid_refund_amount_rows"] += 1

        if not is_sale:
            counts["excluded_sales_status_rows"] += 1
            if is_refund:
                counts["refund_only_rows"] += 1
            continue

        if unit_price is None:
            counts["invalid_amount_rows"] += 1
        if quantity is None:
            counts["invalid_quantity_rows"] += 1
        if unit_price is None or quantity is None:
            if is_refund:
                counts["sales_with_refund_rows"] += 1
            continue

        transaction_amount = (unit_price * quantity).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        counts["valid_sales_rows"] += 1
        sales_by_date[item.business_date] += transaction_amount
        gross_sales += transaction_amount
        gross_quantity += quantity
        if is_refund:
            counts["sales_with_refund_rows"] += 1
        if _is_valid_customer(values):
            counts["valid_customer_rows"] += 1
        if _text(values.get("规格编码")) not in {"", "-"}:
            counts["valid_product_rows"] += 1

    summary = {
        **counts,
        "gross_sales_amount": _number(gross_sales),
        "refund_amount": _number(refund_amount),
        "net_amount_for_reference_only": _number(gross_sales - refund_amount),
        "gross_product_quantity": format(gross_quantity, "f"),
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
                "file_refund_amount": _number(refund_change),
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
        "source_kind": "youzan_sales_snapshot",
        "source_dates": [value.isoformat() for value in sorted(all_dates)],
        "source_classification": source_summary,
        "policies": {
            "business_date": "订单创建时间",
            "sales_file": "skip_each_business_date_that_already_exists_and_insert_new_dates_only",
            "valid_sales_statuses": ["已完成", "已关闭", "已发货"],
            "sales_amount": "商品单价乘商品数量（逐行四舍五入到2位，毛销售额）",
            "product_quantity": "商品数量",
            "product_code": "规格编码；空白或-不进入商品维度表",
            "refund_amount": "商品已退款金额大于0时独立计入退款，不冲减毛销售额",
            "customer_filter": "销售渠道为网店且买家昵称有效时，客户ID等于买家昵称",
            "ignored_upload_columns": list(config.ignored_upload_columns),
            "future_refund_file": "update_existing_raw_records_only",
            "historical_recalculation": "none; new business dates are added to current period values",
        },
        "store_period_changes": store_periods,
        "aggregate_period_changes": cascade,
    }
