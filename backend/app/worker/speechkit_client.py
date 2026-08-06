"""Yandex SpeechKit v3 async recognition client.

Contract assumed here (recognizeFileAsync, base64 content, Operation polling
via operation.api.cloud.yandex.net) is our best reading of the v3 REST API —
the live docs are behind a CAPTCHA we could not clear during implementation.
Must be verified against a real YANDEX_API_KEY before this goes to production
(tracked as open question #2 in docs/spec.md).
"""

import base64
import time
from dataclasses import dataclass

import httpx

from app.config import settings

RECOGNIZE_URL = "https://stt.api.cloud.yandex.net/stt/v3/recognizeFileAsync"
OPERATION_URL_TEMPLATE = "https://operation.api.cloud.yandex.net/operations/{operation_id}"


@dataclass
class Segment:
    start_ms: int
    end_ms: int
    text: str


class SpeechKitError(RuntimeError):
    pass


# D9/D15: two SpeechKit tariffs selected by recognitionModel.model — "general"
# (full price, ~30 min) and "deferred-general" (~4x cheaper, up to 24h queue).
_MODE_TO_MODEL = {"fast": "general", "deferred": "deferred-general"}


def model_for_mode(mode: str) -> str:
    try:
        return _MODE_TO_MODEL[mode]
    except KeyError:
        raise ValueError(f"unknown processing mode: {mode!r}") from None


# How long we're willing to poll before giving up on one attempt: "fast"
# stays within its own ~30 min promise; "deferred" must cover D15's "up to
# 24h" — polling every 5s for 24h would be 17280 requests, so back off to
# a coarser interval instead of just raising max_polls at the same cadence.
_MODE_TO_POLL_CONFIG = {
    "fast": (5.0, 360),  # 5s * 360 = 30 min
    "deferred": (60.0, 1440),  # 60s * 1440 = 24h
}


def poll_config_for_mode(mode: str) -> tuple[float, int]:
    try:
        return _MODE_TO_POLL_CONFIG[mode]
    except KeyError:
        raise ValueError(f"unknown processing mode: {mode!r}") from None


def _auth_headers() -> dict:
    return {
        "Authorization": f"Api-Key {settings.yandex_api_key}",
        "x-folder-id": settings.yandex_folder_id,
    }


def _submit(audio_bytes: bytes, model: str, client: httpx.Client) -> str:
    body = {
        "content": base64.b64encode(audio_bytes).decode("ascii"),
        "recognitionModel": {
            "model": model,
            "audioFormat": {"containerAudio": {"containerAudioType": "OGG_OPUS"}},
            "languageRestriction": {"languageCode": ["ru-RU"]},
            "audioProcessingType": "FULL_DATA",
        },
    }
    response = client.post(RECOGNIZE_URL, json=body, headers=_auth_headers())
    response.raise_for_status()
    data = response.json()
    operation_id = data.get("id")
    if not operation_id:
        raise SpeechKitError(f"no operation id in recognizeFileAsync response: {data}")
    return operation_id


def _poll(operation_id: str, client: httpx.Client, poll_interval_sec: float, max_polls: int) -> dict:
    url = OPERATION_URL_TEMPLATE.format(operation_id=operation_id)
    for attempt in range(max_polls):
        response = client.get(url, headers=_auth_headers())
        response.raise_for_status()
        data = response.json()
        if data.get("done"):
            if "error" in data:
                raise SpeechKitError(f"recognition failed: {data['error']}")
            return data.get("response", {})
        if attempt < max_polls - 1:
            time.sleep(poll_interval_sec)
    raise SpeechKitError(f"operation {operation_id} did not complete within {max_polls} polls")


def _time_to_ms(value: str) -> int:
    return round(float(value.rstrip("s")) * 1000)


def _parse_segments(result: dict) -> list[Segment]:
    segments: list[Segment] = []
    for asr_result_chunk in result.get("chunks", []):
        alternatives = asr_result_chunk.get("alternatives", [])
        if not alternatives:
            continue
        best = alternatives[0]
        words = best.get("words", [])
        if not words:
            continue
        start_ms = _time_to_ms(words[0]["startTime"])
        end_ms = _time_to_ms(words[-1]["endTime"])
        text = best.get("text") or " ".join(w["word"] for w in words)
        segments.append(Segment(start_ms=start_ms, end_ms=end_ms, text=text))
    return segments


def transcribe(
    audio_bytes: bytes, *, model: str = "general", poll_interval_sec: float = 5.0, max_polls: int = 360
) -> list[Segment]:
    with httpx.Client(timeout=60.0) as client:
        operation_id = _submit(audio_bytes, model, client)
        result = _poll(operation_id, client, poll_interval_sec, max_polls)
    return _parse_segments(result)
