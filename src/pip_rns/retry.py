# Copyright (c) 2026, Quad4 (quad4.io)
"""Simple retry decorator with exponential backoff."""

from __future__ import annotations

import time
from typing import Callable


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """Retry a call with exponential backoff on the given exception types."""

    def decorator(fn: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            last: Exception | None = None
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:  # noqa: PERF203
                    last = e
                    if attempt < max_attempts - 1:
                        time.sleep(delay * (backoff**attempt))
            if last is not None:
                raise last

        return wrapper

    return decorator
