import json

import httpx
import pytest
import respx

from app.worker.speechkit_client import (
    GET_RECOGNITION_URL,
    RECOGNIZE_URL,
    Segment,
    SpeechKitError,
    model_for_mode,
    poll_config_for_mode,
    transcribe,
)

OPERATION_URL = "https://operation.api.cloud.yandex.net/operations/op-123"


def _ndjson(*events: dict) -> str:
    return "\n".join(json.dumps(e) for e in events)


def _final_line(index: str, text: str, words: list[tuple[str, str, str]]) -> dict:
    return {
        "result": {
            "audioCursors": {"finalIndex": index},
            "final": {
                "alternatives": [
                    {
                        "text": text,
                        "words": [{"text": w, "startTimeMs": s, "endTimeMs": e} for w, s, e in words],
                    }
                ]
            },
        }
    }


def _refinement_line(index: str, text: str, words: list[tuple[str, str, str]]) -> dict:
    return {
        "result": {
            "audioCursors": {"finalIndex": index},
            "finalRefinement": {
                "finalIndex": index,
                "normalizedText": {
                    "alternatives": [
                        {
                            "text": text,
                            "words": [{"text": w, "startTimeMs": s, "endTimeMs": e} for w, s, e in words],
                        }
                    ]
                },
            },
        }
    }


def _eou_line(index: str, time_ms: str) -> dict:
    return {"result": {"audioCursors": {"finalIndex": index}, "eouUpdate": {"timeMs": time_ms}}}


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
    respx.get(OPERATION_URL).mock(return_value=httpx.Response(200, json={"done": True}))
    respx.get(GET_RECOGNITION_URL).mock(return_value=httpx.Response(200, text=""))

    transcribe(b"fake-audio-bytes", model="deferred-general", poll_interval_sec=0, max_polls=1)

    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body["recognitionModel"]["model"] == "deferred-general"


@respx.mock
def test_transcribe_returns_segments_from_final_when_no_refinement():
    respx.post(RECOGNIZE_URL).mock(return_value=httpx.Response(200, json={"id": "op-123"}))
    respx.get(OPERATION_URL).mock(return_value=httpx.Response(200, json={"done": True}))
    respx.get(GET_RECOGNITION_URL).mock(
        return_value=httpx.Response(
            200,
            text=_ndjson(
                _final_line("0", "привет мир", [("привет", "100", "500"), ("мир", "600", "1000")]),
                _eou_line("0", "1000"),
            ),
        )
    )

    segments = transcribe(b"fake-audio-bytes", poll_interval_sec=0, max_polls=1)

    assert segments == [Segment(start_ms=100, end_ms=1000, text="привет мир")]


@respx.mock
def test_transcribe_prefers_normalized_refinement_over_raw_final():
    respx.post(RECOGNIZE_URL).mock(return_value=httpx.Response(200, json={"id": "op-123"}))
    respx.get(OPERATION_URL).mock(return_value=httpx.Response(200, json={"done": True}))
    respx.get(GET_RECOGNITION_URL).mock(
        return_value=httpx.Response(
            200,
            text=_ndjson(
                _final_line("0", "привет мир", [("привет", "100", "500"), ("мир", "600", "1000")]),
                _refinement_line("0", "Привет, мир.", [("привет", "100", "500"), ("мир", "600", "1000")]),
                _eou_line("0", "1000"),
            ),
        )
    )

    segments = transcribe(b"fake-audio-bytes", poll_interval_sec=0, max_polls=1)

    assert segments == [Segment(start_ms=100, end_ms=1000, text="Привет, мир.")]


@respx.mock
def test_transcribe_orders_multiple_utterances_by_index():
    respx.post(RECOGNIZE_URL).mock(return_value=httpx.Response(200, json={"id": "op-123"}))
    respx.get(OPERATION_URL).mock(return_value=httpx.Response(200, json={"done": True}))
    respx.get(GET_RECOGNITION_URL).mock(
        return_value=httpx.Response(
            200,
            # second utterance's events arrive before the first's refinement —
            # output must still be ordered by final_index, not arrival order.
            text=_ndjson(
                _final_line("0", "первая фраза", [("первая", "0", "500"), ("фраза", "500", "900")]),
                _final_line("1", "вторая фраза", [("вторая", "1000", "1500"), ("фраза", "1500", "1900")]),
                _refinement_line("0", "Первая фраза.", [("первая", "0", "500"), ("фраза", "500", "900")]),
            ),
        )
    )

    segments = transcribe(b"fake-audio-bytes", poll_interval_sec=0, max_polls=1)

    assert segments == [
        Segment(start_ms=0, end_ms=900, text="Первая фраза."),
        Segment(start_ms=1000, end_ms=1900, text="вторая фраза"),
    ]


@respx.mock
def test_transcribe_ignores_events_without_words():
    respx.post(RECOGNIZE_URL).mock(return_value=httpx.Response(200, json={"id": "op-123"}))
    respx.get(OPERATION_URL).mock(return_value=httpx.Response(200, json={"done": True}))
    respx.get(GET_RECOGNITION_URL).mock(
        return_value=httpx.Response(
            200,
            text=_ndjson(_eou_line("0", "0"), {"result": {"audioCursors": {"finalIndex": "0"}}}),
        )
    )

    segments = transcribe(b"fake-audio-bytes", poll_interval_sec=0, max_polls=1)

    assert segments == []


@respx.mock
def test_transcribe_polls_until_operation_done():
    respx.post(RECOGNIZE_URL).mock(return_value=httpx.Response(200, json={"id": "op-123"}))
    respx.get(OPERATION_URL).mock(
        side_effect=[
            httpx.Response(200, json={"done": False}),
            httpx.Response(200, json={"done": True}),
        ]
    )
    respx.get(GET_RECOGNITION_URL).mock(return_value=httpx.Response(200, text=""))

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
