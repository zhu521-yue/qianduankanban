from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Awaitable, Callable

from pydantic import ValidationError

from app.ai_metric_catalog import METRIC_CATALOG, catalog_prompt, validate_query_plan
from app.ai_provider import request_ai_completion
from app.ai_tools import AiToolRegistry
from app.catalog import CUSTOMER_HEALTH_STATUSES, STORES, resolve_scope
from app.periods import Grain, parse_date
from app.responses import ApiError
from app.schemas import AiQueryPlan, AiQueryRequest, UserContext


AiCompletion = Callable[[dict[str, Any], list[dict[str, str]]], Awaitable[str]]

SUPPORTED_QUESTION_EXAMPLES = [
    "本月销售额是多少？",
    "本月哪个店铺销售额下降最多？",
    "最近6个月销售趋势怎么样？",
    "本季度哪个店铺退款额最高？",
    "列出半年销售额最高的10个风险客户。",
    "当前半年金额Top5商品是什么？",
    "哪些店铺的数据日期比较旧？",
]


def _default_scope(user: UserContext) -> str:
    return "all" if user.role == "manager" else str(user.group_key)


def is_forbidden_query(question: str) -> bool:
    normalized = "".join(question.lower().split())
    keywords = (
        "回复客户", "怎么回复", "沟通话术", "营销文案", "发给客户", "给客户发",
        "删除数据库", "修改数据库", "写入数据库", "更新数据库", "执行sql", "运行sql",
        "修改客户状态", "保存客户状态", "自动上传", "确认写入", "自动提交",
        "预测销售", "预测退款", "预测流失", "利润", "毛利", "库存", "成本",
    )
    if "预测" in normalized and any(metric in normalized for metric in ("销售", "退款", "流失", "客户", "商品")):
        return True
    return any(keyword in normalized for keyword in keywords)


def _scope_from_question(question: str, fallback: str) -> str:
    normalized = question.lower()
    store_scope = {
        "微店": "talent.weidian",
        "儿童服饰旗舰店": "talent.doudian.children",
        "儿童店": "talent.doudian.children",
        "kocotree服饰配件店": "talent.doudian.kocotree",
        "kocotree": "talent.doudian.kocotree",
        "快手小店": "talent.kuaishou",
        "有赞旗舰店": "private.youzan.qijian",
        "母婴旗舰店": "private.youzan.muying",
        "快团团": "private.kuaituantuan",
        "阿里巴巴": "distribution.alibaba",
        "聚水潭": "distribution.jushuitan",
    }
    for label, scope in store_scope.items():
        if label in normalized:
            return scope
    platform_scope = {
        "抖店": "talent.doudian",
        "有赞": "private.youzan",
    }
    for label, scope in platform_scope.items():
        if label in normalized:
            return scope
    group_scope = {"达人组": "talent", "私域组": "private", "分销组": "distribution"}
    for label, scope in group_scope.items():
        if label in normalized:
            return scope
    return fallback


def _grain_from_question(question: str, fallback: str) -> str:
    normalized = question.lower()
    if re.search(r"最近\s*\d+\s*个?月", normalized):
        return "month"
    if "半年" in normalized or "半年度" in normalized:
        return "half"
    if "季度" in normalized or "本季" in normalized:
        return "quarter"
    if "本月" in normalized or "上月" in normalized or "月度" in normalized:
        return "month"
    if "本周" in normalized or "上周" in normalized or "周度" in normalized:
        return "week"
    if "今天" in normalized or "今日" in normalized or "当天" in normalized:
        return "day"
    return fallback


def _limit_from_question(question: str, default: int, maximum: int) -> int:
    matched = re.search(r"(?:top|前|最高的?|最低的?|列出)\s*(\d{1,3})", question.lower())
    if not matched:
        matched = re.search(r"最近\s*(\d{1,2})\s*个", question.lower())
    if not matched:
        return min(default, maximum)
    return max(1, min(int(matched.group(1)), maximum))


