from dataclasses import dataclass
from datetime import datetime

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


class UploadSummary(BaseModel):
    id: str
    status: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    created_at: datetime
