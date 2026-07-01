"""Exponential-backoff retry for LLM calls."""

from __future__ import annotations

import functools
import time
from typing import Callable, TypeVar

from .base import LLMError

T = TypeVar("T")


def with_retries(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry the decorated function on retryable LLMError.

    Total attempts = 1 initial + max_retries retries.
    Backoff: base_delay * 2**attempt, capped at max_delay.
    """
    def deco(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            last: LLMError | None = None
            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except LLMError as e:
                    last = e
                    if not e.retryable or attempt == max_retries:
                        raise
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    if delay > 0:
                        time.sleep(delay)
            assert last is not None
            raise last
        return wrapper
    return deco
