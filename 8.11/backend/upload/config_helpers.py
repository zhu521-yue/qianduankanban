from __future__ import annotations

from typing import Any, Mapping

from upload.models import MixedSalesRules
from upload.normalization import normalize_customer_id, text_value


INVALID_IDS = {"", "-", "0", "0.0"}


DOUDIAN_MIXED_SALES_RULES = MixedSalesRules(
    amount_column="订单应付金额",
    order_status_column="订单状态",
    valid_sales_statuses=("已完成", "已发货", "待发货"),
    refund_status_column="售后状态",
    non_refund_statuses=("", "-", "换货成功", "换货待收货", "补寄成功"),
)


def value(row: Mapping[str, Any], column: str) -> str:
    return (text_value(row.get(column)) or "").strip()


def simple_customer(
    id_column: str,
    nickname_column: str | None = None,
    *,
    required_values: Mapping[str, str] | None = None,
):
    def resolver(row: Mapping[str, Any]) -> Mapping[str, str] | None:
        for column, expected in (required_values or {}).items():
            if value(row, column) != expected:
                return None
        customer_id = normalize_customer_id(row.get(id_column))
        if customer_id in INVALID_IDS:
            return None
        result = {"customer_id": customer_id}
        if nickname_column:
            result["customer_nickname"] = value(row, nickname_column)
        return result

    return resolver


def first_available_customer(
    choices: tuple[tuple[str, str | None], ...],
    *,
    required_values: Mapping[str, str] | None = None,
):
    def resolver(row: Mapping[str, Any]) -> Mapping[str, str] | None:
        for column, expected in (required_values or {}).items():
            if value(row, column) != expected:
                return None
        for id_column, nickname_column in choices:
            customer_id = normalize_customer_id(row.get(id_column))
            if customer_id not in INVALID_IDS:
                result = {"customer_id": customer_id}
                if nickname_column:
                    result["customer_nickname"] = value(row, nickname_column)
                return result
        return None

    return resolver


def jushuitan_customer(row: Mapping[str, Any]) -> Mapping[str, str] | None:
    distributor = value(row, "分销商")
    if distributor:
        return {"customer_id": distributor}
    shop = value(row, "店铺")
    if not shop:
        return None
    if "童鞋" in shop:
        customer_id = "童鞋"
    elif "晨秋" in shop:
        customer_id = "晨秋"
    elif "老爸评测" in shop:
        customer_id = "老爸评测"
    elif any(keyword in shop for keyword in ("阿里巴巴", "京东商城", "拼多多", "奇门Wms", "淘宝天猫", "头条放心购", "小红书")):
        customer_id = "戎井"
    else:
        customer_id = shop
    return {"customer_id": customer_id}


STORE_TABLES = (
    "daily_sales",
    "daily_product_sales",
    "daily_customer_sales",
    "weekly_sales",
    "weekly_refunds",
    "weekly_product_sales",
    "weekly_customer_sales",
    "monthly_sales",
    "monthly_refunds",
    "monthly_product_sales",
    "monthly_customer_sales",
    "quarterly_sales",
    "quarterly_refunds",
    "quarterly_product_sales",
    "quarterly_customer_sales",
    "half_year_sales",
    "half_year_refunds",
    "half_year_product_sales",
    "half_year_customer_sales",
    "daily_sales_metrics",
    "weekly_sales_metrics",
    "monthly_sales_metrics",
    "customer_daily_sales",
    "customer_daily_sales_metrics",
    "customer_weekly_sales",
    "customer_monthly_sales",
    "customer_quarterly_sales",
    "customer_half_year_sales",
    "customer_daily_product_sales",
    "customer_monthly_product_sales",
    "customer_quarterly_product_sales",
    "customer_half_year_product_sales",
    "customer_health_detail",
)


def aggregate_path(group_key: str, platform_key: str) -> tuple[str, ...]:
    result: list[str] = []
    if platform_key in {"doudian", "youzan"}:
        result.append(platform_key)
    result.extend(({"talent": "daren", "private": "siyu", "distribution": "fenxiao"}[group_key], "qudao"))
    return tuple(result)
