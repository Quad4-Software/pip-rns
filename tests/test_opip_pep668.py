"""Tests for opip PEP 668 recovery during install."""

from __future__ import annotations

import os
import tempfile
from unittest import mock

from opip.install import (
    InstallError,
    _offer_pep668_recovery,
    _run_pip_install_with_recovery,
    _venv_python,
    is_externally_managed_error,
)
from opip.storage import Store

PEP668 = """
error: externally-managed-environment

This environment is externally managed
hint: See PEP 668 for the detailed specification.
"""


def test_detect_externally_managed():
    assert is_externally_managed_error(PEP668)
    assert is_externally_managed_error("PEP 668 blocked install")
    assert not is_externally_managed_error("No matching distribution")


def test_noninteractive_pep668_hints():
    try:
        _offer_pep668_recovery(no_interactive=True)
        raise AssertionError("expected InstallError")
    except InstallError as exc:
        text = str(exc)
        assert "PEP 668" in text
        assert "--venv" in text
        assert "--user" in text
        assert "--target" in text


def test_recovery_prompt_venv(monkeypatch_input=None):
    with tempfile.TemporaryDirectory() as tmp:
        venv_path = os.path.join(tmp, "myenv")
        with mock.patch("opip.interactive.is_noninteractive", return_value=False):
            with mock.patch("builtins.input", side_effect=["1", venv_path]):
                recovered = _offer_pep668_recovery(no_interactive=False)
        assert recovered["venv"] == os.path.abspath(venv_path)
        assert os.path.isfile(_venv_python(recovered["venv"]))


def test_recovery_prompt_user():
    with mock.patch("opip.interactive.is_noninteractive", return_value=False):
        with mock.patch("builtins.input", return_value="2"):
            recovered = _offer_pep668_recovery(no_interactive=False)
    assert recovered == {"user": True, "break_system_packages": True}


def test_user_auto_retries_with_break_system_packages():
    with tempfile.TemporaryDirectory() as tmp:
        wheels = os.path.join(tmp, "wheels")
        os.makedirs(wheels)
        calls = {"n": 0}
        seen_break = []

        def fake_pip(*_a, **kwargs):
            calls["n"] += 1
            seen_break.append(bool(kwargs.get("break_system_packages")))
            if calls["n"] == 1:
                raise InstallError(f"pip install failed:\n{PEP668}")
            return "ok"

        with mock.patch("opip.install._find_pip", return_value=True):
            with mock.patch("opip.install.install_via_pip", side_effect=fake_pip):
                target, user, used_venv, used_pip = _run_pip_install_with_recovery(
                    wheels,
                    os.path.join(tmp, "requirements.txt"),
                    [],
                    user=True,
                    no_interactive=True,
                )
        assert used_pip is True
        assert user is True
        assert used_venv is None
        assert target is None
        assert seen_break == [False, True]
        assert calls["n"] == 2


def test_ensure_venv_rejects_mismatched_python():
    from opip.install import ensure_venv

    with tempfile.TemporaryDirectory() as tmp:
        venv = os.path.join(tmp, "old")
        with mock.patch("opip.install.os.path.isfile", return_value=True):
            with mock.patch("opip.install._interpreter_version", return_value="3.12"):
                with mock.patch(
                    "opip.install.detect_python_version", return_value="3.14"
                ):
                    try:
                        ensure_venv(venv, required_version="3.14", no_interactive=True)
                        raise AssertionError("expected InstallError")
                    except InstallError as exc:
                        assert "3.12" in str(exc)
                        assert "3.14" in str(exc)
                        assert "Recreate" in str(exc)


