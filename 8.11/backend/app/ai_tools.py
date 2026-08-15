from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from app.ai_metric_catalog import MetricDefinition
from app.catalog import STORES, resolve_scope
from app.periods import Grain, period_window, previous_window, recent_windows
from app.repositories import (
    CUSTOMER_SPECS,
    PRODUCT_SPECS,
    REFUND_SPECS,
    SALES_SPECS,
    CustomerRepository,
    DashboardRepository,
    amount_text,
)
from app.responses import ApiError
from app.schemas import UserContext


def _ratio(current: Decimal | int, previous: Decimal | int) -> float | None:
    previous_value = Decimal(previous)
    if previous_value == 0:
        return None
    return float((Decimal(current) - previous_value) / previous_value)


def _percent(value: float | None) -> str:
    if value is None:
        return "暂无可靠对比"
    return f"{value * 100:+.1f}%"


def _money(value: Decimal | str | int | float) -> str:
    return f"¥{Decimal(value):,.2f}"


def _safe_sort(rows: list[dict[str, Any]], key: str, direction: str) -> list[dict[str, Any]]:
    def sortable(item: dict[str, Any]) -> tuple[bool, Decimal | str]:
        value = item.get(key)
        if value is None:
            return False, Decimal(0)
        if isinstance(value, str):
            try:
                return True, Decimal(value)
            except Exception:
                return True, value
        return True, Decimal(str(value))

    reverse = direction == "desc"
    if reverse:
        return sorted(rows, key=sortable, reverse=True)
    return sorted(rows, key=lambda item: (not sortable(item)[0], sortable(item)[1]))


def _scope_identity(store_key: str, group_by: str) -> tuple[str, str]:
    store = STORES[store_key]
    if group_by == "group":
        return store.group_key, store.group_name
    if group_by == "platform":
        return store.platform_key, store.platform_name
    if group_by == "store":
        return store.key, store.name
    return "total", "当前范围"


