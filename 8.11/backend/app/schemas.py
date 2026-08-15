from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


@dataclass(frozen=True)
class UserContext:
    id: str
    username: str
    display_name: str
    role: str
    group_key: str | None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class HealthRuleInput(BaseModel):
    customer_health_status: str = Field(min_length=1, max_length=32)
    state_instructions: str = Field(min_length=1, max_length=2000)
    follow_up_action: str = Field(min_length=1, max_length=2000)


class HealthRulesUpdate(BaseModel):
    rules: list[HealthRuleInput] = Field(min_length=7, max_length=7)


class ApiSettingsUpdate(BaseModel):
    base_url: HttpUrl
    api_key: str | None = Field(default=None, max_length=1000)
    model_name: str | None = Field(default=None, max_length=120)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    store_key: str = Field(min_length=1, max_length=64)
    customer_id: str = Field(min_length=1, max_length=160)
    as_of: str
    history: list[dict[str, str]] = Field(default_factory=list, max_length=20)


class DashboardInsightRequest(BaseModel):
    scope_key: str = Field(min_length=1, max_length=80)
    as_of: str | None = None
    trend_grain: str = Field(default="month", max_length=16)
    refund_grain: str = Field(default="half", max_length=16)


class CustomerAnalysisRequest(BaseModel):
    store_key: str = Field(min_length=1, max_length=64)
    customer_id: str = Field(min_length=1, max_length=160)
    as_of: str
    analysis_type: Literal[
        "overview",
        "recent_performance",
        "health_reason",
        "products",
        "store_refund",
        "follow_up",
    ] = "overview"


class AiQueryContext(BaseModel):
    scope_key: str = Field(min_length=1, max_length=80)
    as_of: str | None = None
    grain: Literal["day", "week", "month", "quarter", "half"] = "month"
    route: str | None = Field(default=None, max_length=200)


class AiQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    context: AiQueryContext
    history: list[dict[str, str]] = Field(default_factory=list, max_length=6)


class AiQueryPlan(BaseModel):
    metric_key: str = Field(min_length=1, max_length=64)
    scope_key: str = Field(min_length=1, max_length=80)
    grain: Literal["day", "week", "month", "quarter", "half"]
    as_of: str | None = None
    group_by: Literal["total", "group", "platform", "store", "period", "customer", "product", "health_status"]
    comparison: Literal["none", "previous_period"] = "none"
    filters: dict[str, str] = Field(default_factory=dict)
    limit: int = Field(default=10, ge=1, le=100)
    output_type: Literal["cards", "table", "line", "bar"] = "table"
    sort_by: Literal["value", "change"] = "value"
    sort_direction: Literal["asc", "desc"] = "desc"


class UploadSummary(BaseModel):
    id: str
    status: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    created_at: datetime
