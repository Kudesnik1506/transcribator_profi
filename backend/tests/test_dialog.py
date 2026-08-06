import pytest

from app.worker.dialog import TranscriptTooLongError, build_dialog_messages, estimate_tokens


def test_estimate_tokens_scales_with_length():
    assert estimate_tokens("a" * 300) == 150


def test_estimate_tokens_never_zero_for_nonempty_text():
    assert estimate_tokens("a") >= 1


def test_build_dialog_messages_includes_transcript_history_and_question():
    messages = build_dialog_messages(
        transcript_text="привет мир",
        history=[{"role": "user", "content": "первый вопрос"}, {"role": "assistant", "content": "первый ответ"}],
        question="второй вопрос",
        max_context_tokens=10_000,
    )

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "привет мир" in messages[1]["content"]
    assert messages[2] == {"role": "user", "content": "первый вопрос"}
    assert messages[3] == {"role": "assistant", "content": "первый ответ"}
    assert messages[-1] == {"role": "user", "content": "второй вопрос"}


def test_build_dialog_messages_raises_when_over_budget():
    with pytest.raises(TranscriptTooLongError):
        build_dialog_messages(
            transcript_text="a" * 100_000,
            history=[],
            question="вопрос",
            max_context_tokens=1_000,
        )


def test_build_dialog_messages_fits_within_budget():
    messages = build_dialog_messages(
        transcript_text="a" * 300,
        history=[],
        question="вопрос",
        max_context_tokens=1_000,
    )

    assert len(messages) == 3
