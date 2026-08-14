from dataclasses import dataclass

from app.responses import ApiError


@dataclass(frozen=True)
class Store:
    key: str
    name: str
    schema_name: str
    platform_key: str
    platform_name: str
    group_key: str
    group_name: str
    nickname_column: str | None
    health_score_column: str


@dataclass(frozen=True)
class HealthRuleGroup:
    key: str
    name: str
    table_name: str
    health_tables: tuple[tuple[str, str], ...]


STORES: dict[str, Store] = {
    "weidian": Store("weidian", "微店", "weidian", "weidian", "微店", "talent", "达人组", "affiliate_nickname", "customer_health_score"),
    "doudian_children": Store("doudian_children", "儿童服饰旗舰店", "doudianChildren", "doudian", "抖店", "talent", "达人组", "customer_nickname", "customer_health_score"),
    "doudian_kocotree": Store("doudian_kocotree", "Kocotree服饰配件店", "doudianKocotree", "doudian", "抖店", "talent", "达人组", "customer_nickname", "customer_health_score"),
    "kuaishou": Store("kuaishou", "快手小店", "kuaishouxiaodian", "kuaishou", "快手小店", "talent", "达人组", "customer_nickname", "customer_health_score"),
    "youzan_qijian": Store("youzan_qijian", "有赞旗舰店", "qijian", "youzan", "有赞", "private", "私域组", None, "customer_score"),
    "youzan_muying": Store("youzan_muying", "母婴旗舰店", "muyinqijian", "youzan", "有赞", "private", "私域组", None, "customer_score"),
    "kuaituantuan": Store("kuaituantuan", "快团团", "kuaituantuan", "kuaituantuan", "快团团", "private", "私域组", None, "customer_score"),
    "alibaba": Store("alibaba", "阿里巴巴", "alibaba", "alibaba", "阿里巴巴", "distribution", "分销组", "buyer_nickname", "customer_score"),
    "jushuitan": Store("jushuitan", "聚水潭", "jushuitan", "jushuitan", "聚水潭", "distribution", "分销组", None, "customer_score"),
}

GROUP_STORES = {
    group: tuple(store.key for store in STORES.values() if store.group_key == group)
    for group in ("talent", "private", "distribution")
}

SCOPE_STORES: dict[str, tuple[str, ...]] = {
    "all": tuple(STORES),
    "talent": GROUP_STORES["talent"],
    "talent.weidian": ("weidian",),
    "talent.doudian": ("doudian_children", "doudian_kocotree"),
    "talent.doudian.children": ("doudian_children",),
    "talent.doudian.kocotree": ("doudian_kocotree",),
    "talent.kuaishou": ("kuaishou",),
    "private": GROUP_STORES["private"],
    "private.youzan": ("youzan_qijian", "youzan_muying"),
    "private.youzan.qijian": ("youzan_qijian",),
    "private.youzan.muying": ("youzan_muying",),
    "private.kuaituantuan": ("kuaituantuan",),
    "distribution": GROUP_STORES["distribution"],
    "distribution.alibaba": ("alibaba",),
    "distribution.jushuitan": ("jushuitan",),
}

ROLE_GROUP = {
    "manager": None,
    "talent": "talent",
    "private": "private",
    "distribution": "distribution",
}

CUSTOMER_HEALTH_STATUSES = ("高活跃", "活跃", "稳定", "观察", "风险", "流失预警", "流失")

HEALTH_RULE_GROUPS: dict[str, HealthRuleGroup] = {
    "talent": HealthRuleGroup(
        "talent",
        "达人组",
        "talent_customer_status_action",
        (
            ("daren", "customer_health_detail"),
            ("doudian", "half_year_customer_health"),
            ("weidian", "customer_health_detail"),
            ("doudianChildren", "customer_health_detail"),
            ("doudianKocotree", "customer_health_detail"),
            ("kuaishouxiaodian", "customer_health_detail"),
        ),
    ),
    "private": HealthRuleGroup(
        "private",
        "私域组",
        "private_customer_status_action",
        (
            ("siyu", "customer_health_detail"),
            ("youzan", "customer_health_detail"),
            ("qijian", "customer_health_detail"),
            ("muyinqijian", "customer_health_detail"),
            ("kuaituantuan", "customer_health_detail"),
        ),
    ),
    "distribution": HealthRuleGroup(
        "distribution",
        "分销组",
        "distribution_customer_status_action",
        (
            ("fenxiao", "customer_health_detail"),
            ("alibaba", "customer_health_detail"),
            ("jushuitan", "customer_health_detail"),
        ),
    ),
}


def allowed_stores(role: str) -> tuple[str, ...]:
    if role == "manager":
        return tuple(STORES)
    group = ROLE_GROUP.get(role)
    if not group:
        raise ApiError(403, "ROLE_FORBIDDEN", "当前账号角色无有效数据范围。")
    return GROUP_STORES[group]


def resolve_scope(role: str, scope_key: str) -> tuple[str, ...]:
    requested = SCOPE_STORES.get(scope_key)
    if requested is None:
        raise ApiError(400, "SCOPE_INVALID", f"未知数据范围：{scope_key}")
    permitted = set(allowed_stores(role))
    if not set(requested).issubset(permitted):
        raise ApiError(403, "SCOPE_FORBIDDEN", "当前账号无权访问该小组或店铺。")
    return requested


def scope_options(role: str) -> list[dict[str, object]]:
    permitted = set(allowed_stores(role))
    return [
        {"scope_key": key, "store_keys": list(stores)}
        for key, stores in SCOPE_STORES.items()
        if set(stores).issubset(permitted)
    ]
