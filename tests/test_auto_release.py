"""Tests for auto-prefer release wheel behavior."""

from __future__ import annotations

from unittest import mock

from pip_rns import core


def _prefs_ctx():
    prefs = mock.MagicMock()
    prefs.resolve.return_value = None
    return mock.patch.multiple(
        "pip_rns.venv_prefs",
        VenvPrefs=mock.Mock(return_value=prefs),
        maybe_remember_venv=mock.DEFAULT,
    )


def test_install_uses_release_when_probe_hits():
    with mock.patch.object(
        core, "_probe_release_wheel", return_value=("v2.0.1", "pkg.whl")
    ):
        with mock.patch.object(core, "install_from_release") as release:
            with mock.patch.object(core, "_run") as run:
                with mock.patch.object(
                    core, "_resolve_remote_label", return_value="rns://id/g/repo"
                ):
                    with mock.patch(
                        "pip_rns.releases._normalize_remote",
                        return_value="rns://id/g/repo",
                    ):
                        with _prefs_ctx():
                            core.install("repo", no_interactive=True)
        assert release.called
        assert not run.called


def test_install_clones_when_probe_misses():
    with mock.patch.object(core, "_probe_release_wheel", return_value=None):
        with mock.patch.object(core, "install_from_release") as release:
            with mock.patch.object(core, "_run") as run:
                with mock.patch.object(
                    core, "_resolve_remote_label", return_value="rns://id/g/repo"
                ):
                    with mock.patch(
                        "pip_rns.releases._normalize_remote",
                        return_value="rns://id/g/repo",
                    ):
                        with _prefs_ctx():
                            core.install("repo", no_interactive=True)
        assert run.called
        assert not release.called


def test_from_source_skips_probe():
    with mock.patch.object(core, "_probe_release_wheel") as probe:
        with mock.patch.object(core, "_run") as run:
            with mock.patch.object(
                core, "_resolve_remote_label", return_value="rns://id/g/repo"
            ):
                with mock.patch(
                    "pip_rns.releases._normalize_remote",
                    return_value="rns://id/g/repo",
                ):
                    with _prefs_ctx():
                        core.install("repo", from_source=True, no_interactive=True)
        assert run.called
        assert not probe.called


def test_from_release_requires_wheel():
    with mock.patch.object(
        core, "_resolve_remote_label", return_value="rns://id/g/repo"
    ):
        with mock.patch(
            "pip_rns.releases._normalize_remote", return_value="rns://id/g/repo"
        ):
            with _prefs_ctx():
                with mock.patch.object(core, "install_from_release") as release:
                    core.install("repo", from_release=True, no_interactive=True)
                assert release.called
                assert release.call_args.kwargs.get("require_wheel") is True


def test_from_release_and_from_source_conflict():
    try:
        core.install("repo", from_release=True, from_source=True)
        assert False, "expected ValueError"
    except ValueError:
        pass
