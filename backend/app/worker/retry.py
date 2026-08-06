import time
from typing import Callable, TypeVar

T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay_sec: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    last_exception: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:
            last_exception = exc
            if attempt < max_attempts - 1:
                sleep(base_delay_sec * (2**attempt))
    assert last_exception is not None
    raise last_exception
