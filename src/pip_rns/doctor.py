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
    fix: str | None = None


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
            checks.append(
                Check(
                    tool,
                    False,
                    f"not on PATH ({hint})",
                    level,
                    fix="pip install rns"
                    if tool in ("rngit", "rnid")
                    else "install git",
                )
            )

    for backend in ("pip", "pipx", "uv", "poetry"):
        path = _which(backend)
        if backend == "pip":
            import subprocess

            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "--version"],
                    check=True,
                    capture_output=True,
                )
                checks.append(Check("pip", True, f"{sys.executable} -m pip", "pass"))
            except Exception:
                checks.append(
                    Check(
                        "pip",
                        False,
                        "python -m pip unavailable",
                        "fail",
                        fix="python -m venv .venv && source .venv/bin/activate",
                    )
                )
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
                f"{n} registered ({_config_dir()}) (opt-in only)",
                "pass" if n else "warn",
                fix=None if n else "pip-rns index add rns://identity/group/index",
            )
        )
    except Exception as exc:
        checks.append(Check("indexes", False, str(exc), "warn"))

    from .trust import TrustStore

    trust = TrustStore(cfg)
    trusted = trust.list_all()
    if trusted:
        detail = (
            f"{len(trusted)} entr{'y' if len(trusted) == 1 else 'ies'} ({trust.path})"
        )
        checks.append(Check("trust", True, detail, "pass"))
    else:
        checks.append(
            Check(
                "trust",
                True,
                f"empty ({trust.path}). use pip-rns trust add",
                "warn",
                fix="pip-rns trust add rns://id/group/repo IDENTITY",
            )
        )

    from .resolver import CACHE_DIR, PERSISTENT_DIR

    cache_n = 0
    if CACHE_DIR.is_dir():
        cache_n = sum(1 for p in CACHE_DIR.iterdir() if p.is_dir())
    checks.append(
        Check(
            "source-cache",
            True,
            f"{cache_n} clone(s) under {CACHE_DIR}",
            "pass" if cache_n else "warn",
        )
    )
    edit_n = 0
    if PERSISTENT_DIR.is_dir():
        edit_n = sum(1 for p in PERSISTENT_DIR.iterdir() if p.is_dir())
    checks.append(
        Check(
            "editable-checkouts",
            True,
            f"{edit_n} under {PERSISTENT_DIR}",
            "pass",
        )
    )

    from .discover import DiscoverStore

    discovered = DiscoverStore(cfg)
    dnodes = discovered.list_nodes()
    checks.append(
        Check(
            "discover",
            True,
            (
                f"{len(dnodes)} node(s) ({discovered.path})"
                if dnodes
                else f"empty ({discovered.path}). pip-rns discover --save"
            ),
            "pass" if dnodes else "warn",
            fix=None if dnodes else "pip-rns browse",
        )
    )

    try:
        import RNS  # noqa: F401

        checks.append(
            Check("rns-python", True, "import RNS ok (needed for discover)", "pass")
        )
    except ImportError:
        checks.append(
            Check(
                "rns-python",
                False,
                "RNS not importable. pip install rns (needed for discover)",
                "warn",
                fix="pip install rns",
            )
        )

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


def print_doctor(checks: list[Check], *, show_fix: bool = False) -> int:
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
        if show_fix and c.fix and (not c.ok or c.level == "warn"):
            print(f"       fix: {dim(c.fix)}")
    return 1 if failed else 0