def test_ensure_venv_recreates_when_confirmed():
    from opip.install import ensure_venv

    with tempfile.TemporaryDirectory() as tmp:
        venv = os.path.join(tmp, "old")
        py = _venv_python(venv)
        os.makedirs(os.path.dirname(py))
        open(py, "w").close()
        versions = iter(["3.12", "3.14"])

        def fake_version(_py):
            return next(versions)

        real_isfile = os.path.isfile

        with mock.patch("opip.install.detect_python_version", return_value="3.14"):
            with mock.patch(
                "opip.install._interpreter_version", side_effect=fake_version
            ):
                with mock.patch("builtins.input", return_value="y"):
                    with mock.patch(
                        "opip.interactive.is_noninteractive", return_value=False
                    ):
                        with mock.patch("opip.install._find_pip", return_value=True):
                            with mock.patch("subprocess.run") as run:
                                states = {"exists": True}

                                def isfile(path):
                                    if path == py or str(path).endswith(
                                        ("python", "python.exe")
                                    ):
                                        return states["exists"]
                                    return real_isfile(path)

                                def fake_run(cmd, **kwargs):
                                    if len(cmd) >= 3 and cmd[1:3] == ["-m", "venv"]:
                                        states["exists"] = True
                                        os.makedirs(os.path.dirname(py), exist_ok=True)
                                        open(py, "w").close()
                                    return mock.Mock(returncode=0)

                                run.side_effect = fake_run
                                with mock.patch(
                                    "opip.install.os.path.isfile", side_effect=isfile
                                ):
                                    with mock.patch(
                                        "opip.install.shutil.rmtree",
                                        side_effect=lambda *_a, **_k: states.update(
                                            exists=False
                                        ),
                                    ):
                                        out = ensure_venv(
                                            venv,
                                            required_version="3.14",
                                            no_interactive=False,
                                        )
        assert out == os.path.abspath(venv)


def test_recovery_prompt_target():
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "vendor")
        with mock.patch("opip.interactive.is_noninteractive", return_value=False):
            with mock.patch("builtins.input", side_effect=["3", target]):
                recovered = _offer_pep668_recovery(no_interactive=False)
        assert recovered["target"] == os.path.abspath(target)


def test_pip_recovery_retries_with_venv():
    with tempfile.TemporaryDirectory() as tmp:
        wheels = os.path.join(tmp, "wheels")
        os.makedirs(wheels)
        venv = os.path.join(tmp, ".venv")
        calls = {"n": 0}

        def fake_pip(*_a, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise InstallError(f"pip install failed:\n{PEP668}")
            return "ok"

        with mock.patch("opip.install._find_pip", return_value=True):
            with mock.patch("opip.install.install_via_pip", side_effect=fake_pip):
                with mock.patch(
                    "opip.install._offer_pep668_recovery",
                    return_value={"venv": venv},
                ):
                    with mock.patch("opip.install.ensure_venv", return_value=venv):
                        with mock.patch(
                            "opip.install._venv_python",
                            return_value="/fake/python",
                        ):
                            with mock.patch(
                                "opip.install.os.path.isfile", return_value=True
                            ):
                                target, user, used_venv, used_pip = (
                                    _run_pip_install_with_recovery(
                                        wheels,
                                        os.path.join(tmp, "requirements.txt"),
                                        [],
                                        no_interactive=False,
                                    )
                                )
        assert used_pip is True
        assert used_venv == venv
        assert user is False
        assert target is None
        assert calls["n"] == 2


def test_install_bundle_noninteractive_pep668():
    from opip.install import install_bundle
    from tests.test_opip import _make_test_bundle

    with tempfile.TemporaryDirectory() as tmp:
        work = os.path.join(tmp, "work")
        os.makedirs(work)
        bundle = os.path.join(tmp, "test.opip")
        _make_test_bundle(work, bundle)
        store = Store(data_dir=os.path.join(tmp, "state"))

        def boom(*_a, **_k):
            raise InstallError(f"pip install failed:\n{PEP668}")

        with mock.patch("opip.install._find_pip", return_value=True):
            with mock.patch("opip.install.install_via_pip", side_effect=boom):
                try:
                    install_bundle(bundle, store=store, no_interactive=True)
                    raise AssertionError("expected InstallError")
                except InstallError as exc:
                    assert "--venv" in str(exc)
