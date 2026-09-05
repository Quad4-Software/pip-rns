# Copyright (c) 2026, Quad4 (quad4.io)
"""Terminal colors and styling (stdlib only, Linux/macOS/Windows)."""

import contextlib
import os
import sys

_CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
}

_enabled = False
_initialized = False


def configure_stdio():
    """Prefer UTF-8 on stdout/stderr so styled output works on classic Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            with contextlib.suppress(Exception):
                reconfigure(errors="replace")


def _env_truthy(name):
    val = os.environ.get(name)
    if val is None:
        return False
    return val.strip().lower() not in ("", "0", "false", "no", "off")


def _windows_color_host_ok():
    """Return True only on modern Windows hosts that handle ANSI well.

    Classic cmd.exe and PowerShell stay colorless unless FORCE_COLOR.
    """
    if os.environ.get("WT_SESSION"):
        return True
    if _env_truthy("ANSICON") or _env_truthy("ConEmuANSI"):
        return True
    term = (os.environ.get("TERM") or "").strip().lower()
    return bool(term.startswith("xterm") or term in ("cygwin", "ansi", "mintty"))


def enable_windows_vt():
    """Enable ANSI escape processing on Windows 10+ consoles."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        stdout_handle = kernel32.GetStdHandle(-11)
        stderr_handle = kernel32.GetStdHandle(-12)
        mode = ctypes.c_uint32()
        for handle in (stdout_handle, stderr_handle):
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def should_enable_color(color_mode=None, no_color=False):
    """Decide whether ANSI color should be enabled.

    color_mode: auto, always, never, or None to read OPIP_COLOR.
    """
    mode = (color_mode or os.environ.get("OPIP_COLOR", "auto")).strip().lower()
    if no_color or _env_truthy("OPIP_NO_COLOR") or _env_truthy("NO_COLOR"):
        return False
    if _env_truthy("FORCE_COLOR") or _env_truthy("OPIP_FORCE_COLOR"):
        return True
    if mode == "never":
        return False
    if mode == "always":
        return True

    if _env_truthy("CI") or _env_truthy("GITHUB_ACTIONS"):
        return False
    if _env_truthy("OPIP_NO_INTERACTIVE"):
        return False

    try:
        if not (sys.stdout.isatty() or sys.stderr.isatty()):
            return False
    except Exception:
        return False

    if sys.platform == "win32" and not _windows_color_host_ok():
        return False
    return True


def configure(color_mode=None, no_color=False):
    """Configure color output.

    color_mode: auto, always, never, or None to read from environment.
    """
    global _enabled, _initialized

    _enabled = should_enable_color(color_mode=color_mode, no_color=no_color)
    if _enabled:
        enable_windows_vt()
    _initialized = True


def enabled():
    if not _initialized:
        configure()
    return _enabled


def style(code, text):
    if not enabled():
        return text
    return _CODES.get(code, "") + text + _CODES["reset"]


def bold(text):
    return style("bold", text)


def dim(text):
    return style("dim", text)


def green(text):
    return style("green", text)


def red(text):
    return style("red", text)


def yellow(text):
    return style("yellow", text)


def cyan(text):
    return style("cyan", text)


def blue(text):
    return style("blue", text)


def write_out(text):
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")


def write_err(text):
    sys.stderr.write(text)
    if not text.endswith("\n"):
        sys.stderr.write("\n")


def success(text):
    write_out(green(text))


def error(text):
    write_err(red("Error: ") + text if enabled() else "Error: " + text)


def warn(text):
    write_err(yellow(text))


def info(text):
    write_out(cyan(text))


def heading(text):
    write_out(bold(text))


def bullet(label, desc):
    write_out(f"  {cyan(label)}  {desc}")