def infer_query_plan(question: str, context: dict[str, Any], user: UserContext) -> dict[str, Any]:
    if is_forbidden_query(question):
        raise ApiError(422, "AI_QUERY_UNSUPPORTED", "问看板只提供内部经营数据查询，不执行写操作、预测或客户沟通任务。")
    normalized = question.lower().strip()
    scope_key = _scope_from_question(normalized, str(context.get("scope_key") or _default_scope(user)))
    grain = _grain_from_question(normalized, str(context.get("grain") or "month"))
    filters: dict[str, str] = {}
    status = next((item for item in CUSTOMER_HEALTH_STATUSES if item in question), None)
    if status:
        filters["health_status"] = status

    if ("数据" in normalized and any(word in normalized for word in ("日期", "更新", "新鲜", "滞后", "旧"))) or "最新到" in normalized:
        metric_key, group_by, grain = "data_freshness", "store", "day"
    elif "预售" in normalized:
        metric_key, group_by = "presale_amount", "product" if any(word in normalized for word in ("商品", "top", "排名", "哪些")) else "total"
        if grain not in {"month", "quarter", "half"}:
            grain = "month"
    elif "退款" in normalized:
        metric_key = "refund_amount"
        group_by = "store" if any(word in normalized for word in ("哪个店", "店铺", "门店", "来自哪些")) else "group" if any(word in normalized for word in ("哪个组", "小组")) else "platform" if "平台" in normalized else "total"
        if grain == "day":
            grain = "month"
    elif any(word in normalized for word in ("商品", "产品", "货品")):
        metric_key = "top_product_quantity" if any(word in normalized for word in ("数量", "件数", "销量")) else "top_product_amount"
        group_by = "product"
    elif "客户" in normalized and ("销售" in normalized or any(word in normalized for word in ("排名", "top", "最高", "最低", "列出", "前"))):
        metric_key, group_by = "customer_ranking", "customer"
    elif ("客户" in normalized and status) or any(word in normalized for word in ("健康分布", "流失分布", "风险分布", "状态分布")):
        metric_key = "customer_health_count"
        group_by = "store" if any(word in normalized for word in ("哪个店", "店铺")) else "health_status"
        grain = "week"
    elif "客户" in normalized and any(word in normalized for word in ("多少", "数量", "客户数")):
        metric_key = "active_customer_count"
        group_by = "store" if "店铺" in normalized else "total"
    elif "趋势" in normalized or re.search(r"最近\s*\d+\s*个", normalized):
        metric_key, group_by = "sales_trend", "period"
    elif any(word in normalized for word in ("贡献", "来自哪些", "主要来自")):
        metric_key = "scope_contribution"
        group_by = "group" if any(word in normalized for word in ("哪个组", "小组")) else "platform" if "平台" in normalized else "store"
    elif any(word in normalized for word in ("下降", "增长", "变化", "环比", "同比", "比上")):
        metric_key = "sales_change_rate"
        group_by = "group" if any(word in normalized for word in ("哪个组", "小组")) else "platform" if "平台" in normalized else "store" if any(word in normalized for word in ("哪个店", "店铺", "门店")) else "total"
    elif "销售" in normalized or "销售额" in normalized or "交易额" in normalized:
        metric_key = "sales_amount"
        group_by = "group" if any(word in normalized for word in ("哪个组", "小组")) else "platform" if "平台" in normalized else "store" if any(word in normalized for word in ("哪个店", "店铺", "门店")) else "total"
    else:
        raise ApiError(
            422,
            "AI_QUERY_UNSUPPORTED",
            "暂时无法识别这个问题，请询问销售、退款、客户、健康、商品、预售或数据日期。",
        )

    definition = METRIC_CATALOG[metric_key]
    descending = not any(word in normalized for word in ("下降最多", "最低", "最少", "最差"))
    sort_by = "change" if any(word in normalized for word in ("下降", "增长", "变化", "环比")) and metric_key in {"sales_change_rate", "refund_amount"} else "value"
    default_limit = 6 if metric_key == "sales_trend" else 10 if metric_key == "customer_ranking" else 5 if "top" in normalized or "排名" in normalized else definition.max_limit
    output_type = definition.default_output_type
    plan = {
        "metric_key": metric_key,
        "scope_key": scope_key,
        "grain": grain,
        "as_of": context.get("as_of"),
        "group_by": group_by,
        "comparison": "previous_period" if metric_key in {"sales_amount", "sales_change_rate", "scope_contribution", "active_customer_count", "refund_amount"} else "none",
        "filters": filters if "health_status" in definition.filters else {},
        "limit": _limit_from_question(normalized, default_limit, definition.max_limit),
        "output_type": output_type,
        "sort_by": sort_by,
        "sort_direction": "desc" if descending else "asc",
    }
    try:
        parsed = AiQueryPlan.model_validate(plan).model_dump()
    except ValidationError as exc:
        raise ApiError(422, "AI_QUERY_UNSUPPORTED", "问题已识别，但当前指标不支持请求的范围或粒度。") from exc
    validate_query_plan(parsed)
    return parsed


def _extract_json(answer: str) -> dict[str, Any]:
    cleaned = answer.replace("```json", "").replace("```", "").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("AI未返回JSON对象")
    payload = json.loads(cleaned[start:end + 1])
    if not isinstance(payload, dict):
        raise ValueError("AI查询计划不是对象")
    return payload


