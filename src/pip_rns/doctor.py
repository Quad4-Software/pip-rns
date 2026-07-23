"""Environment health checks for pip-rns."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass

from .ui import dim, green, yellow


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    level: str = "fail"  # fail | warn | pass


def _which(name: str) -> str | None:
    return shutil.which(name)


def run_doctor(
    *,
    online: bool = False,
    online_remote: str | None = None,
    config_dir: str | None = None,
) -> list[Check]:
    """Collect doctor checks. offline by default."""
    from opip.interactive import is_ci, is_noninteractive

    from . import ui as pip_ui
    from .venv_prefs import VenvPrefs

    checks: list[Check] = []

    for tool in ("rngit", "rnid", "git"):
        path = _which(tool)
        if path:
            checks.append(Check(tool, True, path, "pass"))
        else:
            level = "fail" if tool in ("rngit", "git") else "warn"
            hint = (
                "Install via: pip install rns"
                if tool in ("rngit", "rnid")
                else "Install git"
            )
            checks.append(Check(tool, False, f"not on PATH ({hint})", level))

    for backend in ("pip", "pipx", "uv", "poetry"):
        path = _which(backend)
        if backend == "pip":
            import subprocess

            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "--version"],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                checks.append(Check("pip", True, f"{sys.executable} -m pip", "pass"))
            except Exception:
                checks.append(Check("pip", False, "python -m pip unavailable", "fail"))
        elif path:
            checks.append(Check(backend, True, path, "pass"))
        else:
            checks.append(Check(backend, True, "not installed (optional)", "warn"))

    cfg = config_dir or os.environ.get("PIP_RNS_CONFIG")
    prefs = VenvPrefs(cfg)
    checks.append(
        Check(
            "venv-prefs",
            True,
            str(prefs._path),
            "pass",
        )
    )

    from .indexes import IndexManager, _config_dir

    try:
        idx = IndexManager()
        n = len(idx.list())
        checks.append(
            Check(
                "indexes",
                True,
                f"{n} registered ({_config_dir()})",
                "pass" if n else "warn",
            )
        )
    except Exception as exc:
        checks.append(Check("indexes", False, str(exc), "warn"))

    color_on = pip_ui.should_enable_color()
    checks.append(
        Check(
            "color",
            True,
            "enabled" if color_on else "disabled (NO_COLOR/CI/non-TTY/classic Windows)",
            "pass",
        )
    )
    ni = is_noninteractive()
    checks.append(
        Check(
            "interactive",
            True,
            "non-interactive" if ni else ("CI" if is_ci() else "interactive"),
            "pass",
        )
    )

    if online:
        if not online_remote:
            checks.append(
                Check(
                    "online",
                    False,
                    "pass --remote RNS_URL with --online (no default remote)",
                    "fail",
                )
            )
        else:
            try:
                from .releases import list_releases

                releases = list_releases(online_remote)
                checks.append(
                    Check(
                        "online",
                        True,
                        f"{len(releases)} releases from {online_remote}",
                        "pass",
                    )
                )
            except Exception as exc:
                checks.append(Check("online", False, str(exc)[:200], "fail"))

    return checks


def print_doctor(checks: list[Check]) -> int:
    """Print checks. Return 1 if any fail-level failure."""
    failed = 0
    for c in checks:
        if c.ok and c.level == "pass":
            mark = green("ok")
        elif c.level == "warn":
            mark = yellow("warn")
        else:
            mark = yellow("FAIL") if not c.ok else green("ok")
            if not c.ok and c.level == "fail":
                failed += 1
        print(f"  [{mark}] {c.name}: {dim(c.detail)}")
    return 1 if failed else 0
