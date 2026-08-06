import json

import httpx
import pytest
import respx

from app.worker.ai_gateway_client import CHAT_COMPLETIONS_URL, AIGatewayError, summarize


@respx.mock
def test_summarize_returns_items_from_response():
    respx.post(CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(["Обсудили бюджет", "Поставили задачи"])}}]},
        )
    )

    items = summarize("длинный транскрипт совещания")

    assert items == ["Обсудили бюджет", "Поставили задачи"]


@respx.mock
def test_summarize_sends_transcript_and_model_in_request():
    route = respx.post(CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "[]"}}]})
    )

    summarize("транскрипт про бюджет")

    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body["model"]
    assert "транскрипт про бюджет" in sent_body["messages"][-1]["content"]


@respx.mock
def test_summarize_raises_on_malformed_json_response():
    respx.post(CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "это не json"}}]})
    )

    with pytest.raises(AIGatewayError):
        summarize("транскрипт")


@respx.mock
def test_summarize_raises_when_items_not_a_list_of_strings():
    respx.post(CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"oops": 1})}}]})
    )

    with pytest.raises(AIGatewayError):
        summarize("транскрипт")
