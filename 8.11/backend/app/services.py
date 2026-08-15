import json
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
from app.settings import ai_settings_for_role, get_settings, save_ai_settings_for_role


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


REFUND_SOURCE_TABLES = {
    "day": "daily_refunds",
    "week": "weekly_refunds",
    "month": "monthly_refunds",
    "quarter": "quarterly_refunds",
    "half": "half_year_refunds",
}


def _decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (ArithmeticError, ValueError):
        return Decimal(0)


def _percent_text(value: float) -> str:
    return f"{value * 100:+.1f}%"


def build_dashboard_insight(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic, source-backed summary from dashboard data."""
    kpis = {item["key"]: item for item in snapshot.get("kpis", [])}
    month_sales = kpis.get("month_sales", {})
    half_sales = kpis.get("half_sales", {})
    month_amount = _decimal_value(month_sales.get("value"))
    half_amount = _decimal_value(half_sales.get("value"))
    month_change = month_sales.get("change")
    refund = snapshot.get("refund", {})
    refund_amount = _decimal_value(refund.get("current"))
    refund_change = refund.get("change")
    health = snapshot.get("customer_health", {})
    health_total = int(health.get("total") or 0)
    risk_count = sum(
        int(item.get("count") or 0)
        for item in health.get("items", [])
        if item.get("status") in {"风险", "流失预警", "流失"}
    )
    risk_ratio = risk_count / health_total if health_total else None
    amount_products = snapshot.get("top_products", {}).get("by_amount", [])
    top_product = amount_products[0] if amount_products else None
    top_product_amount = _decimal_value(top_product.get("amount")) if top_product else Decimal(0)
    concentration = float(top_product_amount / half_amount) if top_product and half_amount > 0 else None
    presale = snapshot.get("presale", {})
    has_data = any((month_amount > 0, half_amount > 0, refund_amount > 0, health_total > 0, bool(amount_products), presale.get("available")))

    evidence: list[dict[str, Any]] = []
    actions: list[dict[str, str]] = []
    warnings: list[str] = []

    if not has_data:
        return {
            "empty": True,
            "headline": "当前范围暂无足够经营数据",
            "summary": "当前统计范围内没有足够的销售、退款、客户健康度或商品数据，暂不生成方向性结论。",
            "evidence": [],
            "actions": [],
            "warnings": ["请确认所选范围、统计日期及数据库数据是否完整。"],
        }

    if month_change is None:
        evidence.append(
            {
                "key": "month_sales",
                "label": "本月销售额",
                "value": str(month_sales.get("value") or "0.00"),
                "period": str(month_sales.get("period") or "当前月"),
                "source": "monthly_sales",
                "direction": "neutral",
                "severity": "info",
                "description": "本月销售额已有记录，但上一周期为零或缺少数据，暂不能计算可靠环比。",
            }
        )
        warnings.append("本月销售额缺少可比的上一周期数据，未计算销售环比。")
    else:
        month_change_value = float(month_change)
        if month_change_value <= -0.05:
            direction, severity = "negative", "high"
            description = f"本月销售额较上一周期下降 {abs(month_change_value) * 100:.1f}%，销售表现承压。"
            actions.append({"priority": "high", "title": "检查销售下滑来源", "description": "对照渠道、店铺与头部商品，确认下滑集中在哪个经营环节。"})
        elif month_change_value < 0:
            direction, severity = "negative", "medium"
            description = f"本月销售额较上一周期小幅下降 {abs(month_change_value) * 100:.1f}%，建议继续观察。"
            actions.append({"priority": "medium", "title": "跟踪销售变化", "description": "关注后续销售趋势，确认小幅回落是否持续。"})
        elif month_change_value >= 0.05:
            direction, severity = "positive", "info"
            description = f"本月销售额较上一周期增长 {month_change_value * 100:.1f}%，经营规模正在提升。"
            actions.append({"priority": "low", "title": "复盘增长来源", "description": "核对增长主要来自哪些店铺和商品，沉淀可复用的经营动作。"})
        else:
            direction, severity = "neutral", "info"
            description = f"本月销售额环比 {_percent_text(month_change_value)}，整体保持相对稳定。"
        evidence.append(
            {
                "key": "month_sales_change",
                "label": "本月销售额环比",
                "value": _percent_text(month_change_value),
                "period": str(month_sales.get("period") or "当前月"),
                "source": "monthly_sales",
                "direction": direction,
                "severity": severity,
                "description": description,
            }
        )

    refund_grain = str(refund.get("grain") or "half")
    if refund_change is None:
        if refund_amount > 0:
            evidence.append(
                {
                    "key": "refund_amount",
                    "label": "退款金额",
                    "value": str(refund.get("current") or "0.00"),
                    "period": str(refund.get("period") or "当前周期"),
                    "source": REFUND_SOURCE_TABLES.get(refund_grain, "refund aggregate"),
                    "direction": "neutral",
                    "severity": "info",
                    "description": "当前周期存在退款记录，但上一周期为零或缺少数据，暂不能计算退款环比。",
                }
            )
            warnings.append("退款数据缺少可比的上一周期记录，未计算退款环比。")
    else:
        refund_change_value = float(refund_change)
        if refund_change_value >= 0.10:
            direction, severity = "negative", "high"
            description = f"退款金额较上一周期上升 {refund_change_value * 100:.1f}%，需要优先核查。"
            actions.append({"priority": "high", "title": "检查退款上升原因", "description": "优先核对退款贡献较高的商品和订单，确认售后或商品问题。"})
        elif refund_change_value > 0:
            direction, severity = "negative", "medium"
            description = f"退款金额较上一周期上升 {refund_change_value * 100:.1f}%，建议持续关注。"
            actions.append({"priority": "medium", "title": "关注退款变化", "description": "跟踪退款订单与商品，避免风险继续扩大。"})
        elif refund_change_value <= -0.10:
            direction, severity = "positive", "info"
            description = f"退款金额较上一周期下降 {abs(refund_change_value) * 100:.1f}%，退款压力有所缓解。"
        else:
            direction, severity = "neutral", "info"
            description = f"退款金额环比 {_percent_text(refund_change_value)}，整体变化不大。"
        evidence.append(
            {
                "key": "refund_change",
                "label": "退款金额环比",
                "value": _percent_text(refund_change_value),
                "period": str(refund.get("period") or "当前周期"),
                "source": REFUND_SOURCE_TABLES.get(refund_grain, "refund aggregate"),
                "direction": direction,
                "severity": severity,
                "description": description,
            }
        )

    if risk_ratio is not None:
        if risk_ratio >= 0.20:
            severity = "high"
            description = f"风险、流失预警及流失客户共 {risk_count} 个，占已评分客户 {risk_ratio * 100:.1f}%。"
            actions.append({"priority": "high", "title": "安排风险客户跟进", "description": "按风险原因和客户贡献排序，优先处理高价值风险客户。"})
        elif risk_ratio >= 0.10:
            severity = "medium"
            description = f"风险、流失预警及流失客户共 {risk_count} 个，占已评分客户 {risk_ratio * 100:.1f}%。"
            actions.append({"priority": "medium", "title": "关注风险客户", "description": "检查风险客户状态说明并安排分层跟进。"})
        else:
            severity = "info"
            description = f"风险、流失预警及流失客户共 {risk_count} 个，占已评分客户 {risk_ratio * 100:.1f}%。"
        evidence.append(
            {
                "key": "risk_customers",
                "label": "风险客户占比",
                "value": f"{risk_ratio * 100:.1f}%",
                "period": str(health.get("period", {}).get("label") or "自然周"),
                "source": "customer_weekly_sales + customer_health_detail",
                "direction": "negative" if risk_count else "positive",
                "severity": severity,
                "description": description,
            }
        )

    if concentration is not None:
        if concentration >= 0.50:
            severity = "medium"
            description = f"销售额第一商品 {top_product['product_code']} 占半年销售额 {concentration * 100:.1f}%，单品集中度较高。"
            actions.append({"priority": "medium", "title": "关注头部商品依赖", "description": "检查头部商品库存、售后和替代商品，降低单品波动影响。"})
        else:
            severity = "info"
            description = f"销售额第一商品 {top_product['product_code']} 占半年销售额 {concentration * 100:.1f}%。"
        evidence.append(
            {
                "key": "top_product_concentration",
                "label": "头部商品贡献",
                "value": f"{concentration * 100:.1f}%",
                "period": str(snapshot.get("top_products", {}).get("period") or "半年"),
                "source": "half_year_product_sales",
                "direction": "negative" if concentration >= 0.50 else "neutral",
                "severity": severity,
                "description": description,
            }
        )

    latest_data_date = snapshot.get("latest_data_date")
    as_of = snapshot.get("as_of")
    if latest_data_date and as_of and latest_data_date < as_of:
        warnings.append(f"所选统计日期为 {as_of}，当前数据库最新数据为 {latest_data_date}。")

    evidence = evidence[:4]
    priority_order = {"high": 0, "medium": 1, "low": 2}
    unique_actions: list[dict[str, str]] = []
    seen_titles: set[str] = set()
    for action in sorted(actions, key=lambda item: priority_order[item["priority"]]):
        if action["title"] not in seen_titles:
            unique_actions.append(action)
            seen_titles.add(action["title"])
    if not unique_actions:
        unique_actions.append({"priority": "low", "title": "保持周期复盘", "description": "继续按当前统计范围观察销售、退款与客户健康度变化。"})

    negative_sales = month_change is not None and float(month_change) <= -0.05
    rising_refunds = refund_change is not None and float(refund_change) >= 0.10
    high_customer_risk = risk_ratio is not None and risk_ratio >= 0.20
    growing_sales = month_change is not None and float(month_change) >= 0.05
    if negative_sales and rising_refunds:
        headline = "销售承压且退款上升，建议优先排查经营风险"
    elif negative_sales:
        headline = "本月销售出现下滑，需要定位主要影响来源"
    elif rising_refunds:
        headline = "销售表现需结合退款上升情况谨慎判断"
    elif high_customer_risk:
        headline = "风险客户占比较高，需要安排分层跟进"
    elif growing_sales:
        headline = "本月销售保持增长，建议复盘增长来源"
    else:
        headline = "核心经营指标整体平稳，继续关注周期变化"
    summary = "".join(item["description"] for item in evidence[:3])
    return {
        "empty": False,
        "headline": headline,
        "summary": summary,
        "evidence": evidence,
        "actions": unique_actions[:3],
        "warnings": warnings,
    }


def dashboard_insight_messages(insight: dict[str, Any]) -> list[dict[str, str]]:
    evidence_payload = json.dumps(insight.get("evidence", []), ensure_ascii=False, separators=(",", ":"))
    return [
        {
            "role": "system",
            "content": (
                "你是经营看板摘要助手。只能依据后端提供的证据润色摘要，不得增加、修改或推测任何数字，"
                "不得生成证据之外的事实。请输出2至4句中文纯文本，不使用标题、列表或Markdown，控制在300字以内。"
            ),
        },
        {
            "role": "user",
            "content": f"规则结论：{insight.get('headline', '')}\n规则摘要：{insight.get('summary', '')}\n数据证据：{evidence_payload}",
        },
    ]


def normalize_ai_summary(answer: str, fallback: str) -> str:
    normalized = " ".join(answer.replace("```", "").split()).strip()
    return normalized[:500] if normalized else fallback


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
        self.conn = conn
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

    def analysis_snapshot(
        self,
        user: UserContext,
        store_key: str,
        customer_id: str,
        as_of: date,
        *,
        include_store_refund: bool = False,
    ) -> dict[str, Any]:
        customer = self.detail(user, store_key, customer_id, as_of)
        store = STORES[store_key]
        comparisons: dict[str, Any] = {}
        for grain in (Grain.MONTH, Grain.QUARTER, Grain.HALF):
            current_window = period_window(grain, as_of)
            previous_period = previous_window(current_window)
            current = self.repo.customer_sales(store_key, customer_id, grain, current_window)
            previous = self.repo.customer_sales(store_key, customer_id, grain, previous_period)
            current_amount = Decimal(current["amount"] or 0)
            previous_amount = Decimal(previous["amount"] or 0)
            current_count = int(current["purchase_count"] or 0)
            previous_count = int(previous["purchase_count"] or 0)
            comparisons[grain.value] = {
                "current": {
                    "start": current_window.start.isoformat(),
                    "end": current_window.end.isoformat(),
                    "amount": amount_text(current_amount),
                    "purchase_count": current_count,
                },
                "previous": {
                    "start": previous_period.start.isoformat(),
                    "end": previous_period.end.isoformat(),
                    "amount": amount_text(previous_amount),
                    "purchase_count": previous_count,
                },
                "amount_change": ratio(current_amount, previous_amount),
                "purchase_change": ratio(current_count, previous_count),
            }

        products: dict[str, Any] = {}
        for grain in (Grain.MONTH, Grain.HALF):
            rows = customer["dimensions"][grain.value]["products"]
            total_amount = Decimal(comparisons[grain.value]["current"]["amount"])
            top_one = sum((Decimal(item["amount"]) for item in rows[:1]), Decimal(0))
            top_three = sum((Decimal(item["amount"]) for item in rows[:3]), Decimal(0))
            products[grain.value] = {
                "items": rows,
                "top1_amount_ratio": float(top_one / total_amount) if total_amount > 0 else None,
                "top3_amount_ratio": float(top_three / total_amount) if total_amount > 0 else None,
                "source": f"{store.schema_name}.customer_{'monthly' if grain == Grain.MONTH else 'half_year'}_product_sales",
            }

        health_rules = SettingsRepository(self.conn).health_rules(store.group_key)
        health_rule = next((rule for rule in health_rules if rule["customer_health_status"] == customer["status"]), None)
        health_period_start = customer.get("period_start")
        health_period_end = customer.get("period_end")
        health_stale_days = (as_of - health_period_end).days if health_period_end and health_period_end < as_of else 0
        health = {
            "score": customer["score"],
            "status": customer["status"],
            "snapshot_explanation": customer.get("risk_reason"),
            "snapshot_action": customer.get("suggested_action"),
            "period_start": health_period_start.isoformat() if health_period_start else None,
            "period_end": health_period_end.isoformat() if health_period_end else None,
            "stale_days": health_stale_days,
            "source": f"{store.schema_name}.customer_health_detail",
            "rule": {
                "state_instructions": health_rule["state_instructions"],
                "follow_up_action": health_rule["follow_up_action"],
                "source": f"public.{HEALTH_RULE_GROUPS[store.group_key].table_name}",
            } if health_rule else None,
        }

        refund_background = None
        if include_store_refund:
            refund_window = period_window(Grain.MONTH, as_of)
            refund_previous = previous_window(refund_window)
            dashboard_repo = DashboardRepository(self.conn)
            refund_current_amount = dashboard_repo.refund_amount((store_key,), Grain.MONTH, refund_window)
            refund_previous_amount = dashboard_repo.refund_amount((store_key,), Grain.MONTH, refund_previous)
            refund_background = {
                "level": "store",
                "store_key": store_key,
                "store_name": store.name,
                "current": amount_text(refund_current_amount),
                "previous": amount_text(refund_previous_amount),
                "change": ratio(refund_current_amount, refund_previous_amount),
                "period": refund_window.label,
                "source": f"{store.schema_name}.monthly_refunds",
            }

        return {
            "store_key": store_key,
            "store_name": store.name,
            "store_schema": store.schema_name,
            "group_key": store.group_key,
            "customer_id": customer_id,
            "display_name": customer["display_name"],
            "as_of": as_of.isoformat(),
            "comparisons": comparisons,
            "products": products,
            "health": health,
            "refund_background": refund_background,
        }


CUSTOMER_ANALYSIS_TYPES = {
    "overview",
    "recent_performance",
    "health_reason",
    "products",
    "store_refund",
    "follow_up",
}


def infer_customer_analysis_type(message: str) -> str:
    normalized = message.strip().lower()
    if "退款" in normalized:
        return "store_refund"
    if any(keyword in normalized for keyword in ("健康", "状态", "风险", "流失")):
        return "health_reason"
    if any(keyword in normalized for keyword in ("商品", "产品", "sku")):
        return "products"
    if any(keyword in normalized for keyword in ("建议", "跟进", "优先", "核查")):
        return "follow_up"
    if any(keyword in normalized for keyword in ("最近", "表现", "销售", "拿货", "采购")):
        return "recent_performance"
    return "overview"


def is_customer_communication_request(message: str) -> bool:
    normalized = message.strip().lower()
    return any(
        keyword in normalized
        for keyword in ("回复客户", "怎么回复", "沟通话术", "客户话术", "营销文案", "发给客户", "给客户发", "联系客户怎么说")
    )


def build_customer_analysis(snapshot: dict[str, Any], analysis_type: str = "overview") -> dict[str, Any]:
    if analysis_type not in CUSTOMER_ANALYSIS_TYPES:
        raise ApiError(400, "CUSTOMER_ANALYSIS_TYPE_INVALID", "不支持的客户分析类型。")
    comparisons = snapshot["comparisons"]
    health = snapshot["health"]
    products = snapshot["products"]
    evidence: list[dict[str, Any]] = []
    warnings: list[str] = []
    actions: list[dict[str, str]] = []
    source_names = {
        "month": "customer_monthly_sales",
        "quarter": "customer_quarterly_sales",
        "half": "customer_half_year_sales",
    }
    grain_labels = {"month": "本月", "quarter": "本季度", "half": "本半年"}

    def comparison_evidence(grain: str) -> dict[str, Any]:
        comparison = comparisons[grain]
        current = comparison["current"]
        change = comparison["amount_change"]
        if change is None:
            if Decimal(current["amount"]) > 0:
                description = f"{grain_labels[grain]}销售额为 {current['amount']} 元，但上一周期为零或缺少数据，暂不能计算可靠环比。"
                warnings.append(f"{grain_labels[grain]}销售额缺少可比的上一周期数据。")
            else:
                description = f"{grain_labels[grain]}没有有效销售金额记录。"
            value = current["amount"]
            value_type = "currency"
            direction = "neutral"
            severity = "info"
        else:
            change_value = float(change)
            value = _percent_text(change_value)
            value_type = "percentage"
            if change_value <= -0.10:
                direction, severity = "negative", "high"
                description = f"{grain_labels[grain]}销售额较上一周期下降 {abs(change_value) * 100:.1f}%。"
            elif change_value < 0:
                direction, severity = "negative", "medium"
                description = f"{grain_labels[grain]}销售额较上一周期小幅下降 {abs(change_value) * 100:.1f}%。"
            elif change_value >= 0.10:
                direction, severity = "positive", "info"
                description = f"{grain_labels[grain]}销售额较上一周期增长 {change_value * 100:.1f}%。"
            else:
                direction, severity = "neutral", "info"
                description = f"{grain_labels[grain]}销售额环比 {_percent_text(change_value)}，变化相对平稳。"
        return {
            "key": f"{grain}_sales_change",
            "label": f"{grain_labels[grain]}销售变化",
            "value": value,
            "value_type": value_type,
            "period": f"{current['start']}—{current['end']}",
            "source": f"{snapshot['store_schema']}.{source_names[grain]}",
            "direction": direction,
            "severity": severity,
            "description": description,
        }

    def purchase_evidence() -> dict[str, Any]:
        comparison = comparisons["month"]
        current = comparison["current"]
        change = comparison["purchase_change"]
        if change is None:
            description = f"本月拿货次数为 {current['purchase_count']} 次，上一周期缺少可比记录。"
            value = str(current["purchase_count"])
            value_type = "number"
            direction, severity = "neutral", "info"
        else:
            change_value = float(change)
            value = _percent_text(change_value)
            value_type = "percentage"
            direction = "negative" if change_value < 0 else "positive" if change_value > 0 else "neutral"
            severity = "medium" if change_value <= -0.20 else "info"
            description = f"本月拿货次数为 {current['purchase_count']} 次，较上一月 {_percent_text(change_value)}。"
        return {
            "key": "month_purchase_change",
            "label": "本月拿货次数变化",
            "value": value,
            "value_type": value_type,
            "period": f"{current['start']}—{current['end']}",
            "source": f"{snapshot['store_schema']}.customer_monthly_sales",
            "direction": direction,
            "severity": severity,
            "description": description,
        }

    health_rule = health.get("rule")
    health_description = (
        str(health_rule.get("state_instructions") or "").strip()
        if health_rule
        else str(health.get("snapshot_explanation") or "当前没有可用的健康状态说明。")
    )
    health_evidence = {
        "key": "health_status",
        "label": "客户健康状态",
        "value": str(health["status"]),
        "value_type": "text",
        "period": f"{health.get('period_start') or '未知'}—{health.get('period_end') or '未知'}",
        "source": str(health["source"]),
        "direction": "negative" if health["status"] in {"风险", "流失预警", "流失"} else "neutral",
        "severity": "high" if health["status"] in {"流失预警", "流失"} else "medium" if health["status"] == "风险" else "info",
        "description": f"当前健康度 {float(health['score']):.0f}，状态为{health['status']}。{health_description}",
    }

    def product_evidence(grain: str) -> dict[str, Any] | None:
        product_data = products[grain]
        items = product_data["items"]
        if not items:
            return None
        concentration = product_data["top3_amount_ratio"]
        top_codes = "、".join(str(item["product_code"]) for item in items[:3])
        concentration_text = f"{float(concentration) * 100:.1f}%" if concentration is not None else "无法计算"
        return {
            "key": f"{grain}_product_concentration",
            "label": f"{grain_labels[grain]}主要商品",
            "value": concentration_text,
            "value_type": "percentage" if concentration is not None else "text",
            "period": f"{comparisons[grain]['current']['start']}—{comparisons[grain]['current']['end']}",
            "source": product_data["source"],
            "direction": "negative" if concentration is not None and float(concentration) >= 0.70 else "neutral",
            "severity": "medium" if concentration is not None and float(concentration) >= 0.70 else "info",
            "description": f"金额排名前三的商品编码为 {top_codes}，合计占该客户同期销售额 {concentration_text}。",
        }

    if analysis_type in {"overview", "follow_up"}:
        evidence.extend([comparison_evidence("month"), health_evidence, comparison_evidence("half")])
        item = product_evidence("half")
        if item:
            evidence.append(item)
    elif analysis_type == "recent_performance":
        evidence.extend([comparison_evidence("month"), purchase_evidence(), comparison_evidence("quarter"), comparison_evidence("half")])
    elif analysis_type == "health_reason":
        evidence.extend([health_evidence, comparison_evidence("month"), purchase_evidence()])
        if health_rule:
            evidence.append(
                {
                    "key": "health_rule",
                    "label": "当前生效规则",
                    "value": str(health["status"]),
                    "value_type": "text",
                    "period": str(health.get("period_end") or snapshot["as_of"]),
                    "source": str(health_rule["source"]),
                    "direction": "neutral",
                    "severity": "info",
                    "description": str(health_rule["state_instructions"]),
                }
            )
    elif analysis_type == "products":
        for grain in ("month", "half"):
            item = product_evidence(grain)
            if item:
                evidence.append(item)
        if not evidence:
            warnings.append("当前客户没有可用于商品分析的月度或半年商品记录。")
    elif analysis_type == "store_refund":
        refund = snapshot.get("refund_background")
        if refund:
            refund_change = refund.get("change")
            evidence.append(
                {
                    "key": "store_refund_change",
                    "label": "所在店铺退款变化",
                    "value": _percent_text(float(refund_change)) if refund_change is not None else str(refund["current"]),
                    "value_type": "percentage" if refund_change is not None else "currency",
                    "period": str(refund["period"]),
                    "source": str(refund["source"]),
                    "direction": "negative" if refund_change is not None and float(refund_change) > 0 else "neutral",
                    "severity": "medium" if refund_change is not None and float(refund_change) >= 0.10 else "info",
                    "description": (
                        f"{refund['store_name']}本月退款金额较上一月 {_percent_text(float(refund_change))}。"
                        if refund_change is not None
                        else f"{refund['store_name']}本月退款金额为 {refund['current']} 元，上一月缺少可比记录。"
                    ),
                }
            )
        warnings.append("退款指标是客户所在店铺的周期汇总，当前数据库不能归因到单个客户。")

    month_change = comparisons["month"]["amount_change"]
    purchase_change = comparisons["month"]["purchase_change"]
    risk_status = health["status"] in {"风险", "流失预警", "流失"}
    if int(health.get("stale_days") or 0) > 1:
        warnings.append(f"客户健康快照比销售截止日期早 {health['stale_days']} 天，当前状态可能未反映最新经营变化。")
        actions.append({"priority": "high", "title": "核对健康快照", "description": "先确认健康状态所用周期，再判断当前客户风险。"})
    if risk_status:
        rule_action = str(health_rule.get("follow_up_action") or "") if health_rule else ""
        actions.append(
            {
                "priority": "high",
                "title": "优先核查风险客户",
                "description": rule_action or "结合当前健康状态和销售变化核查风险原因。",
            }
        )
    if month_change is not None and float(month_change) <= -0.10:
        actions.append({"priority": "high", "title": "核查销售下降来源", "description": "对比本月与上一月拿货次数和主要商品，确认下降集中在哪项指标。"})
    elif month_change is not None and float(month_change) < 0:
        actions.append({"priority": "medium", "title": "持续观察销售回落", "description": "关注下一周期销售和拿货次数，确认回落是否持续。"})
    elif month_change is not None and float(month_change) >= 0.10:
        actions.append({"priority": "low", "title": "复盘增长来源", "description": "核查主要商品和拿货次数，确认本月增长由哪些指标贡献。"})
    if purchase_change is not None and float(purchase_change) <= -0.20:
        actions.append({"priority": "medium", "title": "核查采购频次下降", "description": "判断销售变化是否主要来自拿货次数减少。"})
    half_concentration = products["half"].get("top3_amount_ratio")
    if half_concentration is not None and float(half_concentration) >= 0.70:
        actions.append({"priority": "medium", "title": "关注商品集中度", "description": "核查头部商品贡献是否过度集中，避免单一商品波动被忽略。"})
    refund = snapshot.get("refund_background")
    if refund and refund.get("change") is not None and float(refund["change"]) >= 0.10:
        actions.append({"priority": "medium", "title": "核查店铺退款变化", "description": "查看店铺层退款上升原因，但不要归因到当前客户。"})
    if not health_rule and health["status"] != "未评分":
        warnings.append("当前健康状态没有匹配到公共规则，建议核对规则配置。")

    priority_order = {"high": 0, "medium": 1, "low": 2}
    unique_actions: list[dict[str, str]] = []
    action_titles: set[str] = set()
    for action in sorted(actions, key=lambda item: priority_order[item["priority"]]):
        if action["title"] not in action_titles:
            unique_actions.append(action)
            action_titles.add(action["title"])
    if not unique_actions:
        unique_actions.append({"priority": "low", "title": "保持周期复盘", "description": "继续观察销售、拿货次数、健康状态和主要商品变化。"})

    has_sales = any(Decimal(comparisons[grain]["current"]["amount"]) > 0 for grain in ("month", "quarter", "half"))
    has_products = any(products[grain]["items"] for grain in ("month", "half"))
    empty = not has_sales and not has_products and health["status"] == "未评分"
    if empty:
        conclusion = "当前客户暂无足够经营数据"
    elif risk_status and month_change is not None and float(month_change) < 0:
        conclusion = "客户销售回落且处于风险状态，建议优先核查"
    elif risk_status:
        conclusion = "客户当前处于风险状态，需要优先核对经营变化"
    elif month_change is not None and float(month_change) <= -0.10:
        conclusion = "客户本月销售明显回落，需要定位影响来源"
    elif month_change is not None and float(month_change) >= 0.10:
        conclusion = "客户本月销售保持增长，建议复盘主要贡献"
    else:
        conclusion = "客户核心经营指标整体平稳，继续周期观察"
    if analysis_type == "store_refund":
        conclusion = "以下仅为客户所在店铺退款背景，不能归因到当前客户"
    elif analysis_type == "products" and not evidence:
        conclusion = "当前客户暂无足够商品数据"

    summary = "".join(str(item["description"]) for item in evidence[:3])
    if not summary:
        summary = "当前可用数据不足，暂不能形成可靠的客户经营判断。"
    return {
        "empty": empty,
        "analysis_type": analysis_type,
        "conclusion": conclusion,
        "summary": summary,
        "evidence": evidence[:4],
        "actions": unique_actions[:3],
        "warnings": warnings,
        "internal_only": True,
    }


def customer_analysis_messages(snapshot: dict[str, Any], analysis: dict[str, Any]) -> list[dict[str, str]]:
    payload = json.dumps(
        {
            "analysis_type": analysis["analysis_type"],
            "conclusion": analysis["conclusion"],
            "summary": analysis["summary"],
            "evidence": analysis["evidence"],
            "actions": analysis["actions"],
            "warnings": analysis["warnings"],
            "store_key": snapshot["store_key"],
            "customer_id": snapshot["customer_id"],
            "as_of": snapshot["as_of"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return [
        {
            "role": "system",
            "content": (
                "你是公司内部业务部门使用的客户经营分析助手。只能依据后端证据解释经营表现，"
                "不得增加或修改数字，不得生成面向客户的回复、沟通话术、营销文案或客服文本。"
                "请输出2至4句中文纯文本，不使用Markdown，控制在300字以内。"
            ),
        },
        {"role": "user", "content": f"请增强以下内部经营诊断的表达：{payload}"},
    ]


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
        try:
            config = ai_settings_for_role(user.role)
        except ValueError as exc:
            raise ApiError(403, "ROLE_FORBIDDEN", "当前账号没有可用的AI配置范围。") from exc
        result = {
            "scope_key": "manager" if user.role == "manager" else user.group_key,
            "base_url": config["base_url"],
            "model_name": config["model_name"] or None,
            "api_key_masked": "••••••••" if config["api_key"] else "",
            "configured": bool(config["base_url"] and config["api_key"]),
        }
        if include_secret and config["api_key"]:
            result["api_key"] = config["api_key"]
        return result

    def resolve_api_setting(
        self,
        user: UserContext,
        base_url: str,
        api_key: str | None,
        model_name: str | None,
    ) -> dict[str, str]:
        current = self.api_setting(user, include_secret=True)
        resolved_api_key = (api_key or "").strip() or str(current.get("api_key") or "")
        resolved_model = (model_name or "").strip() or str(current.get("model_name") or "") or get_settings().ai_default_model
        if not resolved_api_key:
            raise ApiError(422, "AI_API_KEY_REQUIRED", "首次配置时必须填写api_key。")
        return {
            "base_url": base_url.strip().rstrip("/"),
            "api_key": resolved_api_key,
            "model_name": resolved_model,
        }

    def update_api_setting(self, user: UserContext, config: dict[str, str]) -> dict[str, Any]:
        try:
            save_ai_settings_for_role(
                user.role,
                config["base_url"],
                config["api_key"],
                config["model_name"],
            )
        except ValueError as exc:
            raise ApiError(422, "AI_CONFIG_INVALID", str(exc)) from exc
        return self.api_setting(user)
