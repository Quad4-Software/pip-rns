"""Edge-case tests for opip install wheel selection and venv safety."""

from __future__ import annotations

import os
import tempfile
from unittest import mock

from opip.install import (
    InstallError,
    _select_wheels_for_install,
    _unsupported_wheel_hint,
    _venv_python,
    ensure_venv,
)
from opip.resolver import detect_python_version
from opip.wheel import parse_wheel_filename, wheel_matches_platform


def test_venv_python_path_is_platform_specific():
    path = _venv_python("/tmp/env")
    if os.name == "nt":
        assert path.replace("\\", "/").endswith("Scripts/python.exe")
    else:
        assert path.endswith("bin/python")


def test_ensure_venv_rejects_unreadable_interpreter():
    with tempfile.TemporaryDirectory() as tmp:
        venv = os.path.join(tmp, "broken")
        py = _venv_python(venv)
        os.makedirs(os.path.dirname(py))
        open(py, "w").close()
        with mock.patch("opip.install._interpreter_version", return_value=None):
            with mock.patch(
                "opip.install.detect_python_version",
                return_value="3.14",
            ):
                try:
                    ensure_venv(venv, required_version="3.14", no_interactive=True)
                    raise AssertionError("expected InstallError")
                except InstallError as exc:
                    assert "Could not determine Python version" in str(exc)


def test_select_wheels_rejects_bundle_python_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        wheels = os.path.join(tmp, "wheels")
        os.makedirs(wheels)
        name = "pkg-1.0.0-py3-none-any.whl"
        open(os.path.join(wheels, name), "wb").close()
        manifest = {
            "python_version": "2.7",
            "platform": "manylinux2014_x86_64",
            "wheels": [{"filename": name, "package": "pkg"}],
        }
        try:
            _select_wheels_for_install(manifest, wheels)
            raise AssertionError("expected InstallError")
        except InstallError as exc:
            assert "2.7" in str(exc)
            assert detect_python_version() in str(exc)


def test_select_wheels_filters_incompatible_abi():
    with tempfile.TemporaryDirectory() as tmp:
        wheels = os.path.join(tmp, "wheels")
        os.makedirs(wheels)
        bad = "cffi-1.0.0-cp27-cp27m-manylinux2014_x86_64.whl"
        good = "pkg-1.0.0-py3-none-any.whl"
        open(os.path.join(wheels, bad), "wb").close()
        open(os.path.join(wheels, good), "wb").close()
        py = detect_python_version()
        manifest = {
            "python_version": py,
            "platform": "manylinux2014_x86_64",
            "wheels": [
                {"filename": bad, "package": "cffi"},
                {"filename": good, "package": "pkg"},
            ],
        }
        selected = _select_wheels_for_install(manifest, wheels)
        assert len(selected) == 1
        assert selected[0].endswith(good)


def test_select_wheels_errors_when_nothing_matches():
    with tempfile.TemporaryDirectory() as tmp:
        wheels = os.path.join(tmp, "wheels")
        os.makedirs(wheels)
        bad = "cffi-1.0.0-cp27-cp27m-win_amd64.whl"
        open(os.path.join(wheels, bad), "wb").close()
        py = detect_python_version()
        manifest = {
            "python_version": py,
            "platform": "win_amd64",
            "wheels": [{"filename": bad, "package": "cffi"}],
        }
        try:
            _select_wheels_for_install(manifest, wheels)
            raise AssertionError("expected InstallError")
        except InstallError as exc:
            assert "No wheels in bundle match" in str(exc)
            assert bad in str(exc)


def test_compressed_wheel_tag_parses_and_matches_linux():
    name = (
        "cffi-2.1.1-cp{maj}{min}-cp{maj}{min}-"
        "manylinux2014_x86_64.manylinux_2_17_x86_64.whl"
    )
    maj, min_ = detect_python_version().split(".")
    filename = name.format(maj=maj, min=min_)
    parsed = parse_wheel_filename(filename)
    assert parsed is not None
    assert parsed["pyver"] == f"cp{maj}{min_}"
    assert "manylinux2014_x86_64" in parsed["plat"]
    # Should match a manylinux target for this arch
    assert wheel_matches_platform(
        parsed, detect_python_version(), "manylinux2014_x86_64"
    )


def test_unsupported_wheel_hint_mentions_recreate():
    tip = _unsupported_wheel_hint(
        "ERROR: foo.whl is not a supported wheel on this platform.",
        required_version="3.14",
    )
    assert tip is not None
    assert "3.14" in tip
    assert "rm -rf" in tip
    assert _unsupported_wheel_hint("No matching distribution") is None
