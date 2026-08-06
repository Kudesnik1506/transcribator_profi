import httpx
import respx

from app.worker.ai_gateway_client import CHAT_COMPLETIONS_URL, stream_answer


@respx.mock
def test_stream_answer_yields_content_deltas():
    sse_body = (
        'data: {"choices": [{"delta": {"content": "При"}}]}\n\n'
        'data: {"choices": [{"delta": {"content": "вет"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    respx.post(CHAT_COMPLETIONS_URL).mock(return_value=httpx.Response(200, content=sse_body.encode()))

    chunks = list(stream_answer([{"role": "user", "content": "вопрос"}]))

    assert chunks == ["При", "вет"]


@respx.mock
def test_stream_answer_ignores_chunks_without_content():
    sse_body = (
        'data: {"choices": [{"delta": {}}]}\n\n'
        'data: {"choices": [{"delta": {"content": "текст"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    respx.post(CHAT_COMPLETIONS_URL).mock(return_value=httpx.Response(200, content=sse_body.encode()))

    chunks = list(stream_answer([{"role": "user", "content": "вопрос"}]))

    assert chunks == ["текст"]


@respx.mock
def test_stream_answer_sends_stream_true_and_messages():
    route = respx.post(CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
    )

    list(stream_answer([{"role": "user", "content": "вопрос про бюджет"}]))

    import json

    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body["stream"] is True
    assert sent_body["messages"] == [{"role": "user", "content": "вопрос про бюджет"}]
