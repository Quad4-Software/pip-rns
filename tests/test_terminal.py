"""Color decision matrix tests for opip and pip_rns."""

from __future__ import annotations

import os
from unittest import mock

from opip import terminal as opip_terminal
from pip_rns import ui as pip_ui


def _clear_color_env():
    for key in (
        "NO_COLOR",
        "FORCE_COLOR",
        "OPIP_COLOR",
        "OPIP_NO_COLOR",
        "OPIP_FORCE_COLOR",
        "OPIP_NO_INTERACTIVE",
        "PIP_RNS_COLOR",
        "PIP_RNS_NO_INTERACTIVE",
        "CI",
        "GITHUB_ACTIONS",
        "WT_SESSION",
        "ANSICON",
        "ConEmuANSI",
        "TERM",
    ):
        os.environ.pop(key, None)


def test_opip_color_off_with_no_color():
    _clear_color_env()
    os.environ["NO_COLOR"] = "1"
    assert opip_terminal.should_enable_color() is False


def test_opip_color_on_with_force_color():
    _clear_color_env()
    os.environ["FORCE_COLOR"] = "1"
    assert opip_terminal.should_enable_color() is True


def test_opip_color_off_in_ci():
    _clear_color_env()
    os.environ["CI"] = "true"
    with mock.patch("opip.terminal.sys.stdout") as stdout:
        stdout.isatty.return_value = True
        with mock.patch("opip.terminal.sys.stderr") as stderr:
            stderr.isatty.return_value = True
            assert opip_terminal.should_enable_color() is False


def test_opip_color_off_non_tty():
    _clear_color_env()
    with mock.patch("opip.terminal.sys.stdout") as stdout:
        stdout.isatty.return_value = False
        with mock.patch("opip.terminal.sys.stderr") as stderr:
            stderr.isatty.return_value = False
            assert opip_terminal.should_enable_color() is False


def test_opip_color_off_win32_classic():
    _clear_color_env()
    with mock.patch("opip.terminal.sys.platform", "win32"):
        with mock.patch("opip.terminal.sys.stdout") as stdout:
            stdout.isatty.return_value = True
            with mock.patch("opip.terminal.sys.stderr") as stderr:
                stderr.isatty.return_value = True
                assert opip_terminal.should_enable_color() is False


def test_opip_color_on_win32_windows_terminal():
    _clear_color_env()
    os.environ["WT_SESSION"] = "abc"
    with mock.patch("opip.terminal.sys.platform", "win32"):
        with mock.patch("opip.terminal.sys.stdout") as stdout:
            stdout.isatty.return_value = True
            with mock.patch("opip.terminal.sys.stderr") as stderr:
                stderr.isatty.return_value = False
                assert opip_terminal.should_enable_color() is True


def test_pip_rns_color_off_ci():
    _clear_color_env()
    os.environ["CI"] = "1"
    with mock.patch("pip_rns.ui.sys.stdout") as stdout:
        stdout.isatty.return_value = True
        assert pip_ui.should_enable_color() is False


def test_pip_rns_color_never_mode():
    _clear_color_env()
    os.environ["PIP_RNS_COLOR"] = "never"
    with mock.patch("pip_rns.ui.sys.stdout") as stdout:
        stdout.isatty.return_value = True
        assert pip_ui.should_enable_color() is False
