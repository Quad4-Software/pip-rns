"""Completion install helper tests."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import mock

from opip import completion_cmd as opip_comp
from pip_rns import completion_cmd as pip_comp


def test_pip_rns_completion_dry_run():
    lines = pip_comp.install_completions(shell="bash", dry_run=True)
    assert lines
    assert "->" in lines[0]


def test_opip_completion_dry_run():
    lines = opip_comp.install_completions(shell="zsh", dry_run=True)
    assert lines
    assert "_opip" in lines[0] or "->" in lines[0]


def test_completion_install_into_temp_home():
    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(Path, "home", return_value=Path(tmp)):
            lines = pip_comp.install_completions(shell="bash", dry_run=False)
        dest = (
            Path(tmp)
            / ".local"
            / "share"
            / "bash-completion"
            / "completions"
            / "pip-rns"
        )
        assert dest.is_file()
        assert any(str(dest) in line or "->" in line for line in lines)


def test_detect_shell_from_env():
    with mock.patch.dict(os.environ, {"SHELL": "/usr/bin/zsh"}):
        assert pip_comp.detect_shell() == "zsh"
