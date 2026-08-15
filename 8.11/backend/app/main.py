from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Cookie, Depends, FastAPI, File, Form, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from psycopg import Error as PsycopgError

from app.ai_provider import request_ai_completion
from app.ai_query import execute_ai_query
from app.auth import authenticate, issue_session, read_session
from app.catalog import STORES, allowed_stores, scope_options
from app.database import close_pool, connection, open_pool
from app.periods import Grain, parse_date
from app.responses import ApiError, error_payload, ok
from app.schemas import AiQueryRequest, ApiSettingsUpdate, ChatRequest, CustomerAnalysisRequest, DashboardInsightRequest, HealthRulesUpdate, LoginRequest, UserContext
from app.services import (
    CustomerService,
    DashboardService,
    SettingsService,
    build_dashboard_insight,
    build_customer_analysis,
    customer_analysis_messages,
    dashboard_insight_messages,
    infer_customer_analysis_type,
    is_customer_communication_request,
    normalize_ai_summary,
)
from app.settings import get_settings
from app.uploads import UploadService, template_csv


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    open_pool()
    yield
    close_pool()


app = FastAPI(
    title="AI 客户看板 Backend",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID", "Idempotency-Key"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or f"req_{uuid4().hex}"
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status_code, content=error_payload(exc, request))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = [
        {"field": ".".join(str(item) for item in error["loc"]), "code": error["type"], "message": error["msg"]}
        for error in exc.errors()
    ]
    wrapped = ApiError(422, "VALIDATION_ERROR", "请求参数校验失败。", errors)
    return JSONResponse(status_code=422, content=error_payload(wrapped, request))


@app.exception_handler(PsycopgError)
async def database_error_handler(request: Request, _: PsycopgError):
    wrapped = ApiError(503, "DATABASE_UNAVAILABLE", "数据库暂时不可用，请稍后重试。")
    return JSONResponse(status_code=503, content=error_payload(wrapped, request))


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, _: Exception):
    wrapped = ApiError(500, "INTERNAL_ERROR", "服务处理请求失败。")
    return JSONResponse(status_code=500, content=error_payload(wrapped, request))


def current_user(
    session_token: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> UserContext:
    if not session_token:
        raise ApiError(401, "AUTH_REQUIRED", "请先登录。")
    return read_session(session_token)


def grain_value(value: str) -> Grain:
    try:
        return Grain(value)
    except ValueError as exc:
        raise ApiError(400, "GRAIN_INVALID", "时间维度仅支持 day、week、month、quarter、half。") from exc


@app.get("/api/v1/health", tags=["system"])
def health(request: Request):
    with connection() as conn:
        database = conn.execute("SELECT current_database() AS name").fetchone()["name"]
    return ok({"service": "ai-customer-dashboard-backend", "status": "UP", "database": database}, request=request)


@app.post("/api/v1/auth/login", tags=["auth"])
def login(body: LoginRequest, response: Response, request: Request):
    user = authenticate(body.username, body.password)
    token, expires_at = issue_session(user, settings.session_ttl_hours)
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.secure_cookie,
        samesite="lax",
        path="/",
    )
    return ok(
        {"user": user.__dict__, "expires_at": expires_at.isoformat()},
        message="登录成功",
        request=request,
    )


@app.get("/api/v1/auth/session", tags=["auth"])
def session(request: Request, user: UserContext = Depends(current_user)):
    return ok({"user": user.__dict__}, request=request)


@app.post("/api/v1/auth/logout", tags=["auth"])
def logout(
    response: Response,
    request: Request,
    session_token: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
):
    response.delete_cookie(settings.session_cookie_name, path="/")
    return ok(message="已退出登录", request=request)


