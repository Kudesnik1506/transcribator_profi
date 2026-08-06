from app.worker.speechkit_client import Segment
from app.worker.timecodes import offset_segments


def test_offset_segments_shifts_start_and_end():
    segments = [
        Segment(start_ms=0, end_ms=1000, text="привет"),
        Segment(start_ms=1000, end_ms=2000, text="мир"),
    ]

    result = offset_segments(segments, offset_sec=900.0)

    assert result[0].start_ms == 900_000
    assert result[0].end_ms == 901_000
    assert result[1].start_ms == 901_000
    assert result[1].end_ms == 902_000
    assert result[0].text == "привет"


def test_offset_segments_zero_offset_is_noop():
    segments = [Segment(start_ms=100, end_ms=200, text="x")]

    result = offset_segments(segments, offset_sec=0)

    assert result[0].start_ms == 100
    assert result[0].end_ms == 200


def test_offset_segments_empty_list():
    assert offset_segments([], offset_sec=500) == []
