"""Tests for discover metadata driving install defaults."""

from __future__ import annotations

import tempfile
from unittest import mock

from pip_rns.discover import DiscoverStore


def test_get_package_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        store = DiscoverStore(tmp)
        store.merge_packages(
            [
                {
                    "name": "lxmfy",
                    "remote": "rns://aa/public/LXMFy",
                    "destination_hash": "aa",
                    "group": "public",
                    "repo": "LXMFy",
                    "has_wheel": True,
                    "latest_tag": "v1.2.0",
                    "source": "scan",
                },
            ],
        )
        pkg = store.get_package("lxmfy")
        assert pkg is not None
        assert pkg["latest_tag"] == "v1.2.0"
        assert store.resolve_package("lxmfy") == "rns://aa/public/LXMFy"


def test_install_uses_discovered_release_tag():
    with tempfile.TemporaryDirectory() as tmp:
        store = DiscoverStore(tmp)
        store.merge_packages(
            [
                {
                    "name": "lxmfy",
                    "remote": "rns://aa/public/LXMFy",
                    "destination_hash": "aa",
                    "group": "public",
                    "repo": "LXMFy",
                    "has_wheel": True,
                    "latest_tag": "v1.2.0",
                    "source": "scan",
                },
            ],
        )

        with mock.patch(
            "pip_rns.discover.DiscoverStore",
            return_value=store,
        ), mock.patch(
            "pip_rns.core._resolve_remote_label",
            return_value="rns://aa/public/LXMFy",
        ), mock.patch(
            "pip_rns.core.install_from_release",
            return_value=None,
        ) as rel, mock.patch(
            "pip_rns.install_prompt.offer_install_options",
            side_effect=AssertionError("menu should be skipped"),
        ), mock.patch(
            "pip_rns.core._probe_release_wheel",
            return_value=("v1.2.0", "pkg.whl"),
        ), mock.patch(
            "pip_rns.venv_prefs.maybe_remember_venv",
        ):
            from pip_rns.core import install

            install(
                "lxmfy",
                config_dir=tmp,
                no_interactive=True,
            )

        assert rel.called
        call_kwargs = rel.call_args[1]
        assert call_kwargs.get("ref") == "v1.2.0"


def test_install_skips_menu_for_bare_remote():
    with mock.patch(
        "pip_rns.install_prompt.offer_install_options",
        return_value=None,
    ) as menu, mock.patch(
        "pip_rns.core._resolve_remote_label",
        return_value="rns://aa/public/LXMFy",
    ), mock.patch(
        "pip_rns.core._probe_release_wheel",
        return_value=("v1.0.0", "pkg.whl"),
    ), mock.patch(
        "pip_rns.core.install_from_release",
        return_value=None,
    ):
        from pip_rns.core import install

        install("rns://aa/public/LXMFy", no_interactive=True)
    assert menu.called