@app.get("/api/v1/meta/options", tags=["meta"])
def meta_options(request: Request, user: UserContext = Depends(current_user)):
    store_keys = allowed_stores(user.role)
    stores = [
        {
            "key": STORES[key].key,
            "name": STORES[key].name,
            "platform_key": STORES[key].platform_key,
            "platform_name": STORES[key].platform_name,
            "group_key": STORES[key].group_key,
            "group_name": STORES[key].group_name,
        }
        for key in store_keys
    ]
    return ok(
        {
            "role": user.role,
            "group_key": user.group_key,
            "stores": stores,
            "scopes": scope_options(user.role),
            "grains": [grain.value for grain in Grain],
            "upload": {"extensions": [".csv", ".xlsx"], "max_bytes": settings.max_upload_bytes, "can_upload": user.role != "manager"},
        },
        request=request,
    )


@app.get("/api/v1/dashboard", tags=["dashboard"])
def dashboard(
    request: Request,
    scope_key: str,
    as_of: str | None = None,
    trend_grain: str = "month",
    refund_grain: str = "half",
    user: UserContext = Depends(current_user),
):
    with connection() as conn:
        service = DashboardService(conn)
        resolved_date = parse_date(as_of) if as_of else service.latest_date(user, scope_key)
        data = service.dashboard(user, scope_key, resolved_date, grain_value(trend_grain), grain_value(refund_grain))
    return ok(data, request=request)


@app.get("/api/v1/customers", tags=["customers"])
def customers(
    request: Request,
    scope_key: str,
    as_of: str | None = None,
    grain: str = "half",
    search: str | None = None,
    status: str | None = None,
    sort_by: str = "amount",
    sort_order: str = "desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: UserContext = Depends(current_user),
):
    with connection() as conn:
        resolved_date = parse_date(as_of) if as_of else DashboardService(conn).latest_date(user, scope_key)
        data = CustomerService(conn).list_customers(
            user, scope_key, resolved_date, grain_value(grain), search, status, sort_by, sort_order, page, page_size
        )
    return ok(data, request=request)


@app.get("/api/v1/customers/{store_key}/{customer_id}", tags=["customers"])
def customer_detail(store_key: str, customer_id: str, request: Request, as_of: str | None = None, user: UserContext = Depends(current_user)):
    with connection() as conn:
        resolved_date = parse_date(as_of) if as_of else DashboardService(conn).repo.latest_data_date((store_key,))
        if not resolved_date:
            raise ApiError(404, "DATA_NOT_FOUND", "当前店铺没有可展示的销售数据。")
        data = CustomerService(conn).detail(user, store_key, customer_id, resolved_date)
    return ok(data, request=request)


@app.get("/api/v1/uploads/template", tags=["uploads"], response_class=PlainTextResponse)
def upload_template(_: UserContext = Depends(current_user)):
    return PlainTextResponse(
        template_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="sales-upload-template.csv"'},
    )


@app.post("/api/v1/uploads/sales", tags=["uploads"])
def upload_sales(
    request: Request,
    store_key: Annotated[str, Form()],
    file: UploadFile = File(...),
    mode: Annotated[str, Form()] = "preview",
    user: UserContext = Depends(current_user),
):
    content = file.file.read(settings.max_upload_bytes + 1)
    with connection() as conn:
        data = UploadService(conn, settings.max_upload_bytes).process(user, store_key, file.filename or "upload", content, mode)
    return ok(data, message="文件处理完成", request=request)


@app.get("/api/v1/uploads", tags=["uploads"])
def upload_records(request: Request, limit: int = Query(default=100, ge=1, le=500), user: UserContext = Depends(current_user)):
    with connection() as conn:
        data = UploadService(conn, settings.max_upload_bytes).list_tasks(user, limit)
    return ok({"items": data}, request=request)


@app.get("/api/v1/uploads/{task_id}", tags=["uploads"])
def upload_task(task_id: str, request: Request, user: UserContext = Depends(current_user)):
    with connection() as conn:
        data = UploadService(conn, settings.max_upload_bytes).task(task_id, include_errors=True)
    if user.role != "manager" and data["store_key"] not in set(allowed_stores(user.role)):
        raise ApiError(403, "UPLOAD_FORBIDDEN", "当前账号无权查看该上传任务。")
    return ok(data, request=request)


