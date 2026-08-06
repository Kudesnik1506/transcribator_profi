import pytest

from app.worker.retry import retry_with_backoff


def test_retry_with_backoff_returns_on_first_success():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    result = retry_with_backoff(fn, max_attempts=3, base_delay_sec=0, sleep=lambda s: None)

    assert result == "ok"
    assert len(calls) == 1


def test_retry_with_backoff_retries_until_success():
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    result = retry_with_backoff(fn, max_attempts=3, base_delay_sec=0, sleep=lambda s: None)

    assert result == "ok"
    assert attempts["n"] == 3


def test_retry_with_backoff_raises_after_exhausting_attempts():
    def fn():
        raise RuntimeError("persistent failure")

    with pytest.raises(RuntimeError, match="persistent failure"):
        retry_with_backoff(fn, max_attempts=3, base_delay_sec=0, sleep=lambda s: None)


def test_retry_with_backoff_uses_increasing_delay():
    sleeps = []

    def fn():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        retry_with_backoff(fn, max_attempts=3, base_delay_sec=1.0, sleep=lambda s: sleeps.append(s))

    assert sleeps == [1.0, 2.0]
