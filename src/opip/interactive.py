"""Non-interactive / CI detection for prompts and automation."""

import os
import sys


def _env_truthy(name):
    val = os.environ.get(name)
    if val is None:
        return False
    return val.strip().lower() not in ("", "0", "false", "no", "off")


def is_ci():
    """Return True when running under common CI environments."""
    return _env_truthy("CI") or _env_truthy("GITHUB_ACTIONS")


def is_noninteractive(flag=False):
    """
    Return True when prompts must not be shown.

    flag: explicit --no-interactive / --yes from CLI.
    """
    if flag:
        return True
    if is_ci():
        return True
    if _env_truthy("OPIP_NO_INTERACTIVE") or _env_truthy("PIP_RNS_NO_INTERACTIVE"):
        return True
    try:
        if not sys.stdin.isatty():
            return True
    except Exception:
        return True
    return False
