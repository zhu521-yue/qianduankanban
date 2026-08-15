import asyncio
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import app.main as main_module
from app.responses import ApiError
from app.schemas import DashboardInsightRequest, UserContext
from app.services import build_dashboard_insight, dashboard_insight_messages, normalize_ai_summary


def dashboard_snapshot(
    *,
    month_change: float | None = -0.12,
    refund_change: float | None = 0.25,
    health_total: int = 10,
    risk_count: int = 3,
) -> dict[str, object]:
    return {
        "scope_key": "talent",
        "store_keys": ["weidian"],
        "as_of": "2026-08-14",
        "latest_data_date": "2026-08-14",
        "kpis": [
            {"key": "half_sales", "label": "半年销售额", "value": "1000.00", "change": 0.08, "period": "2026-02-01—2026-07-31"},
            {"key": "month_sales", "label": "本月销售额", "value": "300.00", "change": month_change, "period": "2026-08-01—2026-08-31"},
        ],
        "sales_trend": {"grain": "month", "series": []},
        "customer_health": {
            "period": {"start": "2026-08-10", "end": "2026-08-16", "label": "2026-08-10—2026-08-16"},
            "total": health_total,
            "healthy_count": health_total - risk_count,
            "healthy_ratio": (health_total - risk_count) / health_total if health_total else None,
            "items": [
                {"status": "稳定", "count": health_total - risk_count, "color": "#34d399"},
                {"status": "风险", "count": risk_count, "color": "#fb923c"},
            ],
        },
        "top_products": {
            "period": "2026-02-01—2026-07-31",
            "by_quantity": [],
            "by_amount": [{"product_code": "SKU-1", "quantity": "10", "amount": "600.00"}],
            "double_top_count": 0,
        },
        "refund": {
            "grain": "week",
            "current": "100.00",
            "previous": "80.00",
            "change": refund_change,
            "period": "2026-08-10—2026-08-16",
            "series": [],
        },
        "presale": {"available": False, "period": "半年", "amount": "0.00", "quantity": "0", "product_count": 0, "products": []},
    }


def test_rule_summary_prioritizes_sales_refund_and_customer_risk() -> None:
    insight = build_dashboard_insight(dashboard_snapshot())

    assert insight["empty"] is False
    assert insight["headline"] == "销售承压且退款上升，建议优先排查经营风险"
    assert [item["key"] for item in insight["evidence"]] == [
        "month_sales_change",
        "refund_change",
        "risk_customers",
        "top_product_concentration",
    ]
    assert insight["evidence"][0]["value"] == "-12.0%"
    assert insight["evidence"][1]["source"] == "weekly_refunds"
    assert insight["evidence"][2]["value"] == "30.0%"
    assert insight["evidence"][3]["value"] == "60.0%"
    assert [item["priority"] for item in insight["actions"]] == ["high", "high", "high"]


def test_rule_summary_does_not_invent_comparisons_when_previous_period_is_missing() -> None:
    insight = build_dashboard_insight(dashboard_snapshot(month_change=None, refund_change=None))

    assert insight["evidence"][0]["key"] == "month_sales"
    assert any("未计算销售环比" in warning for warning in insight["warnings"])
    assert any("未计算退款环比" in warning for warning in insight["warnings"])
    assert "销售额较上一周期" not in insight["summary"]


def test_rule_summary_returns_explicit_empty_state() -> None:
    snapshot = dashboard_snapshot(health_total=0, risk_count=0)
    snapshot["kpis"][0]["value"] = "0.00"  # type: ignore[index]
    snapshot["kpis"][1]["value"] = "0.00"  # type: ignore[index]
    snapshot["refund"]["current"] = "0.00"  # type: ignore[index]
    snapshot["top_products"]["by_amount"] = []  # type: ignore[index]

    insight = build_dashboard_insight(snapshot)

    assert insight["empty"] is True
    assert insight["evidence"] == []
    assert insight["actions"] == []
    assert "不生成方向性结论" in insight["summary"]


def test_ai_prompt_contains_only_rule_evidence_and_normalizes_plain_text() -> None:
    insight = build_dashboard_insight(dashboard_snapshot())
    messages = dashboard_insight_messages(insight)

    assert "不得增加、修改或推测任何数字" in messages[0]["content"]
    assert "SKU-1" in messages[1]["content"]
    assert "api_key" not in messages[1]["content"]
    assert normalize_ai_summary("```\n增长正常。\n继续观察。\n```", insight["summary"]) == "增长正常。 继续观察。"


@contextmanager
def fake_connection():
    yield None


def test_dashboard_insight_uses_rule_summary_without_ai_configuration(monkeypatch) -> None:
    snapshot = dashboard_snapshot()
    user = UserContext("talent-user", "talent", "达人组长", "talent", "talent")
    request = SimpleNamespace(state=SimpleNamespace(request_id="req-rule"))
    calls: list[str] = []

    class FakeDashboardService:
        def __init__(self, _conn) -> None:
            pass

        def latest_date(self, _user, _scope_key):
            return date(2026, 8, 14)

        def dashboard(self, *_args):
            return snapshot

    class FakeSettingsService:
        def __init__(self, _conn) -> None:
            pass

        def api_setting(self, _user, include_secret=False):
            return {"configured": False}

    async def forbidden_ai_call(*_args):
        calls.append("called")
        return "不应调用"

    monkeypatch.setattr(main_module, "connection", fake_connection)
    monkeypatch.setattr(main_module, "DashboardService", FakeDashboardService)
    monkeypatch.setattr(main_module, "SettingsService", FakeSettingsService)
    monkeypatch.setattr(main_module, "request_ai_completion", forbidden_ai_call)
    body = DashboardInsightRequest(scope_key="talent", trend_grain="month", refund_grain="week")

    result = asyncio.run(main_module.dashboard_insight(body, request, user))

    assert calls == []
    assert result["data"]["mode"] == "rule_summary"
    assert result["data"]["configured"] is False
    assert result["data"]["request_id"] == "req-rule"


def test_dashboard_insight_falls_back_when_ai_provider_fails(monkeypatch) -> None:
    snapshot = dashboard_snapshot()
    user = UserContext("talent-user", "talent", "达人组长", "talent", "talent")
    request = SimpleNamespace(state=SimpleNamespace(request_id="req-fallback"))

    class FakeDashboardService:
        def __init__(self, _conn) -> None:
            pass

        def dashboard(self, *_args):
            return snapshot

    class FakeSettingsService:
        def __init__(self, _conn) -> None:
            pass

        def api_setting(self, _user, include_secret=False):
            return {"configured": True, "base_url": "https://example.test/v1", "api_key": "secret", "model_name": "model"}

    async def failing_ai_call(*_args):
        raise ApiError(502, "AI_PROVIDER_ERROR", "provider failed")

    monkeypatch.setattr(main_module, "connection", fake_connection)
    monkeypatch.setattr(main_module, "DashboardService", FakeDashboardService)
    monkeypatch.setattr(main_module, "SettingsService", FakeSettingsService)
    monkeypatch.setattr(main_module, "request_ai_completion", failing_ai_call)
    body = DashboardInsightRequest(scope_key="talent", as_of="2026-08-14", trend_grain="month", refund_grain="week")

    result = asyncio.run(main_module.dashboard_insight(body, request, user))

    assert result["data"]["mode"] == "rule_summary"
    assert result["data"]["configured"] is True
    assert result["data"]["degraded"] is True
    assert any("已展示" in warning for warning in result["data"]["warnings"])
