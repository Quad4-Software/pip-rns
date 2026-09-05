# Copyright (c) 2026, Quad4 (quad4.io)
"""Build and verify USB/airgap kits (zipapps, bundles, optional portable Python)."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from opip.bundle import create_bundle
from opip.fetch import download_url
from opip.integrity import file_hash
from opip.proxy import set_proxy
from opip.storage import default_data_dir

KIT_MANIFEST = "kit.json"


class KitError(Exception):
    pass


def _templates_dir() -> Path:
    return Path(__file__).resolve().parent / "kit_templates"


def _registry_path() -> Path:
    return Path(__file__).resolve().parent / "runtime_registry.json"


def load_runtime_registry() -> dict[str, object]:
    """Load pinned python-build-standalone entries from runtime_registry.json."""
    path = _registry_path()
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise KitError(f"Invalid runtime registry: {path}")
    return data


def detect_arch() -> str:
    """Map platform.machine() to a runtime_registry arch key."""
    m = platform.machine().lower()
    if m in ("x86_64", "amd64"):
        return "x86_64"
    if m in ("aarch64", "arm64"):
        return "aarch64"
    raise KitError(f"Unsupported machine architecture for portable runtime: {m}")


def runtime_key(python: str, arch: str, os_name: str = "linux") -> str:
    py = python.strip()
    if py.count(".") >= 2:
        parts = py.split(".")
        py = f"{parts[0]}.{parts[1]}"
    return f"{py}-{arch}-{os_name}"


def _runtime_cache_dir() -> Path:
    return Path(default_data_dir()) / "runtimes"


def _build_pyz_from_installed(dist: Path) -> tuple[Path, Path]:
    """Build zipapps from currently importable opip and pip_rns packages."""
    import zipapp

    import opip
    import pip_rns

    dist.mkdir(parents=True, exist_ok=True)
    work = dist / ".pyz-stage"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    try:
        for name, mod in (("opip", opip), ("pip_rns", pip_rns)):
            mod_file = getattr(mod, "__file__", None)
            if not mod_file:
                raise KitError(f"Cannot locate package files for {name}")
            src = Path(mod_file).resolve().parent
            shutil.copytree(
                src,
                work / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
        opip_pyz = dist / "opip.pyz"
        pip_rns_pyz = dist / "pip-rns.pyz"
        for path in (opip_pyz, pip_rns_pyz):
            if path.exists():
                path.unlink()
        zipapp.create_archive(
            work,
            target=str(opip_pyz),
            interpreter="/usr/bin/env python3",
            main="opip.cli:main",
            compressed=True,
        )
        zipapp.create_archive(
            work,
            target=str(pip_rns_pyz),
            interpreter="/usr/bin/env python3",
            main="pip_rns.cli:main",
            compressed=True,
        )
        return opip_pyz, pip_rns_pyz
    finally:
        shutil.rmtree(work, ignore_errors=True)


def ensure_pyz_artifacts(dist_dir: Path | None = None) -> tuple[Path, Path]:
    """Return (opip.pyz, pip-rns.pyz), building them if missing."""
    candidates: list[Path] = []
    if dist_dir:
        candidates.append(Path(dist_dir))
    # Dev checkout: repo/dist
    maybe_root = Path(__file__).resolve().parents[2]
    if (maybe_root / "scripts" / "build-pyz.py").is_file():
        candidates.append(maybe_root / "dist")
    candidates.append(Path(default_data_dir()) / "pyz")

    for dist in candidates:
        opip_pyz = dist / "opip.pyz"
        pip_rns_pyz = dist / "pip-rns.pyz"
        if opip_pyz.is_file() and pip_rns_pyz.is_file():
            return opip_pyz, pip_rns_pyz

    # Prefer in-repo builder when present
    builder = maybe_root / "scripts" / "build-pyz.py"
    dist = (
        candidates[0]
        if dist_dir
        else (
            maybe_root / "dist"
            if builder.is_file()
            else Path(default_data_dir()) / "pyz"
        )
    )
    if builder.is_file():
        dist.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [sys.executable, str(builder), "-o", str(dist)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise KitError(
                "Failed to build zipapps:\n" + (result.stderr or result.stdout or ""),
            )
        opip_pyz = dist / "opip.pyz"
        pip_rns_pyz = dist / "pip-rns.pyz"
        if opip_pyz.is_file() and pip_rns_pyz.is_file():
            return opip_pyz, pip_rns_pyz

    return _build_pyz_from_installed(Path(default_data_dir()) / "pyz")


def _extract_runtime_tarball(tarball: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball, "r:gz") as tf:
        # install_only archives contain a top-level python/ directory
        members = tf.getmembers()
        for member in members:
            name = member.name
            # Strip leading python/ if present
            parts = Path(name).parts
            if parts and parts[0] == "python":
                member.name = str(Path(*parts[1:])) if len(parts) > 1 else ""
            if not member.name or member.name == ".":
                continue
            tf.extract(member, path=dest)


def fetch_portable_runtime(
    *,
    python: str,
    arch: str,
    runtime_dir: str | None = None,
    runtime_tarball: str | None = None,
    proxy: str | None = None,
) -> Path:
    """Return a directory containing bin/python for the requested runtime."""
    if runtime_dir:
        path = Path(runtime_dir).expanduser().resolve()
        if not path.is_dir():
            raise KitError(f"Runtime directory not found: {path}")
        return path

    key = runtime_key(python, arch)
    reg = load_runtime_registry()
    runtimes = reg.get("runtimes")
    if not isinstance(runtimes, dict):
        raise KitError("runtime registry missing runtimes map")
    entry_obj = runtimes.get(key)
    if not isinstance(entry_obj, dict):
        raise KitError(
            f"No portable runtime pinned for {key}. "
            "Pass --runtime-dir or --runtime-tarball, or update runtime_registry.json.",
        )
    entry = entry_obj

    cache = _runtime_cache_dir() / key
    marker = cache / "bin" / "python3"
    alt = cache / "bin" / "python"
    if marker.is_file() or alt.is_file():
        return cache

    if runtime_tarball:
        tarball = Path(runtime_tarball).expanduser().resolve()
        if not tarball.is_file():
            raise KitError(f"Runtime tarball not found: {tarball}")
    else:
        if proxy:
            set_proxy(proxy)
        cache.parent.mkdir(parents=True, exist_ok=True)
        tarball = cache.parent / f"{key}.tar.gz"
        expected_raw = entry.get("sha256")
        expected = expected_raw if isinstance(expected_raw, str) else None
        url = entry.get("url")
        if not isinstance(url, str) or not url:
            raise KitError(f"Runtime {key} missing url")
        if expected and tarball.is_file() and file_hash(str(tarball)) == expected:
            pass
        else:
            from opip import terminal

            terminal.info(f"Downloading portable CPython ({key})")
            download_url(url, str(tarball), expected_hash=expected)

    if cache.exists():
        shutil.rmtree(cache)
    cache.mkdir(parents=True)
    _extract_runtime_tarball(tarball, cache)
    if not marker.is_file() and not alt.is_file():
        raise KitError(f"Runtime extract missing bin/python under {cache}")
    return cache


def create_kit(
    packages: list[str],
    output_dir: str,
    *,
    python_version: str | None = None,
    platform_tag: str | None = None,
    with_runtime: bool = False,
    with_tools: bool = True,
    runtime_arch: str | None = None,
    runtime_dir: str | None = None,
    runtime_tarball: str | None = None,
    proxy: str | None = None,
    find_links: str | None = None,
    offline: bool = False,
    name: str | None = None,
    require_pypi_hash: bool = False,
    dist_dir: str | None = None,
    as_app: bool = False,
    entry: str | None = None,
) -> Path:
    """Create a sneakernet kit directory ready for USB copy.

    Writes packages/*.opip, optional portable CPython under runtime/,
    zipapps, install.sh, and when as_app is set an AppImage-style launcher.
    """
    from opip import terminal
    from opip.resolver import detect_python_version

    if proxy:
        set_proxy(proxy)

    if as_app and not with_runtime:
        terminal.warn(
            "--as-app without --with-runtime needs python3 on the offline host",
        )

    out = Path(output_dir).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        raise KitError(f"Output directory is not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    packages_dir = out / "packages"
    packages_dir.mkdir()

    py = python_version or detect_python_version()
    bundle_name = name or (
        packages[0].split("==")[0].split("[")[0] if packages else "kit"
    )
    bundle_path = packages_dir / f"{bundle_name}.opip"

    terminal.info(f"Building bundle {bundle_path.name}")
    create_bundle(
        str(bundle_path),
        packages,
        name=bundle_name,
        py_version=py,
        platform_tag=platform_tag,
        find_links=find_links,
        offline=offline,
        require_pypi_hash=require_pypi_hash,
    )

    if with_tools:
        terminal.info("Adding opip.pyz and pip-rns.pyz")
        opip_pyz, pip_rns_pyz = ensure_pyz_artifacts(
            Path(dist_dir) if dist_dir else None,
        )
        shutil.copy2(opip_pyz, out / "opip.pyz")
        shutil.copy2(pip_rns_pyz, out / "pip-rns.pyz")
        for src in (opip_pyz, pip_rns_pyz):
            rsg = Path(str(src) + ".rsg")
            if rsg.is_file():
                shutil.copy2(rsg, out / rsg.name)

    # Standalone bootstrap helper for the next machine (no prior opip)
    get_opip = Path(__file__).resolve().parent / "kit_templates" / "get-opip.py"
    if not get_opip.is_file():
        get_opip = Path(__file__).resolve().parents[2] / "scripts" / "get-opip.py"
    if get_opip.is_file():
        shutil.copy2(get_opip, out / "get-opip.py")

    runtime_meta = None
    if with_runtime:
        arch = runtime_arch or detect_arch()
        terminal.info(f"Adding portable runtime ({py}/{arch})")
        runtime_src = fetch_portable_runtime(
            python=py,
            arch=arch,
            runtime_dir=runtime_dir,
            runtime_tarball=runtime_tarball,
            proxy=proxy,
        )
        runtime_dest = out / "runtime"
        if runtime_dest.exists():
            shutil.rmtree(runtime_dest)
        shutil.copytree(runtime_src, runtime_dest, symlinks=True)
        runtime_meta = {"python": py, "arch": arch, "path": "runtime"}

    app_meta = None
    if as_app:
        from opip.appdir import build_appdir

        terminal.info("Building AppImage-style launcher (--as-app)")
        try:
            app_meta = build_appdir(
                bundle_path,
                out,
                entry=entry,
                app_name=bundle_name,
            )
        except Exception as exc:
            raise KitError(f"Failed to build app launcher: {exc}") from exc
        launcher_name = app_meta.get("launcher")
        if not isinstance(launcher_name, str):
            launcher_name = bundle_name
        terminal.info(f"Launcher: ./{launcher_name}  (or ./Run)")

    templates = _templates_dir()
    shutil.copy2(templates / "install.sh", out / "install.sh")
    os.chmod(out / "install.sh", 0o755)
    readme_src = templates / "README.txt"
    readme = readme_src.read_text(encoding="utf-8")
    if as_app and app_meta:
        launcher_name = app_meta.get("launcher")
        if not isinstance(launcher_name, str):
            launcher_name = bundle_name
        readme = (
            f"AppImage-style run (no install step):\n  ./{launcher_name}\n  ./Run\n\n"
        ) + readme
    (out / "README.txt").write_text(readme, encoding="utf-8")

    manifest = {
        "format": "opip-kit/1",
        "bundle": f"packages/{bundle_path.name}",
        "packages": packages,
        "python": py,
        "platform": platform_tag,
        "with_tools": with_tools,
        "runtime": runtime_meta,
        "as_app": app_meta,
    }
    (out / KIT_MANIFEST).write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    # Digest file for kit verify (after all files exist)
    digests = {}
    for path in sorted(out.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "SHA256SUMS":
            continue
        rel = path.relative_to(out).as_posix()
        digests[rel] = file_hash(str(path))
    lines = [f"{digest}  {rel}" for rel, digest in sorted(digests.items())]
    (out / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")

    terminal.success(f"Kit ready: {out}")
    if as_app and app_meta:
        launcher = app_meta.get("launcher")
        if isinstance(launcher, str):
            terminal.success(f"Offline run: {out / launcher}")
    return out


def verify_kit(kit_dir: str, *, require_signature: bool = False) -> list[str]:
    """Verify kit SHA256SUMS and optional .rsg sidecars. Returns error list."""
    root = Path(kit_dir).expanduser().resolve()
    errors: list[str] = []
    sums = root / "SHA256SUMS"
    if not sums.is_file():
        return [f"Missing {sums.name}"]

    for line in sums.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            errors.append(f"Bad SHA256SUMS line: {line}")
            continue
        expected, rel = parts[0], parts[1].lstrip("*").strip()
        if rel == "SHA256SUMS":
            continue
        path = root / rel
        if not path.is_file():
            errors.append(f"Missing file: {rel}")
            continue
        actual = file_hash(str(path))
        if actual != expected:
            errors.append(f"Hash mismatch: {rel}")

    if require_signature:
        from opip.signing import has_signature, verify_bundle_signature

        for bundle in (root / "packages").glob("*.opip"):
            if not has_signature(str(bundle)):
                errors.append(f"Unsigned bundle: {bundle.name}")
            else:
                errors.extend(verify_bundle_signature(str(bundle)))

    return errors
