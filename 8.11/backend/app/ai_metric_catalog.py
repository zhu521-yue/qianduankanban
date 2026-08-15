from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.responses import ApiError


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    grains: tuple[str, ...]
    group_bys: tuple[str, ...]
    filters: tuple[str, ...]
    max_limit: int
    default_group_by: str
    default_output_type: str
    target_module: str


METRIC_CATALOG: dict[str, MetricDefinition] = {
    "sales_amount": MetricDefinition(
        "sales_amount", "销售额", ("day", "week", "month", "quarter", "half"),
        ("total", "group", "platform", "store"), (), 20, "total", "cards", "sales",
    ),
    "sales_change_rate": MetricDefinition(
        "sales_change_rate", "销售额周期变化", ("day", "week", "month", "quarter", "half"),
        ("total", "group", "platform", "store"), (), 20, "store", "bar", "sales",
    ),
    "sales_trend": MetricDefinition(
        "sales_trend", "销售趋势", ("day", "week", "month", "quarter", "half"),
        ("period",), (), 24, "period", "line", "sales",
    ),
    "scope_contribution": MetricDefinition(
        "scope_contribution", "销售贡献", ("day", "week", "month", "quarter", "half"),
        ("group", "platform", "store"), (), 20, "store", "bar", "sales",
    ),
    "active_customer_count": MetricDefinition(
        "active_customer_count", "购买客户数", ("day", "week", "month", "quarter", "half"),
        ("total", "store"), (), 20, "total", "cards", "customers",
    ),
    "customer_ranking": MetricDefinition(
        "customer_ranking", "客户销售排名", ("day", "week", "month", "quarter", "half"),
        ("customer",), ("health_status",), 100, "customer", "table", "customers",
    ),
    "customer_health_count": MetricDefinition(
        "customer_health_count", "客户健康分布", ("week",),
        ("health_status", "store"), ("health_status",), 20, "health_status", "bar", "health",
    ),
    "top_product_amount": MetricDefinition(
        "top_product_amount", "商品金额排名", ("day", "week", "month", "quarter", "half"),
        ("product",), (), 20, "product", "bar", "products",
    ),
    "top_product_quantity": MetricDefinition(
        "top_product_quantity", "商品数量排名", ("day", "week", "month", "quarter", "half"),
        ("product",), (), 20, "product", "bar", "products",
    ),
    "refund_amount": MetricDefinition(
        "refund_amount", "退款金额", ("week", "month", "quarter", "half"),
        ("total", "group", "platform", "store"), (), 20, "store", "bar", "refund",
    ),
    "presale_amount": MetricDefinition(
        "presale_amount", "微店预售", ("month", "quarter", "half"),
        ("total", "product"), (), 20, "product", "bar", "presale",
    ),
    "data_freshness": MetricDefinition(
        "data_freshness", "数据新鲜度", ("day",),
        ("store",), (), 20, "store", "table", "freshness",
    ),
}


def validate_query_plan(plan: dict[str, Any]) -> MetricDefinition:
    metric_key = str(plan.get("metric_key") or "")
    definition = METRIC_CATALOG.get(metric_key)
    if not definition:
        raise ApiError(
            422,
            "AI_QUERY_UNSUPPORTED",
            "当前问题超出首版指标范围，请询问销售、退款、客户、健康、商品、预售或数据日期。",
        )
    grain = str(plan.get("grain") or "")
    if grain not in definition.grains:
        raise ApiError(422, "AI_QUERY_UNSUPPORTED", f"{definition.label}暂不支持{grain}粒度。")
    group_by = str(plan.get("group_by") or definition.default_group_by)
    if group_by not in definition.group_bys:
        raise ApiError(422, "AI_QUERY_UNSUPPORTED", f"{definition.label}暂不支持按{group_by}展示。")
    filters = plan.get("filters") or {}
    if not isinstance(filters, dict) or any(key not in definition.filters for key in filters):
        raise ApiError(422, "AI_QUERY_UNSUPPORTED", f"{definition.label}包含未登记的筛选条件。")
    limit = int(plan.get("limit") or 1)
    if limit < 1 or limit > definition.max_limit:
        raise ApiError(422, "AI_QUERY_UNSUPPORTED", f"{definition.label}最多返回{definition.max_limit}条结果。")
    return definition


def catalog_prompt() -> list[dict[str, Any]]:
    return [
        {
            "metric_key": item.key,
            "label": item.label,
            "grains": list(item.grains),
            "group_bys": list(item.group_bys),
            "filters": list(item.filters),
            "max_limit": item.max_limit,
        }
        for item in METRIC_CATALOG.values()
    ]
