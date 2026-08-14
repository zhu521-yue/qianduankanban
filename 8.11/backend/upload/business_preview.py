from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable, Iterable

from upload.models import MixedSalesRules, PreparedRow, StoreUploadConfig
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
        "summary_sales_table": "weekly_sales_summary",
        "summary_refund_table": "weekly_refunds_summary",
        "previous_start": lambda value: value - timedelta(days=7),
    },
    "months": {
        "bounds": month_bounds,
        "sales_table": "monthly_sales",
        "sales_column": "monthly_transaction_amount",
        "refund_table": "monthly_refunds",
        "refund_column": "monthly_refund_amount",
        "summary_sales_table": "monthly_sales_summary",
        "summary_refund_table": "monthly_refunds_summary",
        "previous_start": lambda value: month_bounds(value - timedelta(days=1))[0],
    },
    "quarters": {
        "bounds": quarter_bounds,
        "sales_table": "quarterly_sales",
        "sales_column": "quarterly_transaction_amount",
        "refund_table": "quarterly_refunds",
        "refund_column": "quarterly_refund_amount",
        "summary_sales_table": "quarterly_sales_summary",
        "summary_refund_table": "quarterly_refunds_summary",
        "previous_start": None,
    },
    "half_years": {
        "bounds": half_year_bounds,
        "sales_table": "half_year_sales",
        "sales_column": "half_year_transaction_amount",
        "refund_table": "half_year_refunds",
        "refund_column": "half_year_refund_amount",
        "summary_sales_table": "half_year_sales_summary",
        "summary_refund_table": "half_year_refunds_summary",
        "previous_start": None,
    },
}


AGGREGATE_REFRESH_TABLES: dict[str, tuple[str, ...]] = {
    "doudian": (
        "daily_sales_summary",
        "weekly_sales_summary",
        "monthly_sales_summary",
        "quarterly_sales_summary",
        "half_year_sales_summary",
        "weekly_refunds_summary",
        "monthly_refunds_summary",
        "quarterly_refunds_summary",
        "half_year_refunds_summary",
        "half_year_customer_health",
        "half_year_high_frequency_products",
    ),
    "daren": (
        "daily_sales",
        "weekly_sales",
        "monthly_sales",
        "quarterly_sales",
        "half_year_sales",
        "weekly_refunds",
        "monthly_refunds",
        "quarterly_refunds",
        "half_year_refunds",
        "customer_health_detail",
        "half_year_high_frequency_products",
    ),
    "fenxiao": (
        "daily_sales",
        "weekly_sales",
        "monthly_sales",
        "quarterly_sales",
        "half_year_sales",
        "weekly_refunds",
        "monthly_refunds",
        "quarterly_refunds",
        "half_year_refunds",
        "customer_health_detail",
        "half_year_high_frequency_products",
    ),
    "youzan": (
        "daily_sales",
        "weekly_sales",
        "monthly_sales",
        "quarterly_sales",
        "half_year_sales",
        "weekly_refunds",
        "monthly_refunds",
        "quarterly_refunds",
        "half_year_refunds",
        "customer_health_detail",
        "half_year_product_frequency",
    ),
    "siyu": (
        "daily_sales",
        "weekly_sales",
        "monthly_sales",
        "quarterly_sales",
        "half_year_sales",
        "weekly_refunds",
        "monthly_refunds",
        "quarterly_refunds",
        "half_year_refunds",
        "customer_health_detail",
        "half_year_high_frequency_products",
    ),
    "qudao": (
        "daily_sales",
        "weekly_sales",
        "monthly_sales",
        "quarterly_sales",
        "half_year_sales",
        "weekly_refunds",
        "monthly_refunds",
        "quarterly_refunds",
        "half_year_refunds",
    ),
}


