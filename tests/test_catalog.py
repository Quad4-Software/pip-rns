"""Tests for unified package catalog."""

from __future__ import annotations

import tempfile
from unittest import mock

from pip_rns.aliases import AliasManager
from pip_rns.aliases import init as alias_init
from pip_rns.catalog import CatalogEntry, all_entries, offer_package_picker, search
from pip_rns.discover import DiscoverStore
from pip_rns.errors import UserCancelled


def test_all_entries_priority():
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
                    "latest_tag": "v1.0.0",
                    "source": "scan",
                },
            ],
        )
        alias_init(tmp)
        amgr = AliasManager(tmp)
        amgr.set("lxmfy", "rns://bb/public/LXMFy")
        alias_init(tmp)

        with mock.patch(
            "pip_rns.catalog.get_index_mgr",
            return_value=None,
        ), mock.patch(
            "pip_rns.catalog.DiscoverStore",
            return_value=store,
        ), mock.patch(
            "pip_rns.catalog.get_alias_mgr",
            return_value=amgr,
        ):
            entries = all_entries(tmp)

    assert len(entries) == 1
    assert entries[0].name == "lxmfy"
    assert entries[0].source == "alias"
    assert entries[0].remote == "rns://bb/public/LXMFy"
    assert entries[0].has_wheel is True
    assert entries[0].latest_tag == "v1.0.0"


def test_search_substring():
    entries = [
        CatalogEntry("lxmfy", "rns://a", "discover"),
        CatalogEntry("reticulum", "rns://b", "discover"),
    ]
    with mock.patch("pip_rns.catalog.all_entries", return_value=entries):
        hits = search("lxm")
    assert len(hits) == 1
    assert hits[0].name == "lxmfy"


def test_offer_package_picker_by_number():
    entries = [
        CatalogEntry("lxmfy", "rns://a", "discover", has_wheel=True, latest_tag="v1"),
    ]
    with mock.patch("pip_rns.catalog.all_entries", return_value=entries), mock.patch(
        "pip_rns.catalog._read_line",
        return_value="1",
    ), mock.patch(
        "pip_rns.catalog.is_noninteractive",
        return_value=False,
    ):
        name = offer_package_picker()
    assert name == "lxmfy"


def test_offer_package_picker_noninteractive():
    with mock.patch(
        "pip_rns.catalog.is_noninteractive",
        return_value=True,
    ):
        try:
            offer_package_picker(no_interactive=True)
            raise AssertionError("expected RuntimeError")
        except RuntimeError as exc:
            assert "browse" in str(exc)


def test_offer_package_picker_abort():
    with mock.patch("pip_rns.catalog.all_entries", return_value=[]), mock.patch(
        "pip_rns.catalog.is_noninteractive",
        return_value=False,
    ):
        try:
            offer_package_picker()
            raise AssertionError("expected RuntimeError")
        except RuntimeError:
            pass

    entries = [CatalogEntry("a", "rns://x", "discover")]
    with mock.patch("pip_rns.catalog.all_entries", return_value=entries), mock.patch(
        "pip_rns.catalog._read_line",
        return_value="q",
    ), mock.patch(
        "pip_rns.catalog.is_noninteractive",
        return_value=False,
    ):
        try:
            offer_package_picker()
            raise AssertionError("expected UserCancelled")
        except UserCancelled:
            pass
