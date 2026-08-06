import json

import httpx

from app.config import settings

CHAT_COMPLETIONS_URL = f"{settings.timeweb_ai_gateway_url}/chat/completions"

SYSTEM_PROMPT = (
    "Ты составляешь сводку транскрипта совещания. "
    "Верни строго JSON-массив строк — от 5 до 15 пунктов, без markdown и пояснений вокруг. "
    "Каждый пункт — законченная мысль: тема, решение или действие."
)


class AIGatewayError(RuntimeError):
    pass


def summarize(transcript_text: str) -> list[str]:
    body = {
        "model": settings.timeweb_ai_gateway_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcript_text},
        ],
    }
    headers = {"Authorization": f"Bearer {settings.timeweb_ai_gateway_key}"}

    with httpx.Client(timeout=120.0) as client:
        response = client.post(CHAT_COMPLETIONS_URL, json=body, headers=headers)
    response.raise_for_status()

    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise AIGatewayError(f"unexpected response shape: {data}") from exc

    try:
        items = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AIGatewayError(f"model did not return valid JSON: {content!r}") from exc

    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise AIGatewayError(f"expected a JSON array of strings, got: {items!r}")

    return items
