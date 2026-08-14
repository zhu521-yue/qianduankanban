import pytest

from app.catalog import CUSTOMER_HEALTH_STATUSES, HEALTH_RULE_GROUPS
from app.responses import ApiError
from app.schemas import UserContext
from app.services import SettingsService


def rules() -> list[dict[str, str]]:
    return [
        {
            "customer_health_status": status,
            "state_instructions": f"{status}说明",
            "follow_up_action": f"{status}动作",
        }
        for status in CUSTOMER_HEALTH_STATUSES
    ]


class FakeSettingsRepository:
    def __init__(self) -> None:
        self.updated_group: str | None = None

    def health_rules(self, group_key: str) -> list[dict[str, str]]:
        return rules()

    def update_health_rules(self, group_key: str, values: list[dict[str, str]]) -> dict[str, object]:
        self.updated_group = group_key
        return {"group_key": group_key, "updated_rule_count": len(values), "updated_health_rows": {}}


def service_with_fake_repo() -> tuple[SettingsService, FakeSettingsRepository]:
    service = SettingsService(None)  # type: ignore[arg-type]
    repository = FakeSettingsRepository()
    service.repo = repository  # type: ignore[assignment]
    return service, repository


def test_fixed_health_status_order() -> None:
    assert CUSTOMER_HEALTH_STATUSES == ("高活跃", "活跃", "稳定", "观察", "风险", "流失预警", "流失")


def test_health_rule_sync_covers_group_platform_and_store_tables() -> None:
    assert HEALTH_RULE_GROUPS["talent"].health_tables == (
        ("daren", "customer_health_detail"),
        ("doudian", "half_year_customer_health"),
        ("weidian", "customer_health_detail"),
        ("doudianChildren", "customer_health_detail"),
        ("doudianKocotree", "customer_health_detail"),
        ("kuaishouxiaodian", "customer_health_detail"),
    )
    assert ("youzan", "customer_health_detail") in HEALTH_RULE_GROUPS["private"].health_tables
    assert HEALTH_RULE_GROUPS["distribution"].health_tables == (
        ("fenxiao", "customer_health_detail"),
        ("alibaba", "customer_health_detail"),
        ("jushuitan", "customer_health_detail"),
    )


def test_manager_has_no_customer_health_rule_module() -> None:
    service, _ = service_with_fake_repo()
    user = UserContext("manager", "manager", "主管", "manager", None)
    groups = service.health_rules(user)
    assert groups == []


def test_group_can_only_update_its_own_rule_table() -> None:
    service, repository = service_with_fake_repo()
    user = UserContext("talent", "talent", "达人组", "talent", "talent")
    result = service.update_health_rules(user, rules())
    assert repository.updated_group == "talent"
    assert result["updated_rule_count"] == 7


def test_reordered_statuses_are_rejected() -> None:
    service, _ = service_with_fake_repo()
    user = UserContext("private", "private", "私域组", "private", "private")
    values = rules()
    values[0], values[1] = values[1], values[0]
    with pytest.raises(ApiError) as caught:
        service.update_health_rules(user, values)
    assert caught.value.code == "HEALTH_RULE_STATUS_INVALID"


def test_manager_cannot_save_rules() -> None:
    service, _ = service_with_fake_repo()
    user = UserContext("manager", "manager", "主管", "manager", None)
    with pytest.raises(ApiError) as caught:
        service.update_health_rules(user, rules())
    assert caught.value.status_code == 403