class AiToolRegistry:
    def __init__(self, conn: Any):
        self.dashboard = DashboardRepository(conn)
        self.customers = CustomerRepository(conn)

    def execute(
        self,
        user: UserContext,
        plan: dict[str, Any],
        definition: MetricDefinition,
        as_of: date,
    ) -> dict[str, Any]:
        stores = resolve_scope(user.role, str(plan["scope_key"]))
        metric_key = str(plan["metric_key"])
        grain = Grain(str(plan["grain"]))
        if metric_key in {"sales_amount", "sales_change_rate", "scope_contribution"}:
            result = self._sales(stores, plan, definition, grain, as_of)
        elif metric_key == "sales_trend":
            result = self._sales_trend(stores, plan, definition, grain, as_of)
        elif metric_key == "active_customer_count":
            result = self._active_customers(stores, plan, definition, grain, as_of)
        elif metric_key == "customer_ranking":
            result = self._customer_ranking(stores, plan, definition, grain, as_of)
        elif metric_key == "customer_health_count":
            result = self._health(stores, plan, definition, as_of)
        elif metric_key in {"top_product_amount", "top_product_quantity"}:
            result = self._top_products(stores, plan, definition, grain, as_of)
        elif metric_key == "refund_amount":
            result = self._refund(stores, plan, definition, grain, as_of)
        elif metric_key == "presale_amount":
            result = self._presale(stores, plan, definition, grain, as_of)
        elif metric_key == "data_freshness":
            result = self._freshness(stores, plan, definition, as_of)
        else:
            raise ApiError(422, "AI_QUERY_UNSUPPORTED", "当前指标尚未注册只读查询工具。")
        result.setdefault("warnings", [])
        if metric_key != "data_freshness":
            stale = [
                row for row in self.dashboard.latest_data_dates(stores)
                if row["latest_data_date"] is None or row["latest_data_date"] < as_of
            ]
            if stale:
                names = "、".join(row["store_name"] for row in stale[:4])
                suffix = "等" if len(stale) > 4 else ""
                result["warnings"].append(f"{names}{suffix}的数据日期早于查询截止日期，跨店铺比较可能不完整。")
        result.update(
            {
                "metric_key": metric_key,
                "metric_label": definition.label,
                "scope_key": plan["scope_key"],
                "store_keys": list(stores),
                "as_of": as_of.isoformat(),
                "grain": grain.value,
                "target_module": definition.target_module,
            }
        )
        self._validate(result, plan, definition, stores)
        return result

    def _sales(
        self,
        stores: tuple[str, ...],
        plan: dict[str, Any],
        definition: MetricDefinition,
        grain: Grain,
        as_of: date,
    ) -> dict[str, Any]:
        current_window = period_window(grain, as_of)
        previous = previous_window(current_window)
        current_rows = self.dashboard.sales_amount_by_store(stores, grain, current_window)
        previous_by_store = {row["store_key"]: row for row in self.dashboard.sales_amount_by_store(stores, grain, previous)}
        grouped: dict[str, dict[str, Any]] = {}
        for row in current_rows:
            key, label = _scope_identity(row["store_key"], str(plan["group_by"]))
            item = grouped.setdefault(key, {"key": key, "label": label, "current": Decimal(0), "previous": Decimal(0), "sources": [], "store_keys": []})
            item["current"] += Decimal(row["amount"])
            item["previous"] += Decimal(previous_by_store[row["store_key"]]["amount"])
            item["sources"].append(row["source"])
            item["store_keys"].append(row["store_key"])
        total = sum((item["current"] for item in grouped.values()), Decimal(0))
        rows: list[dict[str, Any]] = []
        for item in grouped.values():
            change = _ratio(item["current"], item["previous"])
            rows.append(
                {
                    "key": item["key"],
                    "label": item["label"],
                    "current": amount_text(item["current"]),
                    "previous": amount_text(item["previous"]),
                    "change": change,
                    "contribution": float(item["current"] / total) if total else None,
                    "source": " + ".join(item["sources"]),
                    "store_keys": item["store_keys"],
                }
            )
        sort_key = "change" if plan["sort_by"] == "change" or plan["metric_key"] == "sales_change_rate" else "current"
        rows = _safe_sort(rows, sort_key, str(plan["sort_direction"]))[: int(plan["limit"])]
        first = rows[0] if rows else None
        if not first:
            answer = f"{current_window.label}没有可用销售数据。"
        elif len(rows) == 1:
            answer = f"{current_window.label}{first['label']}销售额为{_money(first['current'])}，较上一周期{_percent(first['change'])}。"
        elif sort_key == "change" and plan["sort_direction"] == "asc":
            answer = f"{current_window.label}销售变化最低的是{first['label']}，较上一周期{_percent(first['change'])}。"
        else:
            answer = f"{current_window.label}{definition.label}最高的是{first['label']}，销售额为{_money(first['current'])}。"
        columns = [
            {"key": "label", "label": str(plan["group_by"]), "type": "text"},
            {"key": "current", "label": "当前销售额", "type": "currency"},
            {"key": "previous", "label": "上一周期", "type": "currency"},
            {"key": "change", "label": "周期变化", "type": "percentage"},
            {"key": "contribution", "label": "当前贡献", "type": "percentage"},
        ]
        return self._result(
            answer,
            rows,
            columns,
            current_window.label,
            "bar" if len(rows) > 1 else None,
            "label",
            sort_key,
            first,
            definition.label,
        )

    def _sales_trend(
        self,
        stores: tuple[str, ...],
        plan: dict[str, Any],
        definition: MetricDefinition,
        grain: Grain,
        as_of: date,
    ) -> dict[str, Any]:
        windows = recent_windows(grain, as_of, int(plan["limit"]))
        table_name = SALES_SPECS[grain][0]
        source = " + ".join(f"{STORES[key].schema_name}.{table_name}" for key in stores)
        rows = [
            {
                "label": window.label,
                "start": window.start.isoformat(),
                "end": window.end.isoformat(),
                "current": amount_text(self.dashboard.sales_amount(stores, grain, window)),
                "source": source,
            }
            for window in windows
        ]
        first_amount = Decimal(rows[0]["current"]) if rows else Decimal(0)
        latest_amount = Decimal(rows[-1]["current"]) if rows else Decimal(0)
        movement = _ratio(latest_amount, first_amount)
        answer = f"最近{len(rows)}个{grain.value}周期销售额从{_money(first_amount)}变化到{_money(latest_amount)}，总体变化{_percent(movement)}。" if rows else "当前没有可用销售趋势。"
        return self._result(
            answer,
            rows,
            [
                {"key": "label", "label": "周期", "type": "text"},
                {"key": "current", "label": "销售额", "type": "currency"},
            ],
            f"最近{len(rows)}个周期",
            "line",
            "label",
            "current",
            rows[-1] if rows else None,
            definition.label,
        )

    def _active_customers(
        self,
        stores: tuple[str, ...],
        plan: dict[str, Any],
        definition: MetricDefinition,
        grain: Grain,
        as_of: date,
    ) -> dict[str, Any]:
        current_window = period_window(grain, as_of)
        previous = previous_window(current_window)
        rows: list[dict[str, Any]] = []
        groups = [("total", "当前范围", stores)] if plan["group_by"] == "total" else [(key, STORES[key].name, (key,)) for key in stores]
        table_name = CUSTOMER_SPECS[grain][0]
        for key, label, group_stores in groups:
            current = self.dashboard.active_customer_count(group_stores, grain, current_window)
            previous_value = self.dashboard.active_customer_count(group_stores, grain, previous)
            rows.append(
                {
                    "key": key,
                    "label": label,
                    "current": current,
                    "previous": previous_value,
                    "change": _ratio(current, previous_value),
                    "source": " + ".join(f"{STORES[item].schema_name}.{table_name}" for item in group_stores),
                    "store_keys": list(group_stores),
                }
            )
        rows = _safe_sort(rows, "current", str(plan["sort_direction"]))[: int(plan["limit"])]
        first = rows[0] if rows else None
        answer = f"{current_window.label}{first['label']}共有{first['current']}个产生正向销售的客户，较上一周期{_percent(first['change'])}。" if first else "当前没有可用客户数量数据。"
        return self._result(
            answer,
            rows,
            [
                {"key": "label", "label": "范围", "type": "text"},
                {"key": "current", "label": "当前客户数", "type": "number"},
                {"key": "previous", "label": "上一周期", "type": "number"},
                {"key": "change", "label": "周期变化", "type": "percentage"},
            ],
            current_window.label,
            "bar" if len(rows) > 1 else None,
            "label",
            "current",
            first,
            definition.label,
        )

    def _customer_ranking(
        self,
        stores: tuple[str, ...],
        plan: dict[str, Any],
        definition: MetricDefinition,
        grain: Grain,
        as_of: date,
    ) -> dict[str, Any]:
        window = period_window(grain, as_of)
        rows, _ = self.customers.list_page(
            stores,
            grain,
            window,
            as_of,
            None,
            (plan.get("filters") or {}).get("health_status"),
            "amount",
            str(plan["sort_direction"]),
            1,
            int(plan["limit"]),
        )
        table_name = CUSTOMER_SPECS[grain][0]
        output = [
            {
                "store_key": row["store_key"],
                "store_name": STORES[row["store_key"]].name,
                "customer_id": str(row["customer_id"]),
                "display_name": str(row["display_name"] or row["customer_id"]),
                "period_amount": amount_text(row["period_amount"]),
                "purchase_count": int(row["purchase_count"] or 0),
                "score": float(row["score"] or 0),
                "status": str(row["status"] or "未评分"),
                "source": f"{STORES[row['store_key']].schema_name}.{table_name} + {STORES[row['store_key']].schema_name}.customer_health_detail",
            }
            for row in rows
        ]
        first = output[0] if output else None
        status_text = f"{(plan.get('filters') or {}).get('health_status')}状态的" if (plan.get("filters") or {}).get("health_status") else ""
        answer = f"{window.label}{status_text}客户中，销售额最高的是{first['display_name']}，销售额为{_money(first['period_amount'])}。" if first else f"{window.label}没有符合条件的客户。"
        return self._result(
            answer,
            output,
            [
                {"key": "store_name", "label": "店铺", "type": "text"},
                {"key": "display_name", "label": "客户", "type": "text"},
                {"key": "period_amount", "label": "销售额", "type": "currency"},
                {"key": "purchase_count", "label": "拿货次数", "type": "number"},
                {"key": "status", "label": "健康状态", "type": "text"},
            ],
            window.label,
            None,
            "display_name",
            "period_amount",
            first,
            definition.label,
        )

    def _health(
        self,
        stores: tuple[str, ...],
        plan: dict[str, Any],
        definition: MetricDefinition,
        as_of: date,
    ) -> dict[str, Any]:
        week = period_window(Grain.WEEK, as_of)
        filter_status = (plan.get("filters") or {}).get("health_status")
        if plan["group_by"] == "store":
            rows = []
            for key in stores:
                distribution = self.dashboard.health_distribution((key,), week, as_of)
                count = sum(int(item["count"]) for item in distribution if not filter_status or item["status"] == filter_status)
                rows.append(
                    {
                        "store_key": key,
                        "label": STORES[key].name,
                        "count": count,
                        "status": filter_status or "全部状态",
                        "source": f"{STORES[key].schema_name}.customer_weekly_sales + {STORES[key].schema_name}.customer_health_detail",
                    }
                )
            rows = _safe_sort(rows, "count", str(plan["sort_direction"]))[: int(plan["limit"])]
        else:
            distribution = self.dashboard.health_distribution(stores, week, as_of)
            rows = [
                {
                    "label": item["status"],
                    "status": item["status"],
                    "count": int(item["count"]),
                    "source": " + ".join(f"{STORES[key].schema_name}.customer_health_detail" for key in stores),
                }
                for item in distribution
                if not filter_status or item["status"] == filter_status
            ]
            rows = _safe_sort(rows, "count", str(plan["sort_direction"]))[: int(plan["limit"])]
        first = rows[0] if rows else None
        answer = f"{week.label}{first['label']}共有{first['count']}个客户，为当前结果中的最高项。" if first else f"{week.label}没有符合条件的健康状态数据。"
        return self._result(
            answer,
            rows,
            [
                {"key": "label", "label": "店铺/状态", "type": "text"},
                {"key": "count", "label": "客户数", "type": "number"},
            ],
            week.label,
            "bar",
            "label",
            "count",
            first,
            definition.label,
        )

    def _top_products(
        self,
        stores: tuple[str, ...],
        plan: dict[str, Any],
        definition: MetricDefinition,
        grain: Grain,
        as_of: date,
    ) -> dict[str, Any]:
        window = period_window(grain, as_of)
        order_by = "quantity" if plan["metric_key"] == "top_product_quantity" else "amount"
        source = " + ".join(f"{STORES[key].schema_name}.{PRODUCT_SPECS[grain][0]}" for key in stores)
        rows = [
            {
                "product_code": str(item["product_code"]),
                "label": str(item["product_code"]),
                "amount": amount_text(item["amount"]),
                "quantity": str(item["quantity"]),
                "source": source,
            }
            for item in self.dashboard.top_products(stores, grain, window, order_by, int(plan["limit"]))
        ]
        first = rows[0] if rows else None
        value_text = _money(first["amount"]) if first and order_by == "amount" else f"{first['quantity']}件" if first else ""
        answer = f"{window.label}{definition.label}第一的是商品编码{first['product_code']}，对应{value_text}。" if first else f"{window.label}没有可用商品数据。"
        return self._result(
            answer,
            rows,
            [
                {"key": "product_code", "label": "商品编码", "type": "text"},
                {"key": "amount", "label": "销售额", "type": "currency"},
                {"key": "quantity", "label": "商品数量", "type": "number"},
            ],
            window.label,
            "bar",
            "label",
            order_by,
            first,
            definition.label,
        )

    def _refund(
        self,
        stores: tuple[str, ...],
        plan: dict[str, Any],
        definition: MetricDefinition,
        grain: Grain,
        as_of: date,
    ) -> dict[str, Any]:
        current_window = period_window(grain, as_of)
        previous = previous_window(current_window)
        current_rows = self.dashboard.refund_amount_by_store(stores, grain, current_window)
        previous_by_store = {row["store_key"]: row for row in self.dashboard.refund_amount_by_store(stores, grain, previous)}
        grouped: dict[str, dict[str, Any]] = {}
        for row in current_rows:
            key, label = _scope_identity(row["store_key"], str(plan["group_by"]))
            item = grouped.setdefault(key, {"key": key, "label": label, "current": Decimal(0), "previous": Decimal(0), "sources": [], "store_keys": []})
            item["current"] += Decimal(row["amount"])
            item["previous"] += Decimal(previous_by_store[row["store_key"]]["amount"])
            item["sources"].append(row["source"])
            item["store_keys"].append(row["store_key"])
        rows = [
            {
                "key": item["key"],
                "label": item["label"],
                "current": amount_text(item["current"]),
                "previous": amount_text(item["previous"]),
                "change": _ratio(item["current"], item["previous"]),
                "source": " + ".join(item["sources"]),
                "store_keys": item["store_keys"],
            }
            for item in grouped.values()
        ]
        sort_key = "change" if plan["sort_by"] == "change" else "current"
        rows = _safe_sort(rows, sort_key, str(plan["sort_direction"]))[: int(plan["limit"])]
        first = rows[0] if rows else None
        answer = f"{current_window.label}退款金额最高的是{first['label']}，退款金额为{_money(first['current'])}，较上一周期{_percent(first['change'])}。" if first else f"{current_window.label}没有可用退款数据。"
        return self._result(
            answer,
            rows,
            [
                {"key": "label", "label": "范围", "type": "text"},
                {"key": "current", "label": "当前退款额", "type": "currency"},
                {"key": "previous", "label": "上一周期", "type": "currency"},
                {"key": "change", "label": "周期变化", "type": "percentage"},
            ],
            current_window.label,
            "bar" if len(rows) > 1 else None,
            "label",
            sort_key,
            first,
            definition.label,
        )

    def _presale(
        self,
        stores: tuple[str, ...],
        plan: dict[str, Any],
        definition: MetricDefinition,
        grain: Grain,
        as_of: date,
    ) -> dict[str, Any]:
        window = period_window(grain, as_of)
        if "weidian" not in stores:
            return self._result(
                "当前权限范围不包含微店，无法查询预售指标。",
                [],
                [],
                window.label,
                None,
                "label",
                "amount",
                None,
                definition.label,
                ["预售指标目前仅由微店预售派生表提供。"],
            )
        summary = self.dashboard.presale_summary(("weidian",), grain, window, int(plan["limit"]))
        rows = [
            {
                "product_code": str(item["product_code"]),
                "label": str(item["product_code"]),
                "amount": amount_text(item["amount"]),
                "quantity": str(item["quantity"]),
                "source": f"weidian.{PRODUCT_SPECS[grain][0].replace('_sales', '_presales')}",
            }
            for item in summary["products"]
        ]
        answer = f"{window.label}微店预售金额为{_money(summary['amount'])}，预售数量为{summary['quantity']}件，涉及{summary['product_count']}个商品编码。"
        result = self._result(
            answer,
            rows,
            [
                {"key": "product_code", "label": "商品编码", "type": "text"},
                {"key": "amount", "label": "预售金额", "type": "currency"},
                {"key": "quantity", "label": "预售数量", "type": "number"},
            ],
            window.label,
            "bar" if rows else None,
            "label",
            "amount",
            rows[0] if rows else None,
            definition.label,
        )
        result["evidence"].insert(
            0,
            {
                "key": "presale_total",
                "label": "预售金额",
                "value": amount_text(summary["amount"]),
                "value_type": "currency",
                "period": window.label,
                "source": f"weidian.{PRODUCT_SPECS[grain][0].replace('_sales', '_presales')}",
            },
        )
        return result

    def _freshness(
        self,
        stores: tuple[str, ...],
        plan: dict[str, Any],
        definition: MetricDefinition,
        as_of: date,
    ) -> dict[str, Any]:
        rows = []
        for item in self.dashboard.latest_data_dates(stores):
            latest = item["latest_data_date"]
            stale_days = max((as_of - latest).days, 0) if latest else None
            rows.append(
                {
                    "store_key": item["store_key"],
                    "store_name": item["store_name"],
                    "label": item["store_name"],
                    "latest_data_date": latest.isoformat() if latest else None,
                    "stale_days": stale_days,
                    "stale": latest is None or latest < as_of,
                    "source": item["source"],
                }
            )
        rows = _safe_sort(rows, "stale_days", "desc")[: int(plan["limit"])]
        stale = [row for row in rows if row["stale"]]
        answer = f"当前范围有{len(stale)}个店铺的数据日期早于{as_of.isoformat()}。" if stale else f"当前范围各店铺数据日期均达到{as_of.isoformat()}。"
        warnings = ["跨店铺比较前应优先关注数据日期滞后的店铺。"] if stale else []
        return self._result(
            answer,
            rows,
            [
                {"key": "store_name", "label": "店铺", "type": "text"},
                {"key": "latest_data_date", "label": "最新数据日期", "type": "date"},
                {"key": "stale_days", "label": "滞后天数", "type": "number"},
            ],
            as_of.isoformat(),
            None,
            "label",
            "stale_days",
            rows[0] if rows else None,
            definition.label,
            warnings,
        )

    def _result(
        self,
        answer: str,
        rows: list[dict[str, Any]],
        columns: list[dict[str, str]],
        period: str,
        chart_type: str | None,
        x_key: str,
        y_key: str,
        lead: dict[str, Any] | None,
        metric_label: str,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        source = str(lead.get("source") or "") if lead else ""
        value = lead.get(y_key) if lead else None
        value_type = "percentage" if y_key in {"change", "contribution"} else "currency" if y_key in {"current", "amount", "period_amount"} else "number"
        evidence = [] if not lead else [
            {
                "key": f"lead_{y_key}",
                "label": str(lead.get("label") or lead.get("display_name") or metric_label),
                "value": "" if value is None else str(value),
                "value_type": value_type,
                "period": period,
                "source": source,
            }
        ]
        chart = None
        if chart_type and rows:
            chart = {
                "type": chart_type,
                "x_key": x_key,
                "y_key": y_key,
                "series": [{"x": str(row.get(x_key) or ""), "y": row.get(y_key)} for row in rows],
            }
        return {
            "answer": answer,
            "empty": not rows,
            "evidence": evidence,
            "table": {"columns": columns, "rows": rows},
            "chart": chart,
            "period": period,
            "warnings": warnings or [],
        }

    def _validate(
        self,
        result: dict[str, Any],
        plan: dict[str, Any],
        definition: MetricDefinition,
        stores: Iterable[str],
    ) -> None:
        rows = result.get("table", {}).get("rows", [])
        if len(rows) > min(int(plan["limit"]), definition.max_limit):
            raise ApiError(500, "AI_QUERY_VALIDATION_FAILED", "问看板结果超过指标目录上限。")
        permitted = set(stores)
        for row in rows:
            if row.get("store_key") and row["store_key"] not in permitted:
                raise ApiError(500, "AI_QUERY_VALIDATION_FAILED", "问看板结果包含权限范围外的店铺。")
            if row.get("store_keys") and not set(row["store_keys"]).issubset(permitted):
                raise ApiError(500, "AI_QUERY_VALIDATION_FAILED", "问看板聚合结果包含权限范围外的店铺。")
            if "current" in row and "previous" in row and "change" in row:
                expected = _ratio(Decimal(row["current"]), Decimal(row["previous"]))
                actual = row["change"]
                if expected is None and actual is not None:
                    raise ApiError(500, "AI_QUERY_VALIDATION_FAILED", "上一周期为零时不应返回变化率。")
                if expected is not None and (actual is None or abs(expected - float(actual)) > 1e-9):
                    raise ApiError(500, "AI_QUERY_VALIDATION_FAILED", "问看板变化率验证失败。")
        chart = result.get("chart")
        if chart:
            expected_series = [{"x": str(row.get(chart["x_key"]) or ""), "y": row.get(chart["y_key"])} for row in rows]
            if chart.get("series") != expected_series:
                raise ApiError(500, "AI_QUERY_VALIDATION_FAILED", "问看板图表与表格数据不一致。")
