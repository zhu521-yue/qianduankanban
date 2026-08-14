from datetime import date
from decimal import Decimal
from math import ceil
from typing import Any

from psycopg import Connection

from app.catalog import CUSTOMER_HEALTH_STATUSES, HEALTH_RULE_GROUPS, STORES, allowed_stores, resolve_scope
from app.periods import Grain, period_window, previous_window, recent_windows
from app.repositories import CustomerRepository, DashboardRepository, SettingsRepository, amount_text
from app.responses import ApiError
from app.schemas import UserContext
from app.settings import get_settings


HEALTH_ORDER = [*CUSTOMER_HEALTH_STATUSES, "未评分"]
HEALTH_COLORS = {
    "高活跃": "#67e8f9",
    "活跃": "#60a5fa",
    "稳定": "#34d399",
    "观察": "#facc15",
    "风险": "#fb923c",
    "流失预警": "#fb7185",
    "流失": "#9f6f89",
    "未评分": "#94a3b8",
}


def ratio(current: Decimal | int, previous: Decimal | int) -> float | None:
    previous_decimal = Decimal(previous)
    if previous_decimal == 0:
        return None
    return float((Decimal(current) - previous_decimal) / previous_decimal)


def serialize_product(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_code": row["product_code"],
        "quantity": str(row["quantity"]),
        "amount": amount_text(row["amount"]),
    }


class DashboardService:
    def __init__(self, conn: Connection):
        self.repo = DashboardRepository(conn)

    def latest_date(self, user: UserContext, scope_key: str) -> date:
        stores = resolve_scope(user.role, scope_key)
        latest = self.repo.latest_data_date(stores)
        if not latest:
            raise ApiError(404, "DATA_NOT_FOUND", "当前范围没有可展示的销售数据。")
        return latest

    def dashboard(self, user: UserContext, scope_key: str, as_of: date, trend_grain: Grain, refund_grain: Grain) -> dict[str, Any]:
        stores = resolve_scope(user.role, scope_key)
        half = period_window(Grain.HALF, as_of)
        month = period_window(Grain.MONTH, as_of)
        half_previous = previous_window(period_window(Grain.HALF, as_of))
        month_previous = previous_window(period_window(Grain.MONTH, as_of))
        half_sales = self.repo.sales_amount(stores, Grain.HALF, half)
        month_sales = self.repo.sales_amount(stores, Grain.MONTH, month)
        prev_half_sales = self.repo.sales_amount(stores, Grain.HALF, half_previous)
        prev_month_sales = self.repo.sales_amount(stores, Grain.MONTH, month_previous)
        customer_count = self.repo.active_customer_count(stores, Grain.HALF, half)
        product_count = self.repo.product_count(stores, Grain.HALF, half)
        health_week = period_window(Grain.WEEK, as_of)

        trend = []
        for window in recent_windows(trend_grain, as_of, 6):
            value = self.repo.sales_amount(stores, trend_grain, window)
            trend.append({"start": window.start.isoformat(), "end": window.end.isoformat(), "label": window.label, "amount": amount_text(value)})

        health_rows = {row["status"]: int(row["count"]) for row in self.repo.health_distribution(stores, health_week, as_of)}
        health_statuses = [*HEALTH_ORDER, *sorted(status for status in health_rows if status not in HEALTH_ORDER)]
        health = [
            {"status": status, "count": health_rows.get(status, 0), "color": HEALTH_COLORS.get(status, HEALTH_COLORS["未评分"])}
            for status in health_statuses
            if health_rows.get(status, 0) > 0 or status != "未评分"
        ]
        healthy = sum(item["count"] for item in health if item["status"] in {"高活跃", "活跃", "稳定"})
        health_total = sum(item["count"] for item in health)

        quantity_top = [serialize_product(row) for row in self.repo.top_products(stores, Grain.HALF, half, "quantity")]
        amount_top = [serialize_product(row) for row in self.repo.top_products(stores, Grain.HALF, half, "amount")]
        double_top = len({item["product_code"] for item in quantity_top} & {item["product_code"] for item in amount_top})

        refund_current = period_window(refund_grain, as_of)
        refund_previous = previous_window(period_window(refund_grain, as_of))
        refund_amount = self.repo.refund_amount(stores, refund_grain, refund_current)
        previous_refund_amount = self.repo.refund_amount(stores, refund_grain, refund_previous)
        refund_series = []
        for window in recent_windows(refund_grain, as_of, 6):
            value = self.repo.refund_amount(stores, refund_grain, window)
            refund_series.append({"start": window.start.isoformat(), "end": window.end.isoformat(), "amount": amount_text(value)})

        presale = self.repo.presale_summary(stores, Grain.HALF, half)
        latest = self.repo.latest_data_date(stores)
        return {
            "scope_key": scope_key,
            "store_keys": list(stores),
            "as_of": as_of.isoformat(),
            "latest_data_date": latest.isoformat() if latest else None,
            "kpis": [
                {"key": "half_sales", "label": "半年销售额", "value": amount_text(half_sales), "change": ratio(half_sales, prev_half_sales), "period": half.label},
                {"key": "month_sales", "label": "本月销售额", "value": amount_text(month_sales), "change": ratio(month_sales, prev_month_sales), "period": month.label},
                {"key": "half_customers", "label": "半年客户数", "value": customer_count, "change": None, "period": half.label},
                {"key": "half_products", "label": "半年高频商品", "value": product_count, "change": None, "period": half.label},
            ],
            "sales_trend": {"grain": trend_grain.value, "series": trend},
            "customer_health": {
                "period": {
                    "start": health_week.start.isoformat(),
                    "end": health_week.end.isoformat(),
                    "label": health_week.label,
                },
                "total": health_total,
                "healthy_count": healthy,
                "healthy_ratio": healthy / health_total if health_total else None,
                "items": health,
            },
            "top_products": {"period": half.label, "by_quantity": quantity_top, "by_amount": amount_top, "double_top_count": double_top},
            "refund": {
                "grain": refund_grain.value,
                "current": amount_text(refund_amount),
                "previous": amount_text(previous_refund_amount),
                "change": ratio(refund_amount, previous_refund_amount),
                "period": refund_current.label,
                "series": refund_series,
            },
            "presale": {
                "available": Decimal(presale["amount"]) > 0,
                "period": half.label,
                "amount": amount_text(presale["amount"]),
                "quantity": str(presale["quantity"]),
                "product_count": int(presale["product_count"]),
                "products": [serialize_product(row) for row in presale["products"]],
            },
        }


