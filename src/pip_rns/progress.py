"""TTY progress spinner for long RNS / subprocess waits."""

from __future__ import annotations

import os
import sys
import threading
import time


def _env_truthy(name: str) -> bool:
    val = os.environ.get(name)
    if val is None:
        return False
    return val.strip().lower() not in ("", "0", "false", "no", "off")


def progress_enabled() -> bool:
    """Return True when a spinner should run on stderr."""
    if _env_truthy("CI") or _env_truthy("GITHUB_ACTIONS"):
        return False
    if _env_truthy("PIP_RNS_NO_INTERACTIVE") or _env_truthy("OPIP_NO_INTERACTIVE"):
        return False
    try:
        return sys.stderr.isatty()
    except Exception:
        return False


class RnsWait:
    """Context manager: show elapsed wait on stderr while a blocking call runs."""

    def __init__(self, message: str = "Waiting on Reticulum") -> None:
        self.message = message
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._enabled = progress_enabled()

    def __enter__(self) -> RnsWait:
        if not self._enabled:
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._enabled or self._thread is None:
            return None
        self._stop.set()
        self._thread.join(timeout=2.0)
        try:
            sys.stderr.write("\r" + " " * 60 + "\r")
            sys.stderr.flush()
        except Exception:
            pass
        return None

    def _run(self) -> None:
        frames = ("|", "/", "-", "\\")
        t0 = time.time()
        i = 0
        while not self._stop.wait(0.12):
            elapsed = int(time.time() - t0)
            frame = frames[i % len(frames)]
            i += 1
            try:
                sys.stderr.write(f"\r{frame} {self.message}… {elapsed}s")
                sys.stderr.flush()
            except Exception:
                break
