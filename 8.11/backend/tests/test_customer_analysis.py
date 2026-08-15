import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

import app.main as main_module
from app.responses import ApiError
from app.schemas import ChatRequest, CustomerAnalysisRequest, UserContext
from app.services import (
    build_customer_analysis,
    customer_analysis_messages,
    infer_customer_analysis_type,
    is_customer_communication_request,
)


def customer_snapshot(
    *,
    month_change: float | None = -0.20,
    health_status: str = "风险",
    health_stale_days: int = 0,
    include_refund: bool = False,
) -> dict[str, object]:
    comparisons = {
        "month": {
            "current": {"start": "2026-08-01", "end": "2026-08-31", "amount": "800.00", "purchase_count": 4},
            "previous": {"start": "2026-07-01", "end": "2026-07-31", "amount": "1000.00", "purchase_count": 6},
            "amount_change": month_change,
            "purchase_change": -1 / 3,
        },
        "quarter": {
            "current": {"start": "2026-08-01", "end": "2026-10-31", "amount": "1200.00", "purchase_count": 7},
            "previous": {"start": "2026-05-01", "end": "2026-07-31", "amount": "1100.00", "purchase_count": 6},
            "amount_change": 1 / 11,
            "purchase_change": 1 / 6,
        },
        "half": {
            "current": {"start": "2026-08-01", "end": "2027-01-31", "amount": "2000.00", "purchase_count": 12},
            "previous": {"start": "2026-02-01", "end": "2026-07-31", "amount": "1800.00", "purchase_count": 10},
            "amount_change": 1 / 9,
            "purchase_change": 0.2,
        },
    }
    products = {
        "month": {
            "items": [
                {"product_code": "SKU-1", "amount": "500.00", "quantity": "5"},
                {"product_code": "SKU-2", "amount": "200.00", "quantity": "2"},
            ],
            "top1_amount_ratio": 0.625,
            "top3_amount_ratio": 0.875,
            "source": "weidian.customer_monthly_product_sales",
        },
        "half": {
            "items": [
                {"product_code": "SKU-1", "amount": "1400.00", "quantity": "14"},
                {"product_code": "SKU-2", "amount": "200.00", "quantity": "2"},
            ],
            "top1_amount_ratio": 0.7,
            "top3_amount_ratio": 0.8,
            "source": "weidian.customer_half_year_product_sales",
        },
    }
    return {
        "store_key": "weidian",
        "store_name": "微店",
        "store_schema": "weidian",
        "group_key": "talent",
        "customer_id": "customer-001",
        "display_name": "测试客户",
        "as_of": "2026-08-11",
        "comparisons": comparisons,
        "products": products,
        "health": {
            "score": 42.0,
            "status": health_status,
            "snapshot_explanation": "近期表现下降",
            "snapshot_action": "内部核查",
            "period_start": "2026-08-04",
            "period_end": "2026-08-10",
            "stale_days": health_stale_days,
            "source": "weidian.customer_health_detail",
            "rule": {
                "state_instructions": "销售或采购频次出现持续回落。",
                "follow_up_action": "核对近期销售和采购变化。",
                "source": "public.talent_customer_status_action",
            },
        },
        "refund_background": {
            "level": "store",
            "store_key": "weidian",
            "store_name": "微店",
            "current": "120.00",
            "previous": "100.00",
            "change": 0.2,
            "period": "2026-08-01—2026-08-31",
            "source": "weidian.monthly_refunds",
        } if include_refund else None,
    }


def test_overview_is_source_backed_and_prioritizes_internal_risk_checks() -> None:
    analysis = build_customer_analysis(customer_snapshot(), "overview")

    assert analysis["internal_only"] is True
    assert analysis["conclusion"] == "客户销售回落且处于风险状态，建议优先核查"
    assert [item["key"] for item in analysis["evidence"]] == [
        "month_sales_change",
        "health_status",
        "half_sales_change",
        "half_product_concentration",
    ]
    assert analysis["evidence"][0]["value"] == "-20.0%"
    assert analysis["evidence"][1]["source"] == "weidian.customer_health_detail"
    assert analysis["actions"][0]["priority"] == "high"
    assert all("回复" not in action["description"] for action in analysis["actions"])


def test_missing_previous_period_does_not_create_a_fake_change_rate() -> None:
    snapshot = customer_snapshot(month_change=None)
    snapshot["comparisons"]["month"]["previous"]["amount"] = "0.00"  # type: ignore[index]

    analysis = build_customer_analysis(snapshot, "recent_performance")

    month = analysis["evidence"][0]
    assert month["value_type"] == "currency"
    assert month["value"] == "800.00"
    assert any("缺少可比" in warning for warning in analysis["warnings"])


def test_store_refund_is_explicitly_not_customer_refund() -> None:
    analysis = build_customer_analysis(customer_snapshot(include_refund=True), "store_refund")

    assert analysis["evidence"][0]["source"] == "weidian.monthly_refunds"
    assert "不能归因到当前客户" in analysis["conclusion"]
    assert any("不能归因到单个客户" in warning for warning in analysis["warnings"])


def test_health_snapshot_staleness_is_a_high_priority_warning() -> None:
    analysis = build_customer_analysis(customer_snapshot(health_stale_days=5), "health_reason")

    assert any("早 5 天" in warning for warning in analysis["warnings"])
    assert analysis["actions"][0]["title"] == "核对健康快照"


