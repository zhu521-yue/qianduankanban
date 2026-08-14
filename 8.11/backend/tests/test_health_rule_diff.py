from app.repositories import _changed_health_rules


def rule(status: str, state: str = "说明", action: str = "动作") -> dict[str, str]:
    return {
        "customer_health_status": status,
        "state_instructions": state,
        "follow_up_action": action,
    }


def test_identical_rules_have_no_changes() -> None:
    current = [rule("高活跃"), rule("流失")]
    assert _changed_health_rules(current, [dict(item) for item in current]) == []


def test_only_changed_or_missing_rules_are_returned() -> None:
    current = [rule("高活跃"), rule("流失")]
    submitted = [rule("高活跃", state="新说明"), rule("流失"), rule("风险")]
    assert [item["customer_health_status"] for item in _changed_health_rules(current, submitted)] == ["高活跃", "风险"]
