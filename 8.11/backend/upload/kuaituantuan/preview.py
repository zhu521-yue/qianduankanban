from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping

from upload.models import StoreUploadConfig, UploadAnalysis
from upload.periods import half_year_bounds, month_bounds, quarter_bounds, week_bounds
from upload.repository import UploadRepository


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
GRAINS: dict[str, dict[str, Any]] = {
    "weeks": {
        "bounds": week_bounds,
        "sales_table": "weekly_sales",
        "sales_column": "weekly_transaction_amount",
        "refund_table": "weekly_refunds",
        "refund_column": "weekly_refund_amount",
        "previous": lambda value: value - timedelta(days=7),
    },
    "months": {
        "bounds": month_bounds,
        "sales_table": "monthly_sales",
        "sales_column": "monthly_transaction_amount",
        "refund_table": "monthly_refunds",
        "refund_column": "monthly_refund_amount",
        "previous": lambda value: month_bounds(value - timedelta(days=1))[0],
    },
    "quarters": {
        "bounds": quarter_bounds,
        "sales_table": "quarterly_sales",
        "sales_column": "quarterly_transaction_amount",
        "refund_table": "quarterly_refunds",
        "refund_column": "quarterly_refund_amount",
        "previous": None,
    },
    "half_years": {
        "bounds": half_year_bounds,
        "sales_table": "half_year_sales",
        "sales_column": "half_year_transaction_amount",
        "refund_table": "half_year_refunds",
        "refund_column": "half_year_refund_amount",
        "previous": None,
    },
}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _decimal(value: Any) -> Decimal:
    text = _text(value).replace(",", "").replace("¥", "").replace("￥", "")
    if not text or text in {"-", "--"}:
        return ZERO
    try:
        return Decimal(text)
    except InvalidOperation:
        return ZERO


def _amount(values: Mapping[str, Any]) -> Decimal:
    return (_decimal(values.get("数量")) * _decimal(values.get("商品金额"))).quantize(
        CENT, rounding=ROUND_HALF_UP
    )


def _refund(values: Mapping[str, Any]) -> Decimal:
    return _decimal(values.get("已退款+退款中")).quantize(CENT, rounding=ROUND_HALF_UP)


def _number(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), "f")


def _rate(current: Decimal, previous: Decimal) -> str:
    if previous == 0:
        return "0.00"
    return _number((current - previous) / previous * 100)


def _period_totals(
    values: Mapping[date, Decimal],
    bounds,
) -> dict[date, Decimal]:
    result: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for business_date, amount in values.items():
        result[bounds(business_date)[0]] += amount
    return dict(result)


