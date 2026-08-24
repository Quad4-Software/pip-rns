"""Guard tests for multi-backend installer command contracts.

Catches argv drift when pip, pipx, uv, or poetry change their CLIs.
Live probes skip when a backend binary is missing.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

from pip_rns.installer import (
    PipInstaller,
    PipxInstaller,
    PoetryInstaller,
    UvInstaller,
    get_installer,
)
from tests.support import SkipTest

PKG = Path("/tmp/example-pkg")


def _ok_run(*_a, **_k):
    return mock.Mock(returncode=0, stdout="", stderr="")


def _patch_run():
    return mock.patch("pip_rns.installer.subprocess.run", side_effect=_ok_run)


def _require(binary: str) -> None:
    if shutil.which(binary) is None:
        raise SkipTest(f"{binary} not on PATH")


def _help_text(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    return (result.stdout or "") + (result.stderr or "")


def test_registry_exposes_all_four_backends():
    for name, cls in (
        ("pip", PipInstaller),
        ("pipx", PipxInstaller),
        ("uv", UvInstaller),
        ("poetry", PoetryInstaller),
    ):
        inst = get_installer(name)
        assert isinstance(inst, cls)
        assert inst.name == name


def test_pip_argv_install_update_uninstall():
    inst = PipInstaller()
    with _patch_run() as run:
        inst.install(PKG)
        assert run.call_args[0][0][:3] == ["pip", "install", str(PKG)]
        run.reset_mock()
        inst.install(PKG, editable=True, extra_args=["--user"])
        assert run.call_args[0][0] == ["pip", "install", "-e", str(PKG), "--user"]
        run.reset_mock()
        inst.update(PKG)
        assert run.call_args[0][0] == ["pip", "install", "--force-reinstall", str(PKG)]
        run.reset_mock()
        inst.uninstall("demo")
        assert run.call_args[0][0] == ["pip", "uninstall", "-y", "demo"]
        run.reset_mock()
        inst.list_packages()
        assert run.call_args[0][0] == ["pip", "list"]


def test_pip_venv_uses_python_m_pip():
    inst = PipInstaller(venv="/opt/venv")
    with _patch_run() as run:
        inst.install(PKG)
    cmd = run.call_args[0][0]
    assert cmd[0].endswith("python") or cmd[0].endswith("python.exe")
    assert cmd[1:3] == ["-m", "pip"]
    assert "install" in cmd


def test_pipx_argv_install_inject_uninstall():
    inst = PipxInstaller()
    with _patch_run() as run:
        inst.install(PKG)
        assert run.call_args[0][0][:3] == ["pipx", "install", str(PKG)]
        run.reset_mock()
        inst.inject("myvenv", PKG, extra_args=["--include-deps"])
        assert run.call_args[0][0] == [
            "pipx",
            "inject",
            "myvenv",
            str(PKG),
            "--include-deps",
        ]
        run.reset_mock()
        inst.uninstall("demo")
        assert run.call_args[0][0] == ["pipx", "uninstall", "demo"]


def test_pipx_update_prefers_runpip():
    inst = PipxInstaller()
    with mock.patch.object(inst, "_pkg_name", return_value="demo"):
        with _patch_run() as run:
            inst.update(PKG)
    assert run.call_args[0][0][:4] == ["pipx", "runpip", "demo", "install"]
    assert "--force-reinstall" in run.call_args[0][0]


def test_uv_argv_install_update_uninstall():
    inst = UvInstaller()
    with _patch_run() as run:
        inst.install(PKG, editable=True)
        assert run.call_args[0][0] == ["uv", "pip", "install", "-e", str(PKG)]
        run.reset_mock()
        inst.update(PKG)
        assert run.call_args[0][0] == [
            "uv",
            "pip",
            "install",
            "--reinstall",
            str(PKG),
        ]
        run.reset_mock()
        inst.uninstall("demo")
        assert run.call_args[0][0] == ["uv", "pip", "uninstall", "demo"]
        run.reset_mock()
        inst.list_packages()
        assert run.call_args[0][0] == ["uv", "pip", "list"]


def test_uv_venv_passes_python():
    inst = UvInstaller(venv="/opt/venv")
    with _patch_run() as run:
        inst.install(PKG)
    cmd = run.call_args[0][0]
    assert cmd[:3] == ["uv", "pip", "install"]
    assert "--python" in cmd
    idx = cmd.index("--python")
    assert cmd[idx + 1].endswith("python") or cmd[idx + 1].endswith("python.exe")


def test_poetry_argv_install_update_uninstall():
    inst = PoetryInstaller()
    with _patch_run() as run:
        inst.install(PKG)
        assert run.call_args[0][0] == ["poetry", "add", str(PKG)]
        run.reset_mock()
        inst.install(PKG, editable=True)
        assert run.call_args[0][0] == ["poetry", "add", "--editable", str(PKG)]
        run.reset_mock()
        inst.update(PKG)
        assert run.call_args[0][0] == ["poetry", "add", "--editable", str(PKG)]
        run.reset_mock()
        inst.uninstall("demo")
        assert run.call_args[0][0] == ["poetry", "remove", "demo"]
        run.reset_mock()
        inst.list_packages()
        assert run.call_args[0][0] == ["poetry", "show"]


def test_inject_unsupported_on_pip_uv_poetry():
    for name in ("pip", "uv", "poetry"):
        try:
            get_installer(name).inject("v", PKG)
            raise AssertionError(f"expected NotImplementedError for {name}")
        except NotImplementedError:
            pass


def test_live_pip_supports_force_reinstall_and_yes():
    _require("pip")
    # Prefer the active interpreter's pip module when present
    text = _help_text([sys.executable, "-m", "pip", "install", "--help"])
    if "No module named pip" in text or "--force-reinstall" not in text:
        pip_bin = shutil.which("pip")
        if pip_bin is None:
            raise SkipTest("pip module/binary not available")
        text = _help_text([pip_bin, "install", "--help"])
    assert "--force-reinstall" in text
    text = _help_text([sys.executable, "-m", "pip", "uninstall", "--help"])
    if "No module named pip" in text or ("-y" not in text and "--yes" not in text):
        pip_bin = shutil.which("pip")
        if pip_bin is None:
            raise SkipTest("pip module/binary not available")
        text = _help_text([pip_bin, "uninstall", "--help"])
    assert "-y" in text or "--yes" in text


def test_live_pipx_supports_install_inject_runpip():
    _require("pipx")
    for sub in ("install", "inject", "runpip", "uninstall", "list"):
        result = subprocess.run(["pipx", sub, "--help"], capture_output=True, text=True)
        assert result.returncode == 0, f"pipx {sub} --help failed"


def test_live_uv_supports_reinstall_and_pip_subcommands():
    _require("uv")
    text = _help_text(["uv", "pip", "install", "--help"])
    assert "--reinstall" in text
    for sub in ("install", "uninstall", "list"):
        result = subprocess.run(
            ["uv", "pip", sub, "--help"], capture_output=True, text=True
        )
        assert result.returncode == 0, f"uv pip {sub} --help failed"


def test_live_poetry_supports_add_remove_show():
    _require("poetry")
    add = _help_text(["poetry", "add", "--help"])
    assert "--editable" in add
    for sub in ("add", "remove", "show"):
        result = subprocess.run(
            ["poetry", sub, "--help"], capture_output=True, text=True
        )
        assert result.returncode == 0, f"poetry {sub} --help failed"


def test_noninteractive_pip_uninstall_still_passes_yes():
    """Regression: pip uninstall must not prompt in CI."""
    with _patch_run() as run:
        PipInstaller().uninstall("pkg")
    assert "-y" in run.call_args[0][0]
