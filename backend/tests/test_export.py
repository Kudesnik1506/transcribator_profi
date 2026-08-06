import io

from docx import Document

from app.export import build_docx, build_srt, build_txt, export_filename, ms_to_srt_timestamp


class FakeSegment:
    def __init__(self, start_ms, end_ms, text):
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.text = text


SEGMENTS = [
    FakeSegment(0, 1500, "Первый абзац"),
    FakeSegment(1500, 4000, "Второй абзац про бюджет"),
]


def test_ms_to_srt_timestamp_formats_hours_minutes_seconds_millis():
    assert ms_to_srt_timestamp(3_661_500) == "01:01:01,500"


def test_ms_to_srt_timestamp_zero():
    assert ms_to_srt_timestamp(0) == "00:00:00,000"


def test_build_txt_is_plain_continuous_text_without_markup():
    result = build_txt(SEGMENTS)

    assert result == "Первый абзац\nВторой абзац про бюджет"
    assert "<" not in result
    assert "#" not in result


def test_build_srt_has_index_timecode_and_text_per_segment():
    result = build_srt(SEGMENTS)

    assert result == (
        "1\n00:00:00,000 --> 00:00:01,500\nПервый абзац\n\n"
        "2\n00:00:01,500 --> 00:00:04,000\nВторой абзац про бюджет"
    )


def test_export_filename_replaces_extension():
    assert export_filename("meeting.mp4", "srt") == "meeting.srt"
    assert export_filename("meeting.mp4", "txt") == "meeting.txt"
    assert export_filename("meeting.mp4", "docx") == "meeting.docx"


def test_export_filename_handles_no_extension():
    assert export_filename("meeting", "txt") == "meeting.txt"


def test_build_docx_produces_valid_document_with_segment_paragraphs():
    data = build_docx("meeting.mp4", SEGMENTS)

    doc = Document(io.BytesIO(data))
    paragraph_texts = [p.text for p in doc.paragraphs if p.text]

    assert "Первый абзац" in paragraph_texts
    assert "Второй абзац про бюджет" in paragraph_texts
