"""Tests for installer failure classification and recovery hints."""

from __future__ import annotations

from unittest import mock

from pip_rns.installer import (
    InstallerError,
    PipInstaller,
    classify_install_failure,
    format_installer_error,
    run_installer_cmd,
)

PEP668 = """
error: externally-managed-environment

× This environment is externally managed
╰─> To install Python packages system-wide, try 'pacman -S
    python-xyz'...
hint: See PEP 668 for the detailed specification.
"""


def test_classify_externally_managed():
    err = classify_install_failure(["pip", "install", "x.whl"], 1, PEP668)
    assert err.kind == "externally_managed"
    assert "PEP 668" in str(err)
    text = format_installer_error(err)
    assert "--venv" in text
    assert "--pipx" in text


def test_classify_permission():
    err = classify_install_failure(
        ["pip", "install", "x"], 1, "ERROR: Permission denied: /usr/lib"
    )
    assert err.kind == "permission"
    assert any("venv" in h for h in err.hints)


def test_classify_missing_pip():
    err = classify_install_failure(
        ["python", "-m", "pip", "install", "x"],
        1,
        "No module named pip",
    )
    assert err.kind == "missing_pip"


def test_classify_disk_full():
    err = classify_install_failure(
        ["pip", "install", "x"], 1, "No space left on device"
    )
    assert err.kind == "disk_full"


def test_classify_not_found():
    err = classify_install_failure(
        ["pip", "install", "x"],
        1,
        "ERROR: Could not find a version that satisfies the requirement x",
    )
    assert err.kind == "not_found"


def test_run_installer_cmd_raises_classified_error():
    fake = mock.Mock(returncode=1, stdout="", stderr=PEP668)
    with mock.patch("pip_rns.installer.subprocess.run", return_value=fake):
        try:
            run_installer_cmd(["pip", "install", "x.whl"])
            raise AssertionError("expected InstallerError")
        except InstallerError as exc:
            assert exc.kind == "externally_managed"


def test_run_installer_cmd_missing_binary():
    with mock.patch(
        "pip_rns.installer.subprocess.run",
        side_effect=FileNotFoundError("pip"),
    ):
        try:
            run_installer_cmd(["pip", "install", "x.whl"])
            raise AssertionError("expected InstallerError")
        except InstallerError as exc:
            assert exc.kind == "missing_command"


def test_pip_install_uses_run_installer_cmd():
    inst = PipInstaller()
    with mock.patch("pip_rns.installer.run_installer_cmd") as run:
        from pathlib import Path

        inst.install(Path("/tmp/pkg.whl"))
    assert run.called
    assert run.call_args[0][0][:2] == ["pip", "install"]


def test_offer_managed_env_recovery_noninteractive():
    from pip_rns.core import _offer_managed_env_recovery

    assert (
        _offer_managed_env_recovery(
            installer="pip",
            venv=None,
            no_interactive=True,
        )
        is None
    )


def test_install_package_retries_with_venv():
    from pathlib import Path

    from pip_rns import core
    from pip_rns.installer import PipInstaller

    pkg = Path("/tmp/pkg.whl")
    first = mock.Mock(spec=PipInstaller)
    first.install.side_effect = InstallerError(
        "managed",
        kind="externally_managed",
    )
    retry = mock.Mock(spec=PipInstaller)

    with mock.patch.object(
        core,
        "_offer_managed_env_recovery",
        return_value=("pip", "/tmp/venv"),
    ), mock.patch.object(core, "get_installer", return_value=retry):
        inst, venv = core._install_package(
            first,
            pkg,
            installer_name="pip",
            venv=None,
            no_interactive=False,
        )
    assert venv == "/tmp/venv"
    assert retry.install.called


def test_install_package_switches_to_uv_when_venv_lacks_pip():
    from pathlib import Path

    from pip_rns import core
    from pip_rns.installer import PipInstaller

    pkg = Path("/tmp/pkg.whl")
    first = mock.Mock(spec=PipInstaller)
    first.install.side_effect = InstallerError("no pip", kind="missing_pip")
    retry = mock.Mock()

    with mock.patch.object(
        core,
        "_offer_managed_env_recovery",
        return_value=("uv", "/tmp/venv"),
    ) as offer, mock.patch.object(core, "get_installer", return_value=retry):
        _inst, venv = core._install_package(
            first,
            pkg,
            installer_name="pip",
            venv="/tmp/venv",
            no_interactive=True,
        )
    assert offer.called
    assert venv == "/tmp/venv"
    assert retry.install.called


def test_installer_for_venv_falls_back_to_uv():
    from pip_rns import core

    with mock.patch.object(core, "_venv_has_pip", return_value=False):
        with mock.patch.object(core, "_bootstrap_pip", return_value=False):
            with mock.patch("shutil.which", return_value="/usr/bin/uv"):
                assert core._installer_for_venv("/tmp/venv") == "uv"
