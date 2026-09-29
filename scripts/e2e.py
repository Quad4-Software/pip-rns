#!/usr/bin/env python3
# Copyright (c) 2026, Quad4 (quad4.io)
"""End-to-end smoke test: build artifacts and exercise the real CLIs.

Covers the shapes users actually run:

  1. wheel -> pip install into a fresh venv -> console scripts work
  2. pip-rns install of a local wheel into a second venv
  3. zipapps (opip.pyz, pip-rns.pyz) run with a bare interpreter
  4. self-install --target produces shims and importable packages
  5. opip create --offline --find-links -> verify -> install --target

Runs on Linux, macOS, and Windows. Requires Python 3.10+ and either uv
or the `build` package on PATH/module path. Run from the repo root:

  python scripts/e2e.py [--keep]
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

IS_WIN = os.name == "nt"
BIN = "Scripts" if IS_WIN else "bin"
EXE = ".exe" if IS_WIN else ""


class E2EError(Exception):
    pass


def run(cmd: list[str], *, env: dict | None = None, check=True, cwd=None):
    print(f"$ {' '.join(str(c) for c in cmd)}", flush=True)
    result = subprocess.run(
        [str(c) for c in cmd],
        cwd=cwd or ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise E2EError(
            f"command failed ({result.returncode}): {cmd[0]}\n"
            f"stdout: {result.stdout[-2000:]}\nstderr: {result.stderr[-2000:]}"
        )
    return result


def expect(cond: bool, msg: str) -> None:
    if not cond:
        raise E2EError(msg)
    print(f"  ok: {msg}")


def venv_python(venv: Path) -> Path:
    return venv / BIN / ("python.exe" if IS_WIN else "python")


def venv_cmd(venv: Path, name: str) -> Path:
    return venv / BIN / (name + (".cmd" if IS_WIN else EXE))


def run_cli(venv: Path, name: str, *args: str):
    """Run an installed console script (or .cmd shim on Windows)."""
    script = venv_cmd(venv, name)
    expect(script.is_file(), f"{name} console script exists at {script}")
    if IS_WIN and script.suffix == ".cmd":
        return run(["cmd", "/c", str(script), *args])
    return run([str(script), *args])


def build_artifacts() -> Path:
    if shutil.which("uv"):
        run(["uv", "build"])
    else:
        run([sys.executable, "-m", "build"])
    wheels = sorted(DIST.glob("pip_rns-*.whl"))
    expect(bool(wheels), "wheel was built")
    expect(
        (DIST / "pip_rns-1.5.2.tar.gz").exists() or list(DIST.glob("*.tar.gz")),
        "sdist was built",
    )
    return wheels[-1]


def step_wheel_install(wheel: Path, work: Path) -> Path:
    print("\n== wheel install into fresh venv ==", flush=True)
    venv = work / "venv-wheel"
    run([sys.executable, "-m", "venv", str(venv)])
    run([venv_python(venv), "-m", "pip", "install", str(wheel)])
    for tool in ("pip-rns", "pipx-rns", "opip"):
        out = run_cli(venv, tool, "--version")
        expect(out.returncode == 0, f"{tool} --version exits 0")
    out = run_cli(venv, "pip-rns", "doctor")
    expect("doctor" in out.stdout.lower() or out.returncode == 0, "pip-rns doctor runs")
    return venv


def step_local_wheel_install(wheel: Path, work: Path) -> Path:
    print("\n== pip-rns installs a local wheel into a venv ==", flush=True)
    venv = work / "venv-piprns"
    env = dict(os.environ, PIP_RNS_NO_INTERACTIVE="1")
    run(
        [
            sys.executable,
            DIST / "pip-rns.pyz",
            "install",
            str(wheel),
            "--venv",
            str(venv),
        ],
        env=env,
    )
    py = venv_python(venv)
    out = run(
        [py, "-c", "import pip_rns, opip; print(pip_rns.__name__, opip.__name__)"]
    )
    expect(out.returncode == 0, "pip_rns and opip importable in target venv")
    if sys.platform.startswith("linux"):
        out = run([py, "-c", "import landlockpy, seccompy"])
        expect(out.returncode == 0, "landlockpy/seccompy pulled on Linux")
    return venv


def step_pyz(work: Path) -> None:
    print("\n== zipapps run standalone ==", flush=True)
    run([sys.executable, ROOT / "scripts" / "build-pyz.py", "-o", str(DIST)])
    for name in ("pip-rns", "opip"):
        pyz = DIST / f"{name}.pyz"
        expect(pyz.is_file(), f"{pyz.name} was built")
        out = run([sys.executable, str(pyz), "--version"])
        expect(out.returncode == 0, f"{name}.pyz --version exits 0")


def step_self_install(work: Path) -> None:
    print("\n== self-install --target ==", flush=True)
    target = work / "self"
    env = dict(os.environ, PIP_RNS_NO_INTERACTIVE="1")
    run(
        [sys.executable, DIST / "pip-rns.pyz", "self-install", "--target", str(target)],
        env=env,
    )
    site_pkg = target
    expect((site_pkg / "pip_rns").is_dir(), "pip_rns package copied to target")
    expect((site_pkg / "opip").is_dir(), "opip package copied to target")
    bin_dir = target / BIN
    for tool in ("pip-rns", "opip"):
        shim = bin_dir / (tool + (".cmd" if IS_WIN else ""))
        expect(shim.is_file(), f"{tool} shim written to {bin_dir}")
    # Importable without installing: PYTHONPATH into the target site dir.
    env = dict(os.environ, PYTHONPATH=str(site_pkg))
    out = run([sys.executable, "-c", "import pip_rns, opip; print('ok')"], env=env)
    expect("ok" in out.stdout, "target packages import via PYTHONPATH")


def step_opip_bundle(wheel: Path, work: Path) -> None:
    print("\n== opip bundle roundtrip (offline) ==", flush=True)
    bundle = work / "e2e.opip"
    env = dict(os.environ, PIP_RNS_NO_INTERACTIVE="1")
    run(
        [
            sys.executable,
            DIST / "opip.pyz",
            "create",
            "pip-rns",
            "--find-links",
            str(DIST),
            "--offline",
            "--no-deps",
            "--name",
            "e2e-pip-rns",
            "-o",
            str(bundle),
        ],
        env=env,
    )
    expect(bundle.is_file(), "bundle was created offline")
    out = run([sys.executable, DIST / "opip.pyz", "verify", str(bundle)], env=env)
    expect(out.returncode == 0, "bundle verifies")
    site_dir = work / "bundle-site"
    run(
        [
            sys.executable,
            DIST / "opip.pyz",
            "install",
            str(bundle),
            "--target",
            str(site_dir),
            "--backend",
            "manual",
        ],
        env=env,
    )
    expect((site_dir / "pip_rns").is_dir(), "bundle install extracted pip_rns")


def main() -> int:
    os.environ.setdefault("PYTHONUTF8", "1")
    keep = "--keep" in sys.argv
    work = Path(tempfile.mkdtemp(prefix="pip-rns-e2e-"))
    print(f"workdir: {work}")
    try:
        wheel = build_artifacts()
        step_pyz(work)
        step_wheel_install(wheel, work)
        step_local_wheel_install(wheel, work)
        step_self_install(work)
        step_opip_bundle(wheel, work)
    except E2EError as exc:
        print(f"\nE2E FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)
    print("\nAll e2e steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