def test_customer_question_routing_and_communication_boundary() -> None:
    assert infer_customer_analysis_type("这个客户最近销售表现如何") == "recent_performance"
    assert infer_customer_analysis_type("主要商品有哪些") == "products"
    assert infer_customer_analysis_type("这个客户退款多少") == "store_refund"
    assert infer_customer_analysis_type("内部应该优先核查什么") == "follow_up"
    assert is_customer_communication_request("帮我写一段回复客户的话术") is True
    assert is_customer_communication_request("内部应该怎么跟进这个客户") is False


def test_ai_prompt_is_internal_only_and_contains_no_secret() -> None:
    snapshot = customer_snapshot()
    analysis = build_customer_analysis(snapshot, "overview")
    messages = customer_analysis_messages(snapshot, analysis)

    assert "公司内部业务部门" in messages[0]["content"]
    assert "不得生成面向客户的回复" in messages[0]["content"]
    assert "customer-001" in messages[1]["content"]
    assert "api_key" not in messages[1]["content"]


@contextmanager
def fake_connection():
    yield None


def test_customer_analysis_uses_rule_mode_without_ai_configuration(monkeypatch) -> None:
    snapshot = customer_snapshot()
    user = UserContext("talent-user", "talent", "达人组长", "talent", "talent")
    request = SimpleNamespace(state=SimpleNamespace(request_id="req-customer-rule"))
    calls: list[str] = []

    class FakeCustomerService:
        def __init__(self, _conn) -> None:
            pass

        def analysis_snapshot(self, *_args, **_kwargs):
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
    monkeypatch.setattr(main_module, "CustomerService", FakeCustomerService)
    monkeypatch.setattr(main_module, "SettingsService", FakeSettingsService)
    monkeypatch.setattr(main_module, "request_ai_completion", forbidden_ai_call)
    body = CustomerAnalysisRequest(store_key="weidian", customer_id="customer-001", as_of="2026-08-11")

    result = asyncio.run(main_module.customer_analysis(body, request, user))

    assert calls == []
    assert result["data"]["mode"] == "rule_summary"
    assert result["data"]["configured"] is False
    assert result["data"]["customer_id"] == "customer-001"
    assert result["data"]["request_id"] == "req-customer-rule"


def test_customer_analysis_falls_back_when_provider_fails(monkeypatch) -> None:
    snapshot = customer_snapshot()
    user = UserContext("talent-user", "talent", "达人组长", "talent", "talent")
    request = SimpleNamespace(state=SimpleNamespace(request_id="req-customer-fallback"))

    class FakeCustomerService:
        def __init__(self, _conn) -> None:
            pass

        def analysis_snapshot(self, *_args, **_kwargs):
            return snapshot

    class FakeSettingsService:
        def __init__(self, _conn) -> None:
            pass

        def api_setting(self, _user, include_secret=False):
            return {"configured": True, "base_url": "https://example.test/v1", "api_key": "secret", "model_name": "model"}

    async def failing_ai_call(*_args):
        raise ApiError(502, "AI_PROVIDER_ERROR", "provider failed")

    monkeypatch.setattr(main_module, "connection", fake_connection)
    monkeypatch.setattr(main_module, "CustomerService", FakeCustomerService)
    monkeypatch.setattr(main_module, "SettingsService", FakeSettingsService)
    monkeypatch.setattr(main_module, "request_ai_completion", failing_ai_call)
    body = CustomerAnalysisRequest(store_key="weidian", customer_id="customer-001", as_of="2026-08-11")

    result = asyncio.run(main_module.customer_analysis(body, request, user))

    assert result["data"]["mode"] == "rule_summary"
    assert result["data"]["degraded"] is True
    assert any("规则诊断" in warning for warning in result["data"]["warnings"])


def test_chat_rejects_customer_reply_generation_even_when_ai_is_configured(monkeypatch) -> None:
    snapshot = customer_snapshot()
    user = UserContext("talent-user", "talent", "达人组长", "talent", "talent")
    request = SimpleNamespace(state=SimpleNamespace(request_id="req-chat-boundary"))

    class FakeCustomerService:
        def __init__(self, _conn) -> None:
            pass

        def analysis_snapshot(self, *_args, **_kwargs):
            return snapshot

    class FakeSettingsService:
        def __init__(self, _conn) -> None:
            pass

        def api_setting(self, _user, include_secret=False):
            return {"configured": True, "api_key": "secret"}

    async def forbidden_ai_call(*_args):
        raise AssertionError("customer communication requests must not reach the model")

    monkeypatch.setattr(main_module, "connection", fake_connection)
    monkeypatch.setattr(main_module, "CustomerService", FakeCustomerService)
    monkeypatch.setattr(main_module, "SettingsService", FakeSettingsService)
    monkeypatch.setattr(main_module, "request_ai_completion", forbidden_ai_call)
    body = ChatRequest(
        store_key="weidian",
        customer_id="customer-001",
        as_of="2026-08-11",
        message="帮我写一段回复客户的话术",
    )

    result = asyncio.run(main_module.ai_chat(body, request, user))

    assert result["data"]["mode"] == "rule_summary"
    assert "不生成面向客户的回复" in result["data"]["answer"]
