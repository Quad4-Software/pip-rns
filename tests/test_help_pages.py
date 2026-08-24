"""Tests for pip-rns help pages."""

from __future__ import annotations

import argparse
from unittest import mock

from pip_rns.help_pages import interactive_help, show_main_help


def test_show_main_help():
    show_main_help()


def test_interactive_help_quits():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("install")
    with mock.patch(
        "pip_rns.help_pages.is_noninteractive",
        return_value=False,
    ), mock.patch(
        "builtins.input",
        return_value="q",
    ):
        code = interactive_help(parser)
    assert code == 0


def test_interactive_help_noninteractive():
    parser = argparse.ArgumentParser()
    with mock.patch(
        "pip_rns.help_pages.is_noninteractive",
        return_value=True,
    ):
        code = interactive_help(parser, no_interactive=True)
    assert code == 0
