"""Terminal colors and styling (stdlib only, Linux/macOS/Windows)."""

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


def _env_truthy(name):
    val = os.environ.get(name)
    if val is None:
        return False
    return val.strip().lower() not in ("", "0", "false", "no", "off")


def _env_falsy(name):
    val = os.environ.get(name)
    if val is None:
        return False
    return val.strip().lower() in ("", "0", "false", "no", "off")


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


def configure(color_mode=None, no_color=False):
    """
    Configure color output.

    color_mode: auto, always, never, or None to read from environment.
    """
    global _enabled, _initialized

    mode = (color_mode or os.environ.get("OPIP_COLOR", "auto")).strip().lower()
    if no_color or _env_truthy("OPIP_NO_COLOR") or _env_truthy("NO_COLOR"):
        mode = "never"
    if _env_truthy("FORCE_COLOR") or _env_truthy("OPIP_FORCE_COLOR"):
        mode = "always"

    if mode == "never":
        _enabled = False
    elif mode == "always":
        _enabled = True
    else:
        _enabled = sys.stdout.isatty() or sys.stderr.isatty()

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
    write_out("  {0}  {1}".format(cyan(label), desc))
