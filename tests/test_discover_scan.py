"""Tests for discover scan (Python package cataloging)."""

from __future__ import annotations

import tempfile
from unittest import mock

from pip_rns.discover import DiscoveredNode, DiscoverStore
from pip_rns.discover_scan import (
    DiscoveredPackage,
    format_package_line,
    install_hint,
    package_name_for,
    parse_nomad_groups,
    parse_nomad_repos,
    remote_for,
)

SAMPLE_INDEX = """
> Groups

`![  • public`:/page/group.mu`g=public]! (2 repositories)
`![  • tools`:/page/group.mu`g=tools]! (1 repository)
"""

SAMPLE_GROUP = """
> Repositories

`![  • LXMFy`:/page/repo.mu`g=public|r=LXMFy]! - lxmf bots
`![  • pip-rns`:/page/repo.mu`g=public|r=pip-rns]!
"""


def test_parse_nomad_groups():
    groups = parse_nomad_groups(SAMPLE_INDEX)
    assert groups == ["public", "tools"]


def test_parse_nomad_repos():
    repos = parse_nomad_repos(SAMPLE_GROUP)
    assert ("public", "LXMFy") in repos
    assert ("public", "pip-rns") in repos


def test_remote_and_name_helpers():
    assert remote_for("aa" * 16, "public", "LXMFy").endswith("/public/LXMFy")
    assert package_name_for("LXMFy") == "lxmfy"
    assert package_name_for("Foo_Bar", "MyPkg") == "mypkg"


def test_install_hint_prefers_release():
    pkg = DiscoveredPackage(
        name="lxmfy",
        remote="rns://aa/public/LXMFy",
        destination_hash="aa",
        group="public",
        repo="LXMFy",
        has_wheel=True,
        latest_tag="v1.0.0",
    )
    hint = install_hint(pkg)
    assert hint == "pip-rns install lxmfy"


def test_store_packages_resolve():
    with tempfile.TemporaryDirectory() as tmp:
        store = DiscoverStore(tmp)
        store.merge(
            [
                DiscoveredNode(
                    destination_hash="aa" * 16,
                    identity_hash="bb" * 16,
                    node_name="n1",
                    heard_at=1.0,
                )
            ]
        )
        store.merge_packages(
            [
                DiscoveredPackage(
                    name="lxmfy",
                    remote=f"rns://{'aa' * 16}/public/LXMFy",
                    destination_hash="aa" * 16,
                    group="public",
                    repo="LXMFy",
                    has_wheel=True,
                    latest_tag="v1.2.0",
                    source="nomad",
                )
            ]
        )
        assert store.resolve_package("LXMFy") == f"rns://{'aa' * 16}/public/LXMFy"
        assert store.resolve_package("missing") is None
        line = format_package_line(
            DiscoveredPackage.from_dict(store.list_packages()[0])
        )
        assert "lxmfy" in line
        assert "wheel:v1.2.0" in line


def test_core_resolve_uses_discovered_packages():
    from pip_rns.core import _resolve_remote_label

    with tempfile.TemporaryDirectory() as tmp:
        store = DiscoverStore(tmp)
        store.merge_packages(
            [
                DiscoveredPackage(
                    name="demo",
                    remote="rns://aabbccddeeff00112233445566778899/public/Demo",
                    destination_hash="aabbccddeeff00112233445566778899",
                    group="public",
                    repo="Demo",
                )
            ]
        )
        with mock.patch("pip_rns.discover.DiscoverStore", return_value=store):
            resolved = _resolve_remote_label("demo")
        assert resolved.endswith("/public/Demo")


def test_maybe_auto_alias():
    from pip_rns.aliases import AliasManager
    from pip_rns.discover_scan import maybe_auto_alias

    with tempfile.TemporaryDirectory() as tmp:
        amgr = AliasManager(tmp)
        pkg = DiscoveredPackage(
            name="lxmfy",
            remote="rns://aa/public/LXMFy",
            destination_hash="aa",
            group="public",
            repo="LXMFy",
        )
        n = maybe_auto_alias([pkg], amgr, auto=True, no_interactive=True)
        assert n == 1
        assert amgr.get("lxmfy") == "rns://aa/public/LXMFy"
