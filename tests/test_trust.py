"""Trust store and verify identity resolution tests."""

from __future__ import annotations

import tempfile

from pip_rns.trust import TrustStore, resolve_verify_identity


def test_trust_store_remote_and_default():
    with tempfile.TemporaryDirectory() as tmp:
        store = TrustStore(tmp)
        store.set_remote("rns://aa/g/repo", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        store.set_default("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
        assert store.get_remote("rns://aa/g/repo") == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        assert store.get_default() == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        assert store.forget_remote("rns://aa/g/repo") is True
        assert store.get_remote("rns://aa/g/repo") is None
        assert store.forget_default() is True
        assert store.get_default() is None


def test_trust_resolve_order():
    with tempfile.TemporaryDirectory() as tmp:
        store = TrustStore(tmp)
        store.set_default("dddddddddddddddddddddddddddddddd")
        store.set_remote("rns://aa/g/repo", "cccccccccccccccccccccccccccccccc")
        assert (
            store.resolve(
                "rns://aa/g/repo", explicit="eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
            )
            == "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        )
        assert store.resolve("rns://aa/g/repo") == "cccccccccccccccccccccccccccccccc"
        assert store.resolve("rns://other/g/x") == "dddddddddddddddddddddddddddddddd"


def test_resolve_verify_identity_insecure_skips_pin():
    with tempfile.TemporaryDirectory() as tmp:
        store = TrustStore(tmp)
        store.set_default("ffffffffffffffffffffffffffffffff")
        assert (
            resolve_verify_identity(
                "rns://aa/g/repo",
                explicit="11111111111111111111111111111111",
                insecure=True,
                config_dir=tmp,
            )
            is None
        )
        assert (
            resolve_verify_identity(
                "rns://aa/g/repo",
                config_dir=tmp,
            )
            == "ffffffffffffffffffffffffffffffff"
        )


def test_trust_list_all():
    with tempfile.TemporaryDirectory() as tmp:
        store = TrustStore(tmp)
        store.set_default("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        store.set_remote("rns://z/g/r", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
        rows = store.list_all()
        assert rows[0] == ("default", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        assert ("rns://z/g/r", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb") in rows
