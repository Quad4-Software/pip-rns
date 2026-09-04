"""Terminal UI utilities: colored output, cross-platform, no external deps."""

from __future__ import annotations

import contextlib
import os
import sys

_show_color = False


def configure_stdio() -> None:
    """Prefer UTF-8 on stdout/stderr so UI glyphs do not crash classic Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            with contextlib.suppress(Exception):
                reconfigure(errors="replace")


def _env_truthy(name: str) -> bool:
    val = os.environ.get(name)
    if val is None:
        return False
    return val.strip().lower() not in ("", "0", "false", "no", "off")


def _windows_color_host_ok() -> bool:
    if os.environ.get("WT_SESSION"):
        return True
    if _env_truthy("ANSICON") or _env_truthy("ConEmuANSI"):
        return True
    term = (os.environ.get("TERM") or "").strip().lower()
    return bool(term.startswith("xterm") or term in ("cygwin", "ansi", "mintty"))


def should_enable_color(
    *,
    no_color: bool = False,
    color_mode: str | None = None,
) -> bool:
    mode = (color_mode or os.environ.get("PIP_RNS_COLOR", "auto")).strip().lower()
    if no_color or os.environ.get("NO_COLOR") is not None:
        return False
    if mode in ("0", "never", "off", "false", "no"):
        return False
    if _env_truthy("FORCE_COLOR") or mode in ("always", "1", "on", "true", "yes"):
        return True

    if _env_truthy("CI") or _env_truthy("GITHUB_ACTIONS"):
        return False
    if _env_truthy("PIP_RNS_NO_INTERACTIVE"):
        return False

    try:
        if not sys.stdout.isatty():
            return False
    except Exception:
        return False

    if sys.platform == "win32" and not _windows_color_host_ok():
        return False
    return True


def init(*, no_color: bool = False) -> None:
    global _show_color
    _show_color = should_enable_color(no_color=no_color)


def _c(code: str) -> str:
    return f"\033[{code}m" if _show_color else ""


def bold(text: str) -> str:
    return f"{_c('1')}{text}{_c('0')}"


def green(text: str) -> str:
    return f"{_c('32')}{text}{_c('0')}"


def cyan(text: str) -> str:
    return f"{_c('36')}{text}{_c('0')}"


def yellow(text: str) -> str:
    return f"{_c('33')}{text}{_c('0')}"


def dim(text: str) -> str:
    return f"{_c('2')}{text}{_c('0')}"


def header(text: str) -> str:
    return bold(cyan(text))


def success(text: str) -> str:
    return bold(green(text))
