# Copyright (c) 2026, Quad4 (quad4.io)
"""Build relocatable AppDir-style launchers for kit payloads (AppImage-like UX)."""

from __future__ import annotations

import configparser
import os
import shutil
import zipfile
from pathlib import Path

from opip.bundle import extract_bundle
from opip.install import _select_wheels_for_install, install_wheel_manual


class AppDirError(Exception):
    pass


def read_console_scripts(wheel_path: str | Path) -> list[tuple[str, str, str]]:
    """Return (name, module, attr) from a wheel's entry_points.txt."""
    scripts: list[tuple[str, str, str]] = []
    with zipfile.ZipFile(wheel_path, "r") as zf:
        ep_name = None
        for name in zf.namelist():
            if name.endswith(".dist-info/entry_points.txt"):
                ep_name = name
                break
        if not ep_name:
            return scripts
        raw = zf.read(ep_name).decode("utf-8", errors="replace")
    parser = configparser.ConfigParser()
    # entry_points.txt uses [console_scripts] without interpolation issues
    try:
        parser.read_string(raw)
    except configparser.Error:
        # Fallback line parse
        in_cs = False
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                in_cs = line.lower() == "[console_scripts]"
                continue
            if in_cs and line and not line.startswith("#") and "=" in line:
                left, right = line.split("=", 1)
                target = right.strip()
                if ":" in target:
                    mod, attr = target.split(":", 1)
                    scripts.append((left.strip(), mod.strip(), attr.strip()))
        return scripts
    if parser.has_section("console_scripts"):
        for name, target in parser.items("console_scripts"):
            target = target.strip()
            if ":" not in target:
                continue
            mod, attr = target.split(":", 1)
            scripts.append((name.strip(), mod.strip(), attr.strip()))
    return scripts


def _safe_launcher_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in name)
    return cleaned.strip("-") or "App"


def _shell_launcher(
    *,
    here_expr: str,
    mod: str,
    attr: str,
    missing: str,
    header: str = "",
) -> str:
    """Build a POSIX shell launcher that prefers kit runtime Python."""
    return (
        "#!/bin/sh\n"
        f"{header}"
        f"HERE={here_expr}\n"
        'APP="$HERE/app/site-packages"\n'
        'if [ -x "$HERE/runtime/bin/python3" ]; then\n'
        '  PY="$HERE/runtime/bin/python3"\n'
        'elif [ -x "$HERE/runtime/bin/python" ]; then\n'
        '  PY="$HERE/runtime/bin/python"\n'
        "elif command -v python3 >/dev/null 2>&1; then\n"
        "  PY=$(command -v python3)\n"
        "else\n"
        f'  echo "error: no Python; {missing}" >&2\n'
        "  exit 1\n"
        "fi\n"
        'export PYTHONPATH="$APP${PYTHONPATH:+:$PYTHONPATH}"\n'
        f'exec "$PY" -c \'import sys; from {mod} import {attr}; '
        f'sys.exit({attr}())\' "$@"\n'
    )


def build_appdir(
    bundle_path: str | Path,
    kit_dir: str | Path,
    *,
    entry: str | None = None,
    app_name: str | None = None,
) -> dict[str, object]:
    """Extract matching wheels into kit/app and write a top-level launcher.

    Uses the bundle's declared Python/platform tags so host Python need not
    match. Returns metadata including launcher name and console scripts.
    """
    kit = Path(kit_dir)
    app_root = kit / "app"
    site = app_root / "site-packages"
    bin_dir = app_root / "bin"
    if app_root.exists():
        shutil.rmtree(app_root)
    site.mkdir(parents=True)
    bin_dir.mkdir(parents=True)

    ctx = extract_bundle(str(bundle_path))
    try:
        manifest = ctx["manifest"]
        wheels_dir = Path(ctx["dest_dir"]) / "wheels"
        target_py = manifest.get("python_version")
        target_plat = manifest.get("platform") or "any"
        wheel_paths = _select_wheels_for_install(
            manifest,
            str(wheels_dir),
            py_version=target_py,
            platform_tag=target_plat,
            require_host_match=False,
        )
        all_scripts: list[tuple[str, str, str]] = []
        for whl in wheel_paths:
            install_wheel_manual(whl, str(site))
            all_scripts.extend(read_console_scripts(whl))
    finally:
        shutil.rmtree(ctx["dest_dir"], ignore_errors=True)

    # Deduplicate by script name (last wins)
    by_name = {name: (mod, attr) for name, mod, attr in all_scripts}

    preferred = entry
    if not preferred:
        # Prefer script matching bundle name
        bname = (manifest.get("name") or app_name or "app").lower().replace("_", "-")
        if bname in by_name:
            preferred = bname
        elif by_name:
            preferred = sorted(by_name.keys())[0]
        else:
            preferred = bname

    if preferred not in by_name:
        # Synthesize import of package.__main__ or package name
        pkg = preferred.replace("-", "_")
        by_name[preferred] = (pkg, "main")

    written_bins = []
    for name, (mod, attr) in sorted(by_name.items()):
        path = bin_dir / name
        path.write_text(
            _shell_launcher(
                here_expr='$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)',
                mod=mod,
                attr=attr,
                missing="rebuild kit with --with-runtime",
            ),
            encoding="utf-8",
        )
        os.chmod(path, 0o755)
        written_bins.append(name)

    display = _safe_launcher_name(app_name or preferred)
    top = kit / display
    # Top-level launcher mirrors AppImage double-click UX
    mod, attr = by_name[preferred]
    top.write_text(
        _shell_launcher(
            here_expr='$(CDPATH= cd -- "$(dirname "$0")" && pwd)',
            mod=mod,
            attr=attr,
            missing="this kit needs --with-runtime",
            header="# AppImage-style launcher generated by opip kit --as-app\n",
        ),
        encoding="utf-8",
    )
    os.chmod(top, 0o755)

    # Convenience symlink/copy as Run
    run = kit / "Run"
    if run.exists() or run.is_symlink():
        run.unlink()
    try:
        run.symlink_to(display)
    except OSError:
        shutil.copy2(top, run)
        os.chmod(run, 0o755)

    return {
        "launcher": display,
        "entry": preferred,
        "scripts": written_bins,
        "module": mod,
        "attr": attr,
    }
