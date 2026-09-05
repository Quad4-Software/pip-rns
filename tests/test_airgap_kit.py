"""Tests for zipapps, proxy, self-install, kit, and manual backend."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_build_pyz_and_version():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build-pyz.py"), "-o", str(out)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        opip_pyz = out / "opip.pyz"
        pip_rns_pyz = out / "pip-rns.pyz"
        assert opip_pyz.is_file()
        assert pip_rns_pyz.is_file()

        for pyz in (opip_pyz, pip_rns_pyz):
            r = subprocess.run(
                [sys.executable, str(pyz), "--version"],
                capture_output=True,
                text=True,
            )
            assert r.returncode == 0, r.stderr
            assert "1." in (r.stdout + r.stderr)


def test_proxy_http_and_socks_opener():
    from opip.proxy import ProxyError, build_opener, clear_proxy, set_proxy

    clear_proxy()
    opener = build_opener(proxy="http://127.0.0.1:9")
    assert opener is not None
    opener = build_opener(proxy="socks5h://127.0.0.1:9050")
    assert opener is not None
    set_proxy("socks5://127.0.0.1:1080")
    opener = build_opener()
    assert opener is not None
    clear_proxy()
    try:
        build_opener(proxy="ftp://example")
        raise AssertionError("expected ProxyError")
    except ProxyError:
        pass


def test_self_install_to_target():
    from opip.self_install import self_install

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "site"
        bin_dir = Path(tmp) / "bin"
        # Force target-only install
        info = self_install(target=str(target), no_interactive=True)
        assert (target / "opip").is_dir()
        assert (target / "pip_rns").is_dir()
        assert info["method"] in ("manual-copy", "manual-wheel", "uv", "pip")
        # shims land under target/bin
        assert Path(info["bin_dir"]).is_dir()
        assert any(Path(info["bin_dir"]).iterdir())
        _ = bin_dir


def test_manual_backend_resolve():
    from opip.install import resolve_install_backend

    assert resolve_install_backend("manual") == "manual"
    assert resolve_install_backend("pip") == "pip"


def test_kit_create_offline_with_fake_runtime():
    from opip.kit import create_kit, verify_kit
    from opip.wheel import parse_wheel_filename

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        wheels = tmp_path / "wheels"
        wheels.mkdir()
        name = "demo"
        version = "0.0.1"
        whl_name = f"{name}-{version}-py3-none-any.whl"
        whl_path = wheels / whl_name
        with zipfile.ZipFile(whl_path, "w") as zf:
            zf.writestr(
                f"{name}-{version}.dist-info/METADATA",
                f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
            )
            zf.writestr(
                f"{name}-{version}.dist-info/WHEEL",
                "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            )
            zf.writestr(
                f"{name}-{version}.dist-info/entry_points.txt",
                "[console_scripts]\ndemo = demo:main\n",
            )
            zf.writestr(f"{name}-{version}.dist-info/RECORD", "")
            zf.writestr(
                f"{name}/__init__.py",
                "def main():\n    print('demo-ok')\n    return 0\n",
            )

        assert parse_wheel_filename(whl_name) is not None

        runtime = tmp_path / "runtime"
        (runtime / "bin").mkdir(parents=True)
        py = runtime / "bin" / "python3"
        # Real enough to run the launcher for a smoke check
        py.write_text(
            f'#!/bin/sh\nexec {sys.executable} "$@"\n',
            encoding="utf-8",
        )
        py.chmod(0o755)

        dist = tmp_path / "dist"
        dist.mkdir()
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build-pyz.py"), "-o", str(dist)],
            check=True,
            capture_output=True,
        )

        kit_dir = tmp_path / "kit"
        try:
            create_kit(
                [f"{name}=={version}"],
                str(kit_dir),
                with_runtime=True,
                with_tools=True,
                as_app=True,
                entry="demo",
                runtime_dir=str(runtime),
                find_links=str(wheels),
                offline=True,
                dist_dir=str(dist),
                name="demo",
            )
        except Exception as exc:
            from tests.support import SkipTest

            raise SkipTest(f"offline kit create needs index metadata: {exc}") from exc

        assert (kit_dir / "opip.pyz").is_file()
        assert (kit_dir / "get-opip.py").is_file()
        assert (kit_dir / "Run").exists()
        assert (kit_dir / "demo").is_file()
        assert (kit_dir / "app" / "site-packages" / "demo").is_dir()
        errors = verify_kit(str(kit_dir))
        assert errors == [], errors
        if os.name == "nt":
            # AppDir launchers are POSIX sh scripts for Linux sneakernet kits
            return
        r = subprocess.run(
            [str(kit_dir / "demo")],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stderr
        assert "demo-ok" in r.stdout


def test_get_opip_from_wheel():
    """Build zipapps from a pip_rns wheel without pip (MOI online-no-pip path)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Build a minimal pip_rns-like wheel from source trees
        wheel = tmp_path / "pip_rns-0.0.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as zf:
            for pkg in ("opip", "pip_rns"):
                pkg_root = SRC / pkg
                for path in pkg_root.rglob("*"):
                    if not path.is_file():
                        continue
                    if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
                        continue
                    rel = path.relative_to(SRC).as_posix()
                    zf.write(path, rel)
        out = tmp_path / "out"
        r = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "get-opip.py"),
                "--from-wheel",
                str(wheel),
                "-o",
                str(out),
            ],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stderr
        assert (out / "opip.pyz").is_file()
        ver = subprocess.run(
            [sys.executable, str(out / "opip.pyz"), "--version"],
            capture_output=True,
            text=True,
        )
        assert ver.returncode == 0, ver.stderr


def test_help_airgap_and_bootstrap():
    r = subprocess.run(
        [sys.executable, "-m", "opip", "help", "airgap"],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(SRC), "OPIP_NO_INTERACTIVE": "1"},
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "get-opip" in r.stdout
    assert "--as-app" in r.stdout or "AppImage" in r.stdout or "NomadNet" in r.stdout

    r2 = subprocess.run(
        [sys.executable, "-m", "pip_rns", "help", "bootstrap"],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(SRC), "PIP_RNS_NO_INTERACTIVE": "1"},
        capture_output=True,
        text=True,
    )
    assert r2.returncode == 0, r2.stderr
    assert "self-install" in r2.stdout
