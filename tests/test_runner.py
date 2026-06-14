"""Minimal test runner - no pytest dependency.

Usage:
    python -m tests.test_runner          # run all
    python -m tests.test_runner -v       # verbose
    python -m tests.test_runner -f test_parse_ref  # filter by name
"""

from __future__ import annotations

import importlib
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tests.support import SkipTest

TESTS_DIR = Path(__file__).parent


def _discover() -> list[tuple[str, str, callable]]:
    tests: list[tuple[str, str, callable]] = []
    for f in sorted(TESTS_DIR.glob("test_*.py")):
        mod = importlib.import_module(f"tests.{f.stem}")
        for name in sorted(dir(mod)):
            if name.startswith("test_"):
                tests.append((f.stem, name, getattr(mod, name)))
    return tests


def main() -> int:
    verbose = "-v" in sys.argv
    filt = None
    if "-f" in sys.argv:
        idx = sys.argv.index("-f")
        if idx + 1 < len(sys.argv):
            filt = sys.argv[idx + 1]

    tests = _discover()
    if filt:
        tests = [t for t in tests if filt in t[1]]

    passed = 0
    skipped = 0
    failed: list[tuple[str, str, str]] = []

    G = "\033[32m"
    Y = "\033[33m"
    R = "\033[31m"
    D = "\033[2m"
    X = "\033[0m"

    print(f"running {len(tests)} test{'s' if len(tests) != 1 else ''}")
    print()

    for module, name, fn in tests:
        label = f"{module}.{name}"
        t0 = time.time()
        try:
            fn()
            dt = time.time() - t0
            print(f"  {G}\u2713{X} {label}  {D}({dt * 1000:.0f}ms){X}")
            passed += 1
        except SkipTest as exc:
            dt = time.time() - t0
            reason = str(exc).strip() or "skipped"
            print(f"  {Y}\u25cb{X} {label}  {D}({dt * 1000:.0f}ms){X}  {D}{reason}{X}")
            skipped += 1
        except Exception:
            dt = time.time() - t0
            tb = traceback.format_exc()
            print(f"  {R}\u2717{X} {label}  {D}({dt * 1000:.0f}ms){X}")
            if verbose:
                for line in tb.rstrip().splitlines():
                    print(f"    {line}")
            failed.append((module, name, tb))

    print()
    total = len(tests)
    green = "\033[32m"
    yellow = "\033[33m"
    red = "\033[31m"
    reset = "\033[0m"
    if failed:
        color = red
        summary = f"{color}{passed}/{total} passed{reset}"
        summary += f"  {red}{len(failed)} failed{reset}"
    else:
        color = green
        summary = f"{color}{passed} passed{reset}"
        if skipped:
            summary += f"  {yellow}{skipped} skipped{reset}"
        if passed + skipped < total:
            summary += f"  {dim}{total} total{reset}"
    print(summary)

    if failed and not verbose:
        print("\n  (rerun with -v for details)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
