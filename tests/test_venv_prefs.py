"""Remembered venv preference tests."""

from __future__ import annotations

import tempfile
from unittest import mock

from pip_rns.venv_prefs import VenvPrefs, maybe_remember_venv


def test_venv_prefs_set_get_forget():
    with tempfile.TemporaryDirectory() as tmp:
        prefs = VenvPrefs(tmp)
        prefs.set_remote("rns://id/g/repo", tmp + "/venv")
        assert prefs.get_remote("rns://id/g/repo").endswith("venv")
        assert prefs.forget_remote("rns://id/g/repo") is True
        assert prefs.get_remote("rns://id/g/repo") is None


def test_venv_resolve_order():
    with tempfile.TemporaryDirectory() as tmp:
        prefs = VenvPrefs(tmp)
        prefs.set_default(tmp + "/default")
        prefs.set_remote("rns://id/g/repo", tmp + "/remote")
        assert prefs.resolve("rns://id/g/repo", tmp + "/cli").endswith("cli")
        assert prefs.resolve("rns://id/g/repo", None).endswith("remote")
        assert prefs.resolve("rns://other/g/x", None).endswith("default")


def test_maybe_remember_no_prompt_noninteractive():
    with tempfile.TemporaryDirectory() as tmp:
        prefs = VenvPrefs(tmp)
        with mock.patch("builtins.input", side_effect=AssertionError("prompted")):
            maybe_remember_venv(
                prefs,
                "rns://id/g/repo",
                tmp + "/venv",
                venv_explicit=True,
                no_interactive=True,
            )
        assert prefs.get_remote("rns://id/g/repo") is None


def test_maybe_remember_flag_saves():
    with tempfile.TemporaryDirectory() as tmp:
        prefs = VenvPrefs(tmp)
        maybe_remember_venv(
            prefs,
            "rns://id/g/repo",
            tmp + "/venv",
            venv_explicit=True,
            remember=True,
            no_interactive=True,
        )
        assert prefs.get_remote("rns://id/g/repo") is not None
