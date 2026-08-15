import asyncio
import json
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import app.ai_query as query_module
import app.main as main_module
from app.ai_metric_catalog import METRIC_CATALOG, validate_query_plan
from app.ai_query import execute_ai_query, infer_query_plan, is_forbidden_query
from app.ai_tools import AiToolRegistry
from app.responses import ApiError
from app.schemas import AiQueryRequest, UserContext


MANAGER = UserContext("manager-user", "manager", "主管", "manager", None)
TALENT = UserContext("talent-user", "talent", "达人组长", "talent", "talent")
CONTEXT = {"scope_key": "all", "as_of": "2026-08-11", "grain": "month", "route": "#/manager/overall"}


def test_rule_parser_supports_high_value_dashboard_questions() -> None:
    decline = infer_query_plan("本月哪个店铺销售额下降最多？", CONTEXT, MANAGER)
    assert decline["metric_key"] == "sales_change_rate"
    assert decline["group_by"] == "store"
    assert decline["sort_by"] == "change"
    assert decline["sort_direction"] == "asc"

    trend = infer_query_plan("达人组最近6个月销售趋势怎么样？", CONTEXT, MANAGER)
    assert trend["metric_key"] == "sales_trend"
    assert trend["scope_key"] == "talent"
    assert trend["grain"] == "month"
    assert trend["limit"] == 6

    refund = infer_query_plan("本季度退款最高的是哪个店铺？", CONTEXT, MANAGER)
    assert refund["metric_key"] == "refund_amount"
    assert refund["grain"] == "quarter"
    assert refund["group_by"] == "store"

    customers = infer_query_plan("列出半年销售额最高的20个风险客户。", CONTEXT, MANAGER)
    assert customers["metric_key"] == "customer_ranking"
    assert customers["grain"] == "half"
    assert customers["filters"] == {"health_status": "风险"}
    assert customers["limit"] == 20

    products = infer_query_plan("当前半年金额Top5商品是什么？", CONTEXT, MANAGER)
    assert products["metric_key"] == "top_product_amount"
    assert products["limit"] == 5

    freshness = infer_query_plan("哪些店铺的数据日期比较旧？", CONTEXT, MANAGER)
    assert freshness["metric_key"] == "data_freshness"
    assert freshness["grain"] == "day"


def test_query_boundary_rejects_writes_predictions_and_customer_copy() -> None:
    assert is_forbidden_query("帮我回复客户") is True
    assert is_forbidden_query("执行SQL删除数据库记录") is True
    assert is_forbidden_query("预测下个月销售额") is True
    assert is_forbidden_query("查询本月销售额") is False


def test_group_user_cannot_query_another_group_scope() -> None:
    body = AiQueryRequest(
        question="私域组本月销售额是多少？",
        context={"scope_key": "talent", "grain": "month", "route": "#/talent/overall"},
    )
    try:
        asyncio.run(execute_ai_query(None, TALENT, body, {"configured": False}))
    except ApiError as exc:
        assert exc.code == "SCOPE_FORBIDDEN"
    else:
        raise AssertionError("cross-group queries must be rejected before tool execution")


def test_metric_catalog_rejects_unregistered_dimensions_and_limits() -> None:
    plan = infer_query_plan("本月销售额是多少？", CONTEXT, MANAGER)
    validate_query_plan(plan)
    plan["group_by"] = "customer"
    try:
        validate_query_plan(plan)
    except ApiError as exc:
        assert exc.code == "AI_QUERY_UNSUPPORTED"
    else:
        raise AssertionError("unregistered dimensions must be rejected")


class FakeDashboardRepository:
    def sales_amount_by_store(self, stores, _grain, window):
        current = window.start.month == 8
        values = {
            "weidian": "100.00" if current else "200.00",
            "doudian_children": "200.00" if current else "100.00",
        }
        return [
            {
                "store_key": key,
                "store_name": key,
                "amount": value,
                "source": f"schema.{key}.monthly_sales",
            }
            for key, value in values.items()
            if key in stores
        ]

    def latest_data_dates(self, stores):
        return [
            {"store_key": key, "store_name": key, "latest_data_date": date(2026, 8, 11), "source": f"schema.{key}.daily_sales"}
            for key in stores
        ]


def test_sales_tool_returns_verified_table_and_chart_from_same_rows() -> None:
    plan = infer_query_plan("本月哪个店铺销售额下降最多？", CONTEXT, MANAGER)
    registry = AiToolRegistry(None)
    registry.dashboard = FakeDashboardRepository()
    result = registry.execute(MANAGER, plan, METRIC_CATALOG[plan["metric_key"]], date(2026, 8, 11))

    assert result["table"]["rows"][0]["key"] == "weidian"
    assert result["table"]["rows"][0]["change"] == -0.5
    assert result["chart"]["series"][0]["y"] == result["table"]["rows"][0]["change"]
    assert "下降" in result["answer"] or "最低" in result["answer"]
    assert result["warnings"] == []


