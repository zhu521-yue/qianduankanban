import asyncio
from types import SimpleNamespace

import app.ai_provider as provider_module
from app.ai_provider import request_ai_completion


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"choices": [{"message": {"content": "连接成功"}}]}


class FakeClient:
    def __init__(self, calls: list[dict[str, object]]) -> None:
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def post(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return FakeResponse()


def test_provider_uses_server_side_secret_and_openai_compatible_endpoint(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    settings = SimpleNamespace(ai_default_model="default", ai_temperature=0.2, ai_request_timeout_seconds=15)
    monkeypatch.setattr(provider_module, "get_settings", lambda: settings)
    monkeypatch.setattr(provider_module.httpx, "AsyncClient", lambda timeout: FakeClient(calls))

    answer = asyncio.run(
        request_ai_completion(
            {"base_url": "https://provider.example/v1/", "api_key": "server-secret", "model_name": "model-x"},
            [{"role": "user", "content": "ping"}],
        )
    )

    assert answer == "连接成功"
    assert calls[0]["url"] == "https://provider.example/v1/chat/completions"
    assert calls[0]["headers"] == {"Authorization": "Bearer server-secret", "Content-Type": "application/json"}
    assert calls[0]["json"] == {
        "model": "model-x",
        "messages": [{"role": "user", "content": "ping"}],
        "temperature": 0.2,
    }
