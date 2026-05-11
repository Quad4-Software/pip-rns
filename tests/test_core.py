"""Tests for core.py - orchestrator and retry helpers."""

from __future__ import annotations

from pip_rns.retry import retry


def test_retry_success_no_retry_needed():
    called = 0

    @retry(max_attempts=3)
    def fn():
        nonlocal called
        called += 1
        return 42

    assert fn() == 42
    assert called == 1


def test_retry_fails_once_then_succeeds():
    called = 0

    @retry(max_attempts=3, delay=0.01)
    def fn():
        nonlocal called
        called += 1
        if called < 2:
            raise ValueError("temporary")
        return "ok"

    assert fn() == "ok"
    assert called == 2


def test_retry_exhausted():
    called = 0

    @retry(max_attempts=3, delay=0.01)
    def fn():
        nonlocal called
        called += 1
        raise ValueError("always fails")

    try:
        fn()
        assert False, "should have raised"
    except ValueError as e:
        assert "always fails" in str(e)

    assert called == 3


def test_retry_custom_exception_filter():
    class CustomError(Exception):
        pass

    class OtherError(Exception):
        pass

    @retry(max_attempts=2, delay=0.01, exceptions=(CustomError,))
    def fn():
        raise OtherError("not caught")

    try:
        fn()
        assert False, "should have raised"
    except OtherError:
        pass


def test_retry_backoff_increases():
    import time

    delays = []

    def _sleep(secs):
        delays.append(secs)

    original_sleep = time.sleep
    time.sleep = _sleep

    try:
        called = 0

        @retry(max_attempts=4, delay=1.0, backoff=2.0)
        def fn():
            nonlocal called
            called += 1
            raise ValueError("fail")

        try:
            fn()
        except ValueError:
            pass

        assert called == 4
        assert len(delays) == 3
        assert delays == [1.0, 2.0, 4.0], delays
    finally:
        time.sleep = original_sleep
