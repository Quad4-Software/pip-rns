"""Tests for doctor --fix suggestions."""

from __future__ import annotations

import io
from unittest import mock

from pip_rns.doctor import Check, print_doctor, run_doctor


def test_check_has_fix_field():
    checks = run_doctor(online=False, config_dir="/tmp/nonexistent-pip-rns-test")
    discover = next(c for c in checks if c.name == "discover")
    if not discover.ok or discover.level == "warn":
        assert discover.fix == "pip-rns browse"


def test_print_doctor_show_fix():
    checks = [
        Check("rngit", False, "missing", "fail", fix="pip install rns"),
        Check("pip", True, "ok", "pass"),
    ]
    buf = io.StringIO()
    with mock.patch("sys.stdout", buf):
        code = print_doctor(checks, show_fix=True)
    out = buf.getvalue()
    assert "fix:" in out
    assert "pip install rns" in out
    assert code == 1