def tool_result() -> dict:
    rows = [{"label": "微店", "current": "100.00", "previous": "80.00", "change": 0.25, "source": "weidian.monthly_sales", "store_keys": ["weidian"]}]
    return {
        "answer": "本月微店销售额为¥100.00，较上一周期+25.0%。",
        "empty": False,
        "evidence": [{"key": "lead", "label": "微店", "value": "100.00", "value_type": "currency", "period": "2026-08", "source": "weidian.monthly_sales"}],
        "table": {"columns": [], "rows": rows},
        "chart": None,
        "warnings": [],
        "store_keys": ["weidian"],
        "as_of": "2026-08-11",
        "grain": "month",
        "target_module": "sales",
    }


class FakeRegistry:
    def __init__(self, _conn):
        self.dashboard = SimpleNamespace(latest_data_date=lambda _stores: date(2026, 8, 11))

    def execute(self, *_args):
        return tool_result()


def test_unconfigured_query_uses_rule_parser_and_never_calls_model(monkeypatch) -> None:
    calls: list[str] = []

    async def forbidden_completion(*_args):
        calls.append("called")
        return ""

    monkeypatch.setattr(query_module, "AiToolRegistry", FakeRegistry)
    body = AiQueryRequest(question="本月销售额是多少？", context=CONTEXT)
    result = asyncio.run(execute_ai_query(None, MANAGER, body, {"configured": False}, forbidden_completion))

    assert calls == []
    assert result["mode"] == "rule_summary"
    assert result["plan_source"] == "rule"
    assert result["answer"].startswith("本月微店销售额")
    assert result["scope"]["as_of"] == "2026-08-11"


def test_configured_query_uses_ai_for_plan_and_verified_result_explanation(monkeypatch) -> None:
    calls: list[list[dict[str, str]]] = []
    plan = infer_query_plan("本月销售额是多少？", CONTEXT, MANAGER)

    async def completion(_config, messages):
        calls.append(messages)
        if len(calls) == 1:
            return json.dumps(plan, ensure_ascii=False)
        return "本月销售额为100元，较上一周期增长25%，数据来自已验证的月度销售表。"

    monkeypatch.setattr(query_module, "AiToolRegistry", FakeRegistry)
    body = AiQueryRequest(question="本月销售额是多少？", context=CONTEXT)
    config = {"configured": True, "base_url": "https://example.test/v1", "api_key": "secret", "model_name": "model"}
    result = asyncio.run(execute_ai_query(None, MANAGER, body, config, completion))

    assert len(calls) == 2
    assert result["mode"] == "ai"
    assert result["plan_source"] == "ai"
    assert result["degraded"] is False
    assert "已验证" in result["answer"]
    assert "secret" not in str(calls)


def test_ai_plan_failure_degrades_to_local_parser(monkeypatch) -> None:
    calls = 0

    async def completion(_config, _messages):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ApiError(502, "AI_PROVIDER_ERROR", "failed")
        return "规则证据说明。"

    monkeypatch.setattr(query_module, "AiToolRegistry", FakeRegistry)
    body = AiQueryRequest(question="本月销售额是多少？", context=CONTEXT)
    config = {"configured": True, "base_url": "https://example.test/v1", "api_key": "secret"}
    result = asyncio.run(execute_ai_query(None, MANAGER, body, config, completion))

    assert result["degraded"] is True
    assert result["plan_source"] == "rule"
    assert any("受控模板" in warning for warning in result["warnings"])


@contextmanager
def fake_connection():
    yield None


def test_ai_query_endpoint_adds_request_identity(monkeypatch) -> None:
    class FakeSettingsService:
        def __init__(self, _conn):
            pass

        def api_setting(self, _user, include_secret=False):
            assert include_secret is True
            return {"configured": False}

    async def fake_execute(_conn, _user, _body, _config):
        return {"answer": "规则答案", "mode": "rule_summary", "warnings": []}

    monkeypatch.setattr(main_module, "connection", fake_connection)
    monkeypatch.setattr(main_module, "SettingsService", FakeSettingsService)
    monkeypatch.setattr(main_module, "execute_ai_query", fake_execute)
    request = SimpleNamespace(state=SimpleNamespace(request_id="req-ai-query"))
    body = AiQueryRequest(question="本月销售额是多少？", context=CONTEXT)

    result = asyncio.run(main_module.ai_query(body, request, MANAGER))

    assert result["data"]["answer"] == "规则答案"
    assert result["data"]["request_id"] == "req-ai-query"
    assert result["data"]["generated_at"].endswith("+08:00")