class CustomerService:
    def __init__(self, conn: Connection):
        self.repo = CustomerRepository(conn)

    def list_customers(
        self,
        user: UserContext,
        scope_key: str,
        as_of: date,
        grain: Grain,
        search: str | None,
        status: str | None,
        sort_by: str,
        sort_order: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        stores = resolve_scope(user.role, scope_key)
        window = period_window(grain, as_of)
        rows, total = self.repo.list_page(stores, grain, window, as_of, search, status, sort_by, sort_order, page, page_size)
        items = [
            {
                **row,
                "period_amount": amount_text(row["period_amount"]),
                "purchase_count": int(row["purchase_count"]),
                "score": float(row["score"] or 0),
                "store_name": STORES[row["store_key"]].name,
            }
            for row in rows
        ]
        return {
            "items": items,
            "period": {"grain": grain.value, "start": window.start.isoformat(), "end": window.end.isoformat()},
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": ceil(total / page_size) if total else 0,
                "has_previous": page > 1,
                "has_next": page * page_size < total,
            },
        }

    def detail(self, user: UserContext, store_key: str, customer_id: str, as_of: date) -> dict[str, Any]:
        if store_key not in set(allowed_stores(user.role)):
            raise ApiError(403, "STORE_FORBIDDEN", "当前账号无权查看该店铺客户。")
        customer = self.repo.get_customer(store_key, customer_id, as_of)
        if not customer:
            raise ApiError(404, "CUSTOMER_NOT_FOUND", "未找到该客户。")
        dimensions = {}
        for grain in Grain:
            window = period_window(grain, as_of)
            sales = self.repo.customer_sales(store_key, customer_id, grain, window)
            products = self.repo.customer_products(store_key, customer_id, grain, window)
            dimensions[grain.value] = {
                "start": window.start.isoformat(),
                "end": window.end.isoformat(),
                "sales_amount": amount_text(sales["amount"]),
                "purchase_count": int(sales["purchase_count"]),
                "products": [serialize_product(row) for row in products],
            }
        return {
            **customer,
            "score": float(customer["score"] or 0),
            "status": customer["status"] or "未评分",
            "store_name": STORES[store_key].name,
            "as_of": as_of.isoformat(),
            "dimensions": dimensions,
        }


class SettingsService:
    def __init__(self, conn: Connection):
        self.conn = conn
        self.repo = SettingsRepository(conn)

    def health_rules(self, user: UserContext) -> list[dict[str, Any]]:
        group_keys = () if user.role == "manager" else (user.group_key,)
        return [
            {
                "group_key": group_key,
                "group_name": HEALTH_RULE_GROUPS[group_key].name,
                "editable": user.role != "manager",
                "items": self.repo.health_rules(group_key),
            }
            for group_key in group_keys
            if group_key in HEALTH_RULE_GROUPS
        ]

    def update_health_rules(self, user: UserContext, rules: list[dict[str, Any]]) -> dict[str, Any]:
        if user.role == "manager":
            raise ApiError(403, "SETTINGS_FORBIDDEN", "主管端没有客户状态规则设置权限。")
        if user.group_key not in HEALTH_RULE_GROUPS:
            raise ApiError(403, "ROLE_FORBIDDEN", "当前账号没有可维护的客户状态规则。")
        statuses = tuple(rule["customer_health_status"] for rule in rules)
        if statuses != CUSTOMER_HEALTH_STATUSES:
            raise ApiError(
                422,
                "HEALTH_RULE_STATUS_INVALID",
                "客户状态必须依次为：高活跃、活跃、稳定、观察、风险、流失预警、流失。",
            )
        normalized_rules = []
        for rule in rules:
            state_instructions = rule["state_instructions"].strip()
            follow_up_action = rule["follow_up_action"].strip()
            if not state_instructions or not follow_up_action:
                raise ApiError(422, "HEALTH_RULE_CONTENT_REQUIRED", "状态说明和建议跟进动作不能为空。")
            normalized_rules.append(
                {
                    **rule,
                    "state_instructions": state_instructions,
                    "follow_up_action": follow_up_action,
                }
            )
        return self.repo.update_health_rules(user.group_key, normalized_rules)

    def api_setting(self, user: UserContext, include_secret: bool = False) -> dict[str, Any]:
        settings = get_settings()
        result = {
            "scope_key": "manager" if user.role == "manager" else user.group_key,
            "base_url": settings.ai_base_url,
            "model_name": settings.ai_model_name or None,
            "api_key_masked": "••••••••" if settings.ai_api_key else "",
            "configured": bool(settings.ai_base_url and settings.ai_api_key),
        }
        if include_secret and settings.ai_api_key:
            result["api_key"] = settings.ai_api_key
        return result

    def update_api_setting(self, user: UserContext, base_url: str, api_key: str | None, model_name: str | None) -> None:
        raise ApiError(409, "SETTINGS_READ_ONLY", "AI 接口配置请写入后端 .env，避免由浏览器修改服务端密钥。")
