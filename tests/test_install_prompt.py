"""Tests for bare-remote install prompts and CLI shorthand."""

from __future__ import annotations

from unittest import mock

from pip_rns.cli import _inject_install_command, _looks_like_remote
from pip_rns.install_prompt import InstallChoice, offer_install_options


def test_looks_like_remote():
    assert _looks_like_remote("rns://id/group/repo") is True
    assert _looks_like_remote("id/group/repo") is True
    assert _looks_like_remote("install") is False
    assert _looks_like_remote("--venv") is False


def test_inject_install_command():
    assert _inject_install_command(["pip-rns", "rns://id/g/repo"]) == [
        "pip-rns",
        "install",
        "rns://id/g/repo",
    ]
    assert _inject_install_command(
        ["pip-rns", "--no-color", "id/g/repo", "--venv", ".venv"]
    ) == ["pip-rns", "--no-color", "install", "id/g/repo", "--venv", ".venv"]
    assert _inject_install_command(["pip-rns", "install", "rns://id/g/repo"]) == [
        "pip-rns",
        "install",
        "rns://id/g/repo",
    ]
    assert _inject_install_command(["pip-rns", "doctor"]) == ["pip-rns", "doctor"]


def test_offer_install_options_noninteractive():
    assert offer_install_options("rns://id/g/repo", no_interactive=True) is None


def test_offer_install_options_master():
    with mock.patch(
        "pip_rns.install_prompt._read_line",
        side_effect=["2"],
    ), mock.patch(
        "pip_rns.install_prompt.is_noninteractive",
        return_value=False,
    ):
        choice = offer_install_options("rns://id/g/repo")
    assert choice == InstallChoice(from_source=True, ref="master")


def test_offer_install_options_abort():
    from pip_rns.errors import UserCancelled

    with mock.patch(
        "pip_rns.install_prompt._read_line",
        side_effect=["6"],
    ), mock.patch(
        "pip_rns.install_prompt.is_noninteractive",
        return_value=False,
    ):
        try:
            offer_install_options("rns://id/g/repo")
            raise AssertionError("expected UserCancelled")
        except UserCancelled:
            pass


def test_offer_install_options_eof_cancels():
    from pip_rns.errors import UserCancelled

    with mock.patch(
        "pip_rns.install_prompt._read_line",
        side_effect=UserCancelled("Cancelled."),
    ), mock.patch(
        "pip_rns.install_prompt.is_noninteractive",
        return_value=False,
    ):
        try:
            offer_install_options("rns://id/g/repo")
            raise AssertionError("expected UserCancelled")
        except UserCancelled:
            pass


def test_bare_remote_prompts_then_clones_master():
    from pip_rns import core

    prefs = mock.MagicMock()
    prefs.resolve.return_value = None
    choice = InstallChoice(from_source=True, ref="master")

    with mock.patch.object(core, "_probe_release_wheel", return_value=None):
        with mock.patch.object(core, "_run") as run:
            with mock.patch.object(
                core,
                "_resolve_remote_label",
                return_value="rns://id/g/repo",
            ):
                with mock.patch(
                    "pip_rns.releases._normalize_remote",
                    return_value="rns://id/g/repo",
                ):
                    with mock.patch.multiple(
                        "pip_rns.venv_prefs",
                        VenvPrefs=mock.Mock(return_value=prefs),
                        maybe_remember_venv=mock.DEFAULT,
                    ):
                        with mock.patch(
                            "pip_rns.install_prompt.offer_install_options",
                            return_value=choice,
                        ):
                            core.install(
                                "rns://id/g/repo",
                                no_interactive=False,
                            )
    assert run.called
    assert run.call_args.kwargs.get("ref") == "master"
