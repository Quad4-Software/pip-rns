"""Tests for local wheel install."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

from pip_rns.local_wheel import (
    install_local_wheel,
    is_wheel_source,
    resolve_wheel_path,
)


def test_is_wheel_source_file():
    with tempfile.TemporaryDirectory() as tmp:
        whl = Path(tmp) / "pkg-1.0-py3-none-any.whl"
        whl.write_bytes(b"x")
        assert is_wheel_source(str(whl)) is True
        assert is_wheel_source(str(Path(tmp))) is True


def test_resolve_wheel_from_directory():
    with tempfile.TemporaryDirectory() as tmp:
        whl = Path(tmp) / "pkg-1.0-py3-none-any.whl"
        whl.write_bytes(b"x")
        assert resolve_wheel_path(tmp) == whl.resolve()


def test_install_local_wheel_unsigned():
    with tempfile.TemporaryDirectory() as tmp:
        whl = Path(tmp) / "pkg-1.0-py3-none-any.whl"
        whl.write_bytes(b"x")
        inst = mock.MagicMock()
        with mock.patch(
            "pip_rns.local_wheel.get_installer",
            return_value=inst,
        ), mock.patch(
            "pip_rns.local_wheel.has_signature",
            return_value=False,
        ):
            install_local_wheel(str(whl), no_interactive=True)
        inst.install.assert_called_once()


def test_install_local_wheel_signed_fail_closed():
    with tempfile.TemporaryDirectory() as tmp:
        whl = Path(tmp) / "pkg-1.0-py3-none-any.whl"
        whl.write_bytes(b"x")
        with mock.patch(
            "pip_rns.local_wheel.has_signature",
            return_value=True,
        ), mock.patch(
            "pip_rns.local_wheel.verify_bundle_signature_info",
            return_value=(["bad sig"], None),
        ):
            try:
                install_local_wheel(str(whl), no_interactive=True)
                raise AssertionError("expected RuntimeError")
            except RuntimeError:
                pass


def test_core_install_dispatches_local_wheel():
    with tempfile.TemporaryDirectory() as tmp:
        whl = Path(tmp) / "pkg.whl"
        whl.write_bytes(b"x")
        with mock.patch(
            "pip_rns.local_wheel.is_wheel_source",
            return_value=True,
        ), mock.patch(
            "pip_rns.local_wheel.install_local_wheel",
        ) as local:
            from pip_rns.core import install

            install(str(whl), no_interactive=True)
        assert local.called
