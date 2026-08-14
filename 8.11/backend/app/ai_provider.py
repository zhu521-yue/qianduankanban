from typing import Any

import httpx

from app.responses import ApiError
from app.settings import get_settings


async def request_ai_completion(config: dict[str, Any], messages: list[dict[str, str]]) -> str:
    base_url = str(config.get("base_url") or "").strip().rstrip("/")
    api_key = str(config.get("api_key") or "").strip()
    model_name = str(config.get("model_name") or "").strip() or get_settings().ai_default_model
    if not base_url or not api_key:
        raise ApiError(422, "AI_CONFIG_INCOMPLETE", "请完整填写base_url和api_key后再测试。")
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": get_settings().ai_temperature,
    }
    try:
        async with httpx.AsyncClient(timeout=get_settings().ai_request_timeout_seconds) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("大模型返回内容为空")
            return answer.strip()
    except ApiError:
        raise
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise ApiError(502, "AI_PROVIDER_ERROR", "AI接口调用失败，请检查地址、密钥和模型名称。") from exc
