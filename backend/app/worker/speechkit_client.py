"""Yandex SpeechKit v3 async recognition client.

Verified against a real YANDEX_API_KEY / YANDEX_FOLDER_ID (2026-08-09, live
prod credentials) — the recognizeFileAsync + operation-polling submission
flow was correct, but the result-fetching contract was not: the finished
Operation carries no "response" field at all. Results must be pulled
separately from `getRecognition`, which streams newline-delimited JSON
events (not a single JSON object). Each recognized utterance shows up as a
"final" event, optionally followed by a "finalRefinement" event carrying a
punctuated/capitalized "normalizedText" for the same `final_index` — when
present, that's what we want. Word timings arrive as `startTimeMs`/
`endTimeMs`, already in milliseconds (not the `"0.5s"`-style duration
strings this module originally assumed). See
yandex/cloud/ai/stt/v3/stt.proto (yandex-cloud/cloudapi) for the full
StreamingResponse schema.
"""

import base64
import json
import time
from dataclasses import dataclass

import httpx

from app.config import settings

RECOGNIZE_URL = "https://stt.api.cloud.yandex.net/stt/v3/recognizeFileAsync"
GET_RECOGNITION_URL = "https://stt.api.cloud.yandex.net/stt/v3/getRecognition"
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


def _poll(operation_id: str, client: httpx.Client, poll_interval_sec: float, max_polls: int) -> None:
    url = OPERATION_URL_TEMPLATE.format(operation_id=operation_id)
    for attempt in range(max_polls):
        response = client.get(url, headers=_auth_headers())
        response.raise_for_status()
        data = response.json()
        if data.get("done"):
            if "error" in data:
                raise SpeechKitError(f"recognition failed: {data['error']}")
            return
        if attempt < max_polls - 1:
            time.sleep(poll_interval_sec)
    raise SpeechKitError(f"operation {operation_id} did not complete within {max_polls} polls")


def _ms(value: str) -> int:
    return round(float(value))


def _segment_from_alternative_update(alternative_update: dict) -> Segment | None:
    alternatives = alternative_update.get("alternatives", [])
    if not alternatives:
        return None
    best = alternatives[0]
    words = best.get("words", [])
    if not words:
        return None
    start_ms = _ms(words[0]["startTimeMs"])
    end_ms = _ms(words[-1]["endTimeMs"])
    text = best.get("text") or " ".join(w["text"] for w in words)
    return Segment(start_ms=start_ms, end_ms=end_ms, text=text)


def _fetch_segments(operation_id: str, client: httpx.Client) -> list[Segment]:
    # Only "final" and "finalRefinement" events carry a usable transcript;
    # "partial"/"eouUpdate"/"statusCode" etc. are interim/marker events we
    # skip. A "finalRefinement" is preferred over the raw "final" for the
    # same final_index — it has punctuation/capitalization applied.
    raw_by_index: dict[str, dict] = {}
    refined_by_index: dict[str, dict] = {}

    with client.stream(
        "GET", GET_RECOGNITION_URL, params={"operation_id": operation_id}, headers=_auth_headers()
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            line = line.strip()
            if not line:
                continue
            result = json.loads(line).get("result", {})
            index = result.get("audioCursors", {}).get("finalIndex")
            if index is None:
                continue
            if "final" in result:
                raw_by_index[index] = result["final"]
            elif "finalRefinement" in result:
                refined_by_index[index] = result["finalRefinement"]["normalizedText"]

    segments: list[Segment] = []
    for index in sorted(raw_by_index.keys() | refined_by_index.keys(), key=int):
        alternative_update = refined_by_index.get(index) or raw_by_index[index]
        segment = _segment_from_alternative_update(alternative_update)
        if segment is not None:
            segments.append(segment)
    return segments


def transcribe(
    audio_bytes: bytes, *, model: str = "general", poll_interval_sec: float = 5.0, max_polls: int = 360
) -> list[Segment]:
    with httpx.Client(timeout=60.0) as client:
        operation_id = _submit(audio_bytes, model, client)
        _poll(operation_id, client, poll_interval_sec, max_polls)
        return _fetch_segments(operation_id, client)
