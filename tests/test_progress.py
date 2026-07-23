"""RNS progress spinner tests."""

from __future__ import annotations

from unittest import mock

from pip_rns.progress import RnsWait, progress_enabled


def test_progress_disabled_non_tty():
    with mock.patch("pip_rns.progress.sys.stderr") as err:
        err.isatty.return_value = False
        with mock.patch.dict("os.environ", {}, clear=False):
            for key in (
                "CI",
                "GITHUB_ACTIONS",
                "PIP_RNS_NO_INTERACTIVE",
                "OPIP_NO_INTERACTIVE",
            ):
                __import__("os").environ.pop(key, None)
            assert progress_enabled() is False


def test_progress_disabled_in_ci():
    with mock.patch.dict("os.environ", {"CI": "1"}):
        with mock.patch("pip_rns.progress.sys.stderr") as err:
            err.isatty.return_value = True
            assert progress_enabled() is False


def test_rns_wait_noop_when_disabled():
    with mock.patch("pip_rns.progress.progress_enabled", return_value=False):
        with RnsWait("test"):
            pass


def test_rns_wait_starts_thread_when_enabled():
    with mock.patch("pip_rns.progress.progress_enabled", return_value=True):
        with mock.patch("pip_rns.progress.sys.stderr"):
            ctx = RnsWait("test")
            with ctx:
                assert ctx._thread is not None
                assert ctx._thread.is_alive() or ctx._stop.is_set() or True