@app.get("/api/v1/settings/health-rules", tags=["settings"])
def health_rules(request: Request, user: UserContext = Depends(current_user)):
    with connection() as conn:
        data = SettingsService(conn).health_rules(user)
    return ok({"groups": data}, request=request)


@app.put("/api/v1/settings/health-rules", tags=["settings"])
def update_health_rules(body: HealthRulesUpdate, request: Request, user: UserContext = Depends(current_user)):
    with connection() as conn:
        data = SettingsService(conn).update_health_rules(user, [item.model_dump() for item in body.rules])
        conn.commit()
    return ok(data, message="客户状态规则已保存并同步到客户健康度表", request=request)


@app.get("/api/v1/settings/ai", tags=["settings"])
def ai_setting(request: Request, user: UserContext = Depends(current_user)):
    with connection() as conn:
        data = SettingsService(conn).api_setting(user)
    return ok(data, request=request)


@app.put("/api/v1/settings/ai", tags=["settings"])
async def update_ai_setting(body: ApiSettingsUpdate, request: Request, user: UserContext = Depends(current_user)):
    with connection() as conn:
        service = SettingsService(conn)
        config = service.resolve_api_setting(user, str(body.base_url), body.api_key, body.model_name)
    await request_ai_completion(
        config,
        [{"role": "user", "content": "这是配置保存前校验，请只回复：连接成功"}],
    )
    data = service.update_api_setting(user, config)
    return ok(data, message="AI接口测试通过并已保存", request=request)


@app.post("/api/v1/settings/ai/test", tags=["settings"])
async def test_ai_setting(body: ApiSettingsUpdate, request: Request, user: UserContext = Depends(current_user)):
    with connection() as conn:
        config = SettingsService(conn).resolve_api_setting(user, str(body.base_url), body.api_key, body.model_name)
    answer = await request_ai_completion(
        config,
        [{"role": "user", "content": "这是AI接口连接测试，请只回复：连接成功"}],
    )
    return ok(
        {"model_name": config["model_name"], "reply_preview": answer[:200]},
        message="AI接口连接测试成功",
        request=request,
    )


@app.post("/api/v1/ai/dashboard-insight", tags=["ai"])
async def dashboard_insight(body: DashboardInsightRequest, request: Request, user: UserContext = Depends(current_user)):
    with connection() as conn:
        dashboard_service = DashboardService(conn)
        resolved_date = parse_date(body.as_of) if body.as_of else dashboard_service.latest_date(user, body.scope_key)
        snapshot = dashboard_service.dashboard(
            user,
            body.scope_key,
            resolved_date,
            grain_value(body.trend_grain),
            grain_value(body.refund_grain),
        )
        api_config = SettingsService(conn).api_setting(user, include_secret=True)

    insight = build_dashboard_insight(snapshot)
    insight.update(
        {
            "mode": "rule_summary",
            "configured": bool(api_config.get("configured")),
            "degraded": False,
            "scope_key": body.scope_key,
            "as_of": resolved_date.isoformat(),
            "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
            "request_id": request.state.request_id,
        }
    )
    if api_config.get("configured") and not insight["empty"]:
        try:
            answer = await request_ai_completion(api_config, dashboard_insight_messages(insight))
        except ApiError:
            insight["degraded"] = True
            insight["warnings"].append("AI 服务暂不可用，已展示基于数据库指标生成的规则摘要。")
        else:
            insight["mode"] = "ai"
            insight["summary"] = normalize_ai_summary(answer, insight["summary"])
    return ok(insight, request=request)


