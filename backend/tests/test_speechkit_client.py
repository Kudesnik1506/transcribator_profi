import httpx
import pytest
import respx

from app.worker.speechkit_client import RECOGNIZE_URL, Segment, SpeechKitError, transcribe

OPERATION_URL = "https://operation.api.cloud.yandex.net/operations/op-123"


@respx.mock
def test_transcribe_returns_segments_from_completed_operation():
    respx.post(RECOGNIZE_URL).mock(return_value=httpx.Response(200, json={"id": "op-123"}))
    respx.get(OPERATION_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "done": True,
                "response": {
                    "chunks": [
                        {
                            "alternatives": [
                                {
                                    "text": "привет мир",
                                    "words": [
                                        {"word": "привет", "startTime": "0.100s", "endTime": "0.500s"},
                                        {"word": "мир", "startTime": "0.600s", "endTime": "1.000s"},
                                    ],
                                }
                            ]
                        }
                    ]
                },
            },
        )
    )

    segments = transcribe(b"fake-audio-bytes", poll_interval_sec=0, max_polls=1)

    assert segments == [Segment(start_ms=100, end_ms=1000, text="привет мир")]


@respx.mock
def test_transcribe_polls_until_operation_done():
    respx.post(RECOGNIZE_URL).mock(return_value=httpx.Response(200, json={"id": "op-123"}))
    respx.get(OPERATION_URL).mock(
        side_effect=[
            httpx.Response(200, json={"done": False}),
            httpx.Response(200, json={"done": True, "response": {"chunks": []}}),
        ]
    )

    segments = transcribe(b"fake-audio-bytes", poll_interval_sec=0, max_polls=5)

    assert segments == []


@respx.mock
def test_transcribe_raises_on_recognition_error():
    respx.post(RECOGNIZE_URL).mock(return_value=httpx.Response(200, json={"id": "op-123"}))
    respx.get(OPERATION_URL).mock(
        return_value=httpx.Response(200, json={"done": True, "error": {"code": 3, "message": "bad audio"}})
    )

    with pytest.raises(SpeechKitError):
        transcribe(b"fake-audio-bytes", poll_interval_sec=0, max_polls=1)


@respx.mock
def test_transcribe_raises_when_operation_never_completes():
    respx.post(RECOGNIZE_URL).mock(return_value=httpx.Response(200, json={"id": "op-123"}))
    respx.get(OPERATION_URL).mock(return_value=httpx.Response(200, json={"done": False}))

    with pytest.raises(SpeechKitError):
        transcribe(b"fake-audio-bytes", poll_interval_sec=0, max_polls=3)
