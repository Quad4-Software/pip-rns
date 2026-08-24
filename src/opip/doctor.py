"""Environment health checks for opip."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass

from opip import terminal
from opip.interactive import is_ci, is_noninteractive
from opip.storage import Store, default_data_dir


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    level: str = "fail"


def run_doctor(*, data_dir: str | None = None) -> list[Check]:
    checks: list[Check] = []

    rnid = shutil.which("rnid")
    if rnid:
        checks.append(Check("rnid", True, rnid, "pass"))
    else:
        checks.append(
            Check(
                "rnid",
                False,
                "not on PATH (pip install rns). needed to sign/verify",
                "warn",
            )
        )

    base = data_dir or default_data_dir()
    try:
        os.makedirs(base, exist_ok=True)
        probe = os.path.join(base, ".doctor-write")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
        checks.append(Check("data-dir", True, base, "pass"))
    except Exception as exc:
        checks.append(Check("data-dir", False, str(exc), "fail"))

    try:
        store = Store(data_dir=base)
        n = len(store.list_preferred_targets())
        checks.append(Check("dest-prefs", True, f"{n} remembered destinations", "pass"))
    except Exception as exc:
        checks.append(Check("dest-prefs", False, str(exc), "warn"))

    color_on = terminal.should_enable_color()
    checks.append(
        Check(
            "color",
            True,
            "enabled" if color_on else "disabled",
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

    try:
        import subprocess

        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            check=True,
            capture_output=True,
        )
        checks.append(Check("pip", True, f"{sys.executable} -m pip", "pass"))
    except Exception:
        checks.append(Check("pip", False, "python -m pip unavailable", "warn"))

    return checks


def print_doctor(checks: list[Check]) -> int:
    failed = 0
    for c in checks:
        if c.ok and c.level == "pass":
            mark = terminal.green("ok")
        elif c.level == "warn":
            mark = terminal.yellow("warn")
        else:
            mark = terminal.red("FAIL")
            if not c.ok:
                failed += 1
        terminal.write_out(f"  [{mark}] {c.name}: {terminal.dim(c.detail)}")
    return 1 if failed else 0
