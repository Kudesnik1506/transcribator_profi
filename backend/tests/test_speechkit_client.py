import json

import httpx
import pytest
import respx

from app.worker.speechkit_client import (
    RECOGNIZE_URL,
    Segment,
    SpeechKitError,
    model_for_mode,
    poll_config_for_mode,
    transcribe,
)

OPERATION_URL = "https://operation.api.cloud.yandex.net/operations/op-123"


def test_model_for_mode_maps_fast_to_general():
    assert model_for_mode("fast") == "general"


def test_model_for_mode_maps_deferred_to_deferred_general():
    assert model_for_mode("deferred") == "deferred-general"


def test_poll_config_for_fast_mode_covers_about_30_minutes():
    poll_interval_sec, max_polls = poll_config_for_mode("fast")

    assert poll_interval_sec * max_polls >= 30 * 60
    assert poll_interval_sec * max_polls < 60 * 60


def test_poll_config_for_deferred_mode_covers_up_to_24_hours():
    poll_interval_sec, max_polls = poll_config_for_mode("deferred")

    assert poll_interval_sec * max_polls >= 24 * 60 * 60


def test_poll_config_for_mode_rejects_unknown_mode():
    with pytest.raises(ValueError):
        poll_config_for_mode("turbo")


def test_model_for_mode_rejects_unknown_mode():
    with pytest.raises(ValueError):
        model_for_mode("turbo")


@respx.mock
def test_transcribe_sends_model_matching_mode():
    route = respx.post(RECOGNIZE_URL).mock(return_value=httpx.Response(200, json={"id": "op-123"}))
    respx.get(OPERATION_URL).mock(return_value=httpx.Response(200, json={"done": True, "response": {"chunks": []}}))

    transcribe(b"fake-audio-bytes", model="deferred-general", poll_interval_sec=0, max_polls=1)

    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body["recognitionModel"]["model"] == "deferred-general"


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