def build_preview(
    conn,
    config: StoreUploadConfig,
    analysis: UploadAnalysis,
) -> dict[str, Any]:
    repo = UploadRepository(conn, config)
    file_sales: dict[date, Decimal] = defaultdict(lambda: ZERO)
    file_refunds: dict[date, Decimal] = defaultdict(lambda: ZERO)
    old_sales: dict[date, Decimal] = defaultdict(lambda: ZERO)
    old_refunds: dict[date, Decimal] = defaultdict(lambda: ZERO)
    sales_delta: dict[date, Decimal] = defaultdict(lambda: ZERO)
    refund_delta: dict[date, Decimal] = defaultdict(lambda: ZERO)
    source_counts = {
        "dated_rows": 0,
        "valid_sales_rows": 0,
        "refund_rows": 0,
        "sales_with_refund_rows": 0,
        "refund_only_rows": 0,
        "invalid_amount_rows": 0,
    }
    file_gross = ZERO
    file_refund_total = ZERO

    for item in analysis.compared_rows:
        prepared = item.prepared
        if prepared.business_date is not None:
            amount = _amount(prepared.values)
            refund = _refund(prepared.values)
            file_sales[prepared.business_date] += amount
            file_refunds[prepared.business_date] += refund
            file_gross += amount
            file_refund_total += refund
            source_counts["dated_rows"] += 1
            source_counts["valid_sales_rows"] += 1
            if refund > 0:
                source_counts["refund_rows"] += 1
                source_counts["sales_with_refund_rows"] += 1
        if item.action not in {"insert", "update"}:
            continue
        if prepared.business_date is not None:
            sales_delta[prepared.business_date] += _amount(prepared.values)
            refund_delta[prepared.business_date] += _refund(prepared.values)
        if item.action == "update" and item.previous_values is not None and item.previous_business_date is not None:
            previous_amount = _amount(item.previous_values)
            previous_refund = _refund(item.previous_values)
            old_sales[item.previous_business_date] += previous_amount
            old_refunds[item.previous_business_date] += previous_refund
            sales_delta[item.previous_business_date] -= previous_amount
            refund_delta[item.previous_business_date] -= previous_refund

    source_summary = {
        **source_counts,
        "gross_sales_amount": _number(file_gross),
        "refund_amount": _number(file_refund_total),
        "net_amount_for_reference_only": _number(file_gross - file_refund_total),
        "sales_amount_is_gross": True,
        "refund_is_recorded_separately": True,
    }
    store_periods: dict[str, list[dict[str, Any]]] = {}
    aggregate_periods: dict[str, dict[str, list[dict[str, Any]]]] = {
        schema: {} for schema in config.aggregate_path
    }

    for grain, spec in GRAINS.items():
        bounds = spec["bounds"]
        file_sales_periods = _period_totals(file_sales, bounds)
        file_refund_periods = _period_totals(file_refunds, bounds)
        old_sales_periods = _period_totals(old_sales, bounds)
        old_refund_periods = _period_totals(old_refunds, bounds)
        sales_deltas = _period_totals(sales_delta, bounds)
        refund_deltas = _period_totals(refund_delta, bounds)
        starts = set(sales_deltas) | set(refund_deltas)
        previous = spec["previous"]
        comparison_starts = {previous(value) for value in starts} if previous else set()
        current_sales = repo.period_amounts(
            config.schema_name,
            spec["sales_table"],
            spec["sales_column"],
            starts | comparison_starts,
        )
        current_refunds = repo.period_amounts(
            config.schema_name,
            spec["refund_table"],
            spec["refund_column"],
            starts,
        )
        rows: list[dict[str, Any]] = []
        for start in sorted(starts):
            _, end = bounds(start)
            current_sale = Decimal(current_sales.get(start, {}).get("amount") or 0)
            current_refund = Decimal(current_refunds.get(start, {}).get("amount") or 0)
            projected_sale = current_sale + sales_deltas.get(start, ZERO)
            projected_refund = current_refund + refund_deltas.get(start, ZERO)
            row = {
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "current_store_sales_amount": _number(current_sale),
                "file_sales_amount": _number(file_sales_periods.get(start, ZERO)),
                "replaced_database_sales_amount": _number(old_sales_periods.get(start, ZERO)),
                "sales_delta_amount": _number(sales_deltas.get(start, ZERO)),
                "projected_store_sales_amount": _number(projected_sale),
                "current_store_refund_amount": _number(current_refund),
                "file_refund_amount": _number(file_refund_periods.get(start, ZERO)),
                "replaced_database_refund_amount": _number(old_refund_periods.get(start, ZERO)),
                "refund_delta_amount": _number(refund_deltas.get(start, ZERO)),
                "projected_store_refund_amount": _number(projected_refund),
            }
            if previous:
                previous_amount = Decimal(
                    current_sales.get(previous(start), {}).get("amount") or 0
                )
                row["current_sales_comparison_rate"] = _rate(current_sale, previous_amount)
                row["projected_sales_comparison_rate"] = _rate(projected_sale, previous_amount)
            rows.append(row)
        store_periods[grain] = rows

        for schema in config.aggregate_path:
            aggregate_sales = repo.period_amounts(
                schema,
                spec["sales_table"],
                spec["sales_column"],
                starts | comparison_starts,
            )
            aggregate_refunds = repo.period_amounts(
                schema,
                spec["refund_table"],
                spec["refund_column"],
                starts,
            )
            cascade_rows: list[dict[str, Any]] = []
            for start in sorted(starts):
                _, end = bounds(start)
                current_sale = Decimal(aggregate_sales.get(start, {}).get("amount") or 0)
                current_refund = Decimal(aggregate_refunds.get(start, {}).get("amount") or 0)
                projected_sale = current_sale + sales_deltas.get(start, ZERO)
                projected_refund = current_refund + refund_deltas.get(start, ZERO)
                row = {
                    "table_sales": spec["sales_table"],
                    "table_refunds": spec["refund_table"],
                    "period_start": start.isoformat(),
                    "period_end": end.isoformat(),
                    "current_sales_amount": _number(current_sale),
                    "sales_delta_amount": _number(sales_deltas.get(start, ZERO)),
                    "projected_sales_amount": _number(projected_sale),
                    "current_refund_amount": _number(current_refund),
                    "refund_delta_amount": _number(refund_deltas.get(start, ZERO)),
                    "projected_refund_amount": _number(projected_refund),
                }
                if previous:
                    previous_amount = Decimal(
                        aggregate_sales.get(previous(start), {}).get("amount") or 0
                    )
                    row["current_sales_comparison_rate"] = _rate(current_sale, previous_amount)
                    row["projected_sales_comparison_rate"] = _rate(projected_sale, previous_amount)
                cascade_rows.append(row)
            aggregate_periods[schema][grain] = cascade_rows

    return {
        "source_kind": "kuaituantuan_product_detail_upsert",
        "source_classification": source_summary,
        "store_period_changes": store_periods,
        "aggregate_period_changes": aggregate_periods,
    }