def aggregate_refresh_tables(path: Iterable[str]) -> dict[str, list[str]]:
    return {
        schema: list(AGGREGATE_REFRESH_TABLES.get(schema, ()))
        for schema in path
    }


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _money(value: Any) -> Decimal | None:
    text = _text(value).replace(",", "").replace("¥", "").replace("￥", "")
    if not text or text in {"-", "--"}:
        return None
    try:
        return Decimal(text).quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def _amount(value: Any) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _number(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), "f")


def _rate(current: Decimal, previous: Decimal) -> str:
    if previous == 0:
        return "0.00"
    result = ((current - previous) / previous * 100).quantize(CENT, rounding=ROUND_HALF_UP)
    return format(result, "f")


def _classify_file_rows(
    rows: Iterable[PreparedRow],
    rules: MixedSalesRules,
) -> tuple[dict[date, Decimal], dict[date, Decimal], dict[str, Any]]:
    sales_by_date: dict[date, Decimal] = defaultdict(lambda: ZERO)
    refunds_by_date: dict[date, Decimal] = defaultdict(lambda: ZERO)
    counts = {
        "dated_rows": 0,
        "valid_sales_rows": 0,
        "refund_rows": 0,
        "sales_with_refund_rows": 0,
        "refund_only_rows": 0,
        "invalid_amount_rows": 0,
    }
    gross_sales = ZERO
    refund_amount = ZERO

    for item in rows:
        if item.business_date is None:
            continue
        counts["dated_rows"] += 1
        amount = _money(item.values.get(rules.amount_column))
        status = _text(item.values.get(rules.order_status_column))
        refund_status = _text(item.values.get(rules.refund_status_column))
        is_sale = status in rules.valid_sales_statuses
        is_refund = refund_status not in rules.non_refund_statuses
        if amount is None:
            if is_sale or is_refund:
                counts["invalid_amount_rows"] += 1
            continue
        if is_sale:
            counts["valid_sales_rows"] += 1
            sales_by_date[item.business_date] += amount
            gross_sales += amount
        if is_refund:
            counts["refund_rows"] += 1
            refunds_by_date[item.business_date] += amount
            refund_amount += amount
        if is_sale and is_refund:
            counts["sales_with_refund_rows"] += 1
        elif is_refund:
            counts["refund_only_rows"] += 1

    summary = {
        **counts,
        "gross_sales_amount": _number(gross_sales),
        "refund_amount": _number(refund_amount),
        "net_amount_for_reference_only": _number(gross_sales - refund_amount),
        "sales_amount_is_gross": True,
        "refund_is_recorded_separately": True,
    }
    return dict(sales_by_date), dict(refunds_by_date), summary


def _period_deltas(
    daily_delta: dict[date, Decimal],
    bounds: Callable[[date], tuple[date, date]],
) -> dict[date, Decimal]:
    result: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for business_date, amount in daily_delta.items():
        result[bounds(business_date)[0]] += amount
    return dict(result)


def _dates_in_periods(
    starts: Iterable[date],
    bounds: Callable[[date], tuple[date, date]],
) -> set[date]:
    result: set[date] = set()
    for start in starts:
        _, end = bounds(start)
        current = start
        while current <= end:
            result.add(current)
            current += timedelta(days=1)
    return result


def _schema_tables(schema: str, spec: dict[str, Any]) -> tuple[str, str]:
    if schema == "doudian":
        return spec["summary_sales_table"], spec["summary_refund_table"]
    return spec["sales_table"], spec["refund_table"]


