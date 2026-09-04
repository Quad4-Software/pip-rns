"""Doctor command tests."""

from __future__ import annotations

from unittest import mock

from opip.doctor import run_doctor as opip_run_doctor
from pip_rns.doctor import run_doctor


def test_pip_rns_doctor_offline_includes_tools():
    checks = run_doctor(online=False)
    names = {c.name for c in checks}
    assert "rngit" in names
    assert "git" in names
    assert "color" in names
    assert "interactive" in names


def test_pip_rns_doctor_online_requires_remote():
    checks = run_doctor(online=True, online_remote=None)
    online = [c for c in checks if c.name == "online"]
    assert online
    assert online[0].ok is False
    assert (
        "no default remote" in online[0].detail.lower()
        or "--remote" in online[0].detail
    )


def test_pip_rns_doctor_online_failure_recorded():
    with mock.patch(
        "pip_rns.releases.list_releases",
        side_effect=RuntimeError("offline"),
    ):
        checks = run_doctor(online=True, online_remote="rns://aabb/g/r")
    online = [c for c in checks if c.name == "online"]
    assert online
    assert online[0].ok is False


def test_opip_doctor_has_data_dir():
    checks = opip_run_doctor()
    names = {c.name for c in checks}
    assert "data-dir" in names
    assert "dest-prefs" in names
