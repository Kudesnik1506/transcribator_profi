from app.worker.speechkit_client import Segment


def offset_segments(segments: list[Segment], offset_sec: float) -> list[Segment]:
    offset_ms = round(offset_sec * 1000)
    return [
        Segment(start_ms=s.start_ms + offset_ms, end_ms=s.end_ms + offset_ms, text=s.text) for s in segments
    ]
