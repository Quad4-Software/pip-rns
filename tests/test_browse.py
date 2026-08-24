"""Tests for pip-rns browse command."""

from __future__ import annotations

import tempfile
from unittest import mock

from pip_rns.aliases import AliasManager
from pip_rns.aliases import init as alias_init
from pip_rns.browse import run_browse
from pip_rns.discover import DiscoveredNode
from pip_rns.discover_scan import DiscoveredPackage


def _sample_pkg():
    return DiscoveredPackage(
        name="lxmfy",
        remote="rns://aa/public/LXMFy",
        destination_hash="aa",
        group="public",
        repo="LXMFy",
        has_wheel=True,
        latest_tag="v1.0.0",
    )


def test_browse_no_listen_scan_only():
    with tempfile.TemporaryDirectory() as tmp:
        from pip_rns.discover import DiscoverStore

        store = DiscoverStore(tmp)
        store.merge(
            [
                DiscoveredNode(
                    destination_hash="aa" * 16,
                    heard_at=1.0,
                )
            ]
        )

        with mock.patch(
            "pip_rns.browse.DiscoverStore",
            return_value=store,
        ), mock.patch(
            "pip_rns.browse.scan_nodes",
            return_value=[_sample_pkg()],
        ), mock.patch(
            "pip_rns.browse.get_alias_mgr",
            return_value=None,
        ), mock.patch(
            "pip_rns.browse._prompt_install",
            return_value=False,
        ):
            pkgs = run_browse(
                config_dir=tmp,
                no_listen=True,
                no_interactive=True,
            )
        assert len(pkgs) == 1
        assert pkgs[0].name == "lxmfy"


def test_browse_noninteractive_no_nodes():
    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch(
            "pip_rns.browse.DiscoverStore",
        ) as store_cls:
            store = store_cls.return_value
            store.list_nodes.return_value = []
            try:
                run_browse(config_dir=tmp, no_listen=True, no_interactive=True)
                raise AssertionError("expected RuntimeError")
            except RuntimeError as exc:
                assert "No saved nodes" in str(exc)


def test_browse_auto_alias():
    with tempfile.TemporaryDirectory() as tmp:
        alias_init(tmp)
        amgr = AliasManager(tmp)
        from pip_rns.discover import DiscoverStore

        store = DiscoverStore(tmp)
        store.merge([DiscoveredNode(destination_hash="aa" * 16, heard_at=1.0)])

        with mock.patch(
            "pip_rns.browse.DiscoverStore",
            return_value=store,
        ), mock.patch(
            "pip_rns.browse.scan_nodes",
            return_value=[_sample_pkg()],
        ), mock.patch(
            "pip_rns.browse.get_alias_mgr",
            return_value=amgr,
        ), mock.patch(
            "pip_rns.browse._prompt_install",
            return_value=False,
        ):
            run_browse(
                config_dir=tmp,
                no_listen=True,
                auto_alias=True,
                no_interactive=True,
            )
        assert amgr.get("lxmfy") == "rns://aa/public/LXMFy"


def test_browse_install_flow():
    with tempfile.TemporaryDirectory() as tmp:
        from pip_rns.discover import DiscoverStore

        store = DiscoverStore(tmp)
        store.merge_packages([_sample_pkg().as_dict()])

        with mock.patch(
            "pip_rns.browse.DiscoverStore",
            return_value=store,
        ), mock.patch(
            "pip_rns.browse.scan_nodes",
            return_value=[],
        ), mock.patch(
            "pip_rns.browse.get_alias_mgr",
            return_value=None,
        ), mock.patch(
            "pip_rns.browse.offer_package_picker",
            return_value="lxmfy",
        ), mock.patch(
            "pip_rns.core.install",
        ) as inst:
            run_browse(
                config_dir=tmp,
                no_listen=True,
                no_scan=True,
                do_install=True,
                no_interactive=True,
            )
            assert inst.called
            assert inst.call_args[0][0] == "lxmfy"