@app.post("/api/v1/ai/customer-analysis", tags=["ai"])
async def customer_analysis(body: CustomerAnalysisRequest, request: Request, user: UserContext = Depends(current_user)):
    with connection() as conn:
        snapshot = CustomerService(conn).analysis_snapshot(
            user,
            body.store_key,
            body.customer_id,
            parse_date(body.as_of),
            include_store_refund=body.analysis_type == "store_refund",
        )
        api_config = SettingsService(conn).api_setting(user, include_secret=True)
    analysis = build_customer_analysis(snapshot, body.analysis_type)
    analysis.update(
        {
            "mode": "rule_summary",
            "configured": bool(api_config.get("configured")),
            "degraded": False,
            "store_key": snapshot["store_key"],
            "store_name": snapshot["store_name"],
            "customer_id": snapshot["customer_id"],
            "display_name": snapshot["display_name"],
            "as_of": snapshot["as_of"],
            "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
            "request_id": request.state.request_id,
        }
    )
    if api_config.get("configured") and not analysis["empty"]:
        try:
            answer = await request_ai_completion(api_config, customer_analysis_messages(snapshot, analysis))
        except ApiError:
            analysis["degraded"] = True
            analysis["warnings"].append("AI 服务暂不可用，已展示基于客户数据库指标生成的规则诊断。")
        else:
            analysis["mode"] = "ai"
            analysis["summary"] = normalize_ai_summary(answer, analysis["summary"])
    return ok(analysis, request=request)


@app.post("/api/v1/ai/query", tags=["ai"])
async def ai_query(body: AiQueryRequest, request: Request, user: UserContext = Depends(current_user)):
    with connection() as conn:
        api_config = SettingsService(conn).api_setting(user, include_secret=True)
        data = await execute_ai_query(conn, user, body, api_config)
    data.update(
        {
            "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
            "request_id": request.state.request_id,
        }
    )
    return ok(data, request=request)


@app.post("/api/v1/ai/chat", tags=["ai"])
async def ai_chat(body: ChatRequest, request: Request, user: UserContext = Depends(current_user)):
    analysis_type = infer_customer_analysis_type(body.message)
    with connection() as conn:
        snapshot = CustomerService(conn).analysis_snapshot(
            user,
            body.store_key,
            body.customer_id,
            parse_date(body.as_of),
            include_store_refund=analysis_type == "store_refund",
        )
        api_config = SettingsService(conn).api_setting(user, include_secret=True)
    analysis = build_customer_analysis(snapshot, analysis_type)
    if is_customer_communication_request(body.message):
        answer = "本项目仅供业务部门进行内部经营分析，不生成面向客户的回复、沟通话术、营销文案或客服文本。"
        return ok(
            {
                "answer": answer,
                "mode": "rule_summary",
                "configured": bool(api_config.get("configured")),
                "degraded": False,
                "evidence": analysis["evidence"],
                "actions": analysis["actions"],
                "warnings": analysis["warnings"],
            },
            request=request,
        )
    if not api_config.get("configured"):
        return ok(
            {
                "answer": analysis["summary"],
                "mode": "rule_summary",
                "configured": False,
                "degraded": False,
                "evidence": analysis["evidence"],
                "actions": analysis["actions"],
                "warnings": analysis["warnings"],
            },
            request=request,
        )
    messages = customer_analysis_messages(snapshot, analysis)
    messages.extend(item for item in body.history[-10:] if item.get("role") in {"user", "assistant"} and item.get("content"))
    messages.append({"role": "user", "content": body.message})
    try:
        answer = await request_ai_completion(api_config, messages)
    except ApiError:
        return ok(
            {
                "answer": analysis["summary"],
                "mode": "rule_summary",
                "configured": True,
                "degraded": True,
                "evidence": analysis["evidence"],
                "actions": analysis["actions"],
                "warnings": [*analysis["warnings"], "AI 服务暂不可用，已返回规则诊断。"],
            },
            request=request,
        )
    return ok(
        {
            "answer": normalize_ai_summary(answer, analysis["summary"]),
            "mode": "ai",
            "configured": True,
            "degraded": False,
            "evidence": analysis["evidence"],
            "actions": analysis["actions"],
            "warnings": analysis["warnings"],
        },
        request=request,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=settings.app_env == "development")