def build_mixed_sales_preview(
    conn,
    config: StoreUploadConfig,
    rows: list[PreparedRow],
    replacement_dates: set[date],
) -> dict[str, Any]:
    rules = config.mixed_sales_rules
    if rules is None:
        return {}

    repo = UploadRepository(conn, config)
    file_sales, file_refunds, source_summary = _classify_file_rows(rows, rules)
    old_sales = {
        value: _amount(amount)
        for value, amount in repo.daily_sales_amounts(replacement_dates).items()
    }
    old_refunds = {
        value: _amount(amount)
        for value, amount in repo.daily_refund_amounts(replacement_dates, rules).items()
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
        file_refund_periods = _period_deltas(file_refunds, bounds)
        replaced_refund_periods = _period_deltas(old_refunds, bounds)
        uploaded_refund_delta = _period_deltas(refund_daily_delta, bounds)
        starts = set(sales_delta) | set(uploaded_refund_delta)
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
        raw_refunds = {
            value: _amount(amount)
            for value, amount in repo.daily_refund_amounts(
                _dates_in_periods(starts, bounds), rules
            ).items()
        }
        raw_refund_periods = _period_deltas(raw_refunds, bounds)
        actual_refund_delta = {
            start: (
                raw_refund_periods.get(start, ZERO)
                + file_refund_periods.get(start, ZERO)
                - replaced_refund_periods.get(start, ZERO)
                - _amount(store_refunds.get(start, {}).get("amount"))
            )
            for start in starts
        }
        grain_rows: list[dict[str, Any]] = []
        for start in sorted(starts):
            end = bounds(start)[1]
            current_sales = _amount(store_sales.get(start, {}).get("amount"))
            current_refunds = _amount(store_refunds.get(start, {}).get("amount"))
            sales_change = sales_delta.get(start, ZERO)
            refund_change = actual_refund_delta.get(start, ZERO)
            rule_reclassification = (
                raw_refund_periods.get(start, ZERO) - current_refunds
            )
            item: dict[str, Any] = {
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "file_sales_amount": _number(
                    sum((amount for day, amount in file_sales.items() if bounds(day)[0] == start), ZERO)
                ),
                "replaced_database_sales_amount": _number(
                    sum((amount for day, amount in old_sales.items() if bounds(day)[0] == start), ZERO)
                ),
                "sales_delta_amount": _number(sales_change),
                "current_store_sales_amount": _number(current_sales),
                "projected_store_sales_amount": _number(current_sales + sales_change),
                "file_refund_amount": _number(
                    file_refund_periods.get(start, ZERO)
                ),
                "replaced_database_refund_amount": _number(
                    replaced_refund_periods.get(start, ZERO)
                ),
                "refund_rule_reclassification_amount": _number(rule_reclassification),
                "refund_delta_amount": _number(refund_change),
                "current_store_refund_amount": _number(current_refunds),
                "projected_store_refund_amount": _number(current_refunds + refund_change),
            }
            if previous_start is not None:
                previous = previous_start(start)
                previous_current = _amount(store_sales.get(previous, {}).get("amount"))
                previous_projected = previous_current + sales_delta.get(previous, ZERO)
                item.update(
                    {
                        "comparison_period_start": previous.isoformat(),
                        "current_sales_comparison_rate": _rate(current_sales, previous_current),
                        "projected_sales_comparison_rate": _rate(
                            current_sales + sales_change,
                            previous_projected,
                        ),
                    }
                )
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
                refund_change = actual_refund_delta.get(start, ZERO)
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
                    item.update(
                        {
                            "comparison_period_start": previous.isoformat(),
                            "current_sales_comparison_rate": _rate(current_sales, previous_current),
                            "projected_sales_comparison_rate": _rate(
                                current_sales + sales_change,
                                previous_projected,
                            ),
                        }
                    )
                schema_rows.append(item)
            cascade[schema][grain] = schema_rows

    return {
        "source_kind": "mixed_sales_snapshot",
        "source_classification": source_summary,
        "policies": {
            "sales_file": "replace_each_existing_business_date_and_insert_each_new_business_date",
            "refund_in_sales_file": "persist_in_raw_data_and_refresh_refund_tables",
            "future_refund_file": "update_existing_raw_records_only",
            "unmatched_future_refund": "reject_for_manual_review_without_inserting_a_sales_record",
            "sales_and_refunds_are_separate_metrics": True,
        },
        "store_period_changes": store_periods,
        "aggregate_period_changes": cascade,
    }
