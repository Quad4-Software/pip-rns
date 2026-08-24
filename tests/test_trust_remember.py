"""Tests for trust remember prompt behavior."""

from __future__ import annotations

import tempfile
from unittest import mock

from pip_rns.trust import TrustStore


def test_remember_signer_when_default_exists():
    with tempfile.TemporaryDirectory() as tmp:
        store = TrustStore(tmp)
        store.set_default("a" * 32)
        with mock.patch("builtins.input", return_value="y") as inp:
            from pip_rns.core import _maybe_remember_signer

            _maybe_remember_signer(store, "rns://aa/g/repo", "b" * 32)
        assert inp.called
        assert store.get_remote("rns://aa/g/repo") == "b" * 32
