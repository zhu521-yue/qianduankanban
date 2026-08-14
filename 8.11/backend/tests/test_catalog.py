import pytest

from app.catalog import resolve_scope
from app.responses import ApiError


def test_talent_scope_contains_expected_stores() -> None:
    assert resolve_scope("talent", "talent.doudian") == ("doudian_children", "doudian_kocotree")


def test_group_cannot_cross_scope() -> None:
    with pytest.raises(ApiError) as caught:
        resolve_scope("private", "talent.weidian")
    assert caught.value.status_code == 403


def test_manager_can_use_all_scope() -> None:
    assert len(resolve_scope("manager", "all")) == 9

