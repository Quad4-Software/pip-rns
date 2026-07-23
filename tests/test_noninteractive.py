"""Non-interactive / CI behavior tests."""

from __future__ import annotations

import os
from unittest import mock

from opip.interactive import is_ci, is_noninteractive


def _clear_env():
    for key in (
        "CI",
        "GITHUB_ACTIONS",
        "OPIP_NO_INTERACTIVE",
        "PIP_RNS_NO_INTERACTIVE",
    ):
        os.environ.pop(key, None)


def test_is_ci_from_env():
    _clear_env()
    assert is_ci() is False
    os.environ["CI"] = "true"
    assert is_ci() is True
    _clear_env()


def test_is_noninteractive_flag():
    _clear_env()
    with mock.patch("opip.interactive.sys.stdin") as stdin:
        stdin.isatty.return_value = True
        assert is_noninteractive(False) is False
        assert is_noninteractive(True) is True


def test_is_noninteractive_ci():
    _clear_env()
    os.environ["CI"] = "1"
    with mock.patch("opip.interactive.sys.stdin") as stdin:
        stdin.isatty.return_value = True
        assert is_noninteractive() is True
    _clear_env()


def test_is_noninteractive_non_tty():
    _clear_env()
    with mock.patch("opip.interactive.sys.stdin") as stdin:
        stdin.isatty.return_value = False
        assert is_noninteractive() is True


def test_create_fails_without_name_noninteractive():
    from opip.bundle import BundleError
    from opip.cli import _prompt_bundle_name

    try:
        _prompt_bundle_name(True)
        assert False, "expected BundleError"
    except BundleError as exc:
        assert "bundle name" in str(exc).lower() or "name" in str(exc).lower()


def test_open_skips_menu_when_noninteractive():
    from tests.test_opip import _make_test_bundle
    from opip.open_handler import open_bundle
    from opip.storage import Store

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        store = Store(data_dir=os.path.join(tmp, "state"))
        work = os.path.join(tmp, "work")
        os.makedirs(work)
        bundle = os.path.join(tmp, "test.opip")
        _make_test_bundle(work, bundle)
        target = os.path.join(tmp, "site")
        os.makedirs(target)

        with mock.patch("opip.install._find_pip", return_value=False):
            with mock.patch("opip.install.install_wheel_manual"):
                with mock.patch("builtins.input", side_effect=AssertionError("menu")):
                    with mock.patch("opip.interactive.sys.stdin") as stdin:
                        stdin.isatty.return_value = True
                        packages = open_bundle(
                            bundle,
                            store=store,
                            target=target,
                            no_interactive=True,
                            target_explicit=True,
                        )
        assert packages


def test_pip_uninstall_passes_yes():
    from pip_rns.installer import PipInstaller

    inst = PipInstaller()
    with mock.patch(
        "pip_rns.installer.subprocess.run",
        return_value=mock.Mock(returncode=0, stdout="", stderr=""),
    ) as run:
        inst.uninstall("pkg")
    assert "-y" in run.call_args[0][0]
