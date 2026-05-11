"""Terminal UI utilities: colored output, cross-platform, no external deps."""

from __future__ import annotations

import os
import sys

_show_color = True


def init(*, no_color: bool = False) -> None:
    global _show_color
    _show_color = (
        not no_color
        and os.environ.get("NO_COLOR") is None
        and os.environ.get("PIP_RNS_COLOR", "1") != "0"
        and sys.stdout.isatty()
    )


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