async def parse_plan_with_ai(
    question: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
    api_config: dict[str, Any],
    completion: AiCompletion = request_ai_completion,
) -> dict[str, Any]:
    prompt = json.dumps(
        {
            "question": question,
            "context": context,
            "history": history[-6:],
            "catalog": catalog_prompt(),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    answer = await completion(
        api_config,
        [
            {
                "role": "system",
                "content": (
                    "你是内部经营看板的意图解析器。只能从指标目录选择，不得输出SQL、表名、字段名或用户角色。"
                    "只输出一个JSON对象，字段必须是metric_key、scope_key、grain、as_of、group_by、comparison、filters、limit、"
                    "output_type、sort_by、sort_direction。缺少范围、日期或粒度时沿用context。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    try:
        plan = AiQueryPlan.model_validate(_extract_json(answer)).model_dump()
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        raise ApiError(502, "AI_PLAN_INVALID", "AI未能生成合法的受控查询计划。") from exc
    validate_query_plan(plan)
    return plan


async def explain_result_with_ai(
    question: str,
    plan: dict[str, Any],
    result: dict[str, Any],
    api_config: dict[str, Any],
    completion: AiCompletion = request_ai_completion,
) -> str:
    payload = json.dumps(
        {
            "question": question,
            "query_plan": plan,
            "rule_answer": result["answer"],
            "evidence": result["evidence"],
            "rows": result["table"]["rows"][:20],
            "warnings": result["warnings"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    answer = await completion(
        api_config,
        [
            {
                "role": "system",
                "content": (
                    "你是公司内部业务部门的经营分析助手。只能解释给定的验证结果，不得增加、修改或猜测数字，"
                    "不得生成客户回复、营销文案或任何写操作。输出2至4句中文纯文本，300字以内。"
                ),
            },
            {"role": "user", "content": payload},
        ],
    )
    normalized = " ".join(answer.replace("```", "").split()).strip()
    return normalized[:500] if normalized else result["answer"]


async def execute_ai_query(
    conn: Any,
    user: UserContext,
    body: AiQueryRequest,
    api_config: dict[str, Any],
    completion: AiCompletion = request_ai_completion,
) -> dict[str, Any]:
    question = body.question.strip()
    if is_forbidden_query(question):
        raise ApiError(422, "AI_QUERY_UNSUPPORTED", "问看板只提供内部经营数据查询，不执行写操作、预测或客户沟通任务。")
    context = body.context.model_dump()
    configured = bool(api_config.get("configured") and api_config.get("base_url") and api_config.get("api_key"))
    degraded = False
    plan_source = "rule"
    if configured:
        try:
            plan = await parse_plan_with_ai(question, context, body.history, api_config, completion)
            plan_source = "ai"
        except ApiError:
            plan = infer_query_plan(question, context, user)
            degraded = True
    else:
        plan = infer_query_plan(question, context, user)
    definition = validate_query_plan(plan)
    stores = resolve_scope(user.role, str(plan["scope_key"]))
    latest = AiToolRegistry(conn).dashboard.latest_data_date(stores)
    if not latest:
        raise ApiError(404, "DATA_NOT_FOUND", "当前查询范围没有可用销售数据。")
    resolved_as_of = parse_date(str(plan.get("as_of") or context.get("as_of") or latest.isoformat()))
    plan["as_of"] = resolved_as_of.isoformat()
    registry = AiToolRegistry(conn)
    result = registry.execute(user, plan, definition, resolved_as_of)
    answer = result["answer"]
    mode = "rule_summary"
    if configured and not result["empty"]:
        try:
            answer = await explain_result_with_ai(question, plan, result, api_config, completion)
            mode = "ai"
        except ApiError:
            degraded = True
            result["warnings"].append("AI解释暂不可用，已展示基于数据库工具结果生成的规则答案。")
    if degraded and plan_source == "rule":
        result["warnings"].append("AI意图解析失败，本次使用受控模板完成查询。")
    route = context.get("route") if str(context.get("route") or "").startswith("#/") else f"#/{user.role}/overall"
    return {
        "mode": mode,
        "configured": configured,
        "degraded": degraded,
        "empty": result["empty"],
        "answer": answer,
        "query_plan": plan,
        "evidence": result["evidence"],
        "table": result["table"],
        "chart": result["chart"],
        "scope": {
            "scope_key": plan["scope_key"],
            "store_keys": result["store_keys"],
            "as_of": result["as_of"],
            "grain": result["grain"],
        },
        "warnings": list(dict.fromkeys(result["warnings"])),
        "target": {"route": route, "module": result["target_module"]},
        "plan_source": plan_source,
        "supported_questions": SUPPORTED_QUESTION_EXAMPLES,
    }
