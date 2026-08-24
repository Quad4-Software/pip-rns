"""Discovery store and announce-handler unit tests."""

from __future__ import annotations

import tempfile
from unittest import mock

from pip_rns.discover import (
    DiscoveredNode,
    DiscoverStore,
    _decode_node_name,
    _GitReposHandler,
    discover_nodes,
    format_node_line,
)
from pip_rns.doctor import run_doctor


def test_decode_node_name():
    assert _decode_node_name(None) is None
    assert _decode_node_name(b"peer-one\nextra") == "peer-one"
    assert _decode_node_name("") is None


def test_handler_records_announce():
    h = _GitReposHandler()

    class Ident:
        hash = bytes.fromhex("11" * 16)

    h.received_announce(bytes.fromhex("22" * 16), Ident(), b"lab")
    assert "22" * 16 in h.found
    node = h.found["22" * 16]
    assert node.identity_hash == "11" * 16
    assert node.node_name == "lab"


def test_discover_store_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        store = DiscoverStore(tmp)
        n = DiscoveredNode(
            destination_hash="aa" * 16,
            identity_hash="bb" * 16,
            node_name="n1",
            heard_at=1.0,
        )
        store.merge([n])
        store2 = DiscoverStore(tmp)
        rows = store2.list_nodes()
        assert len(rows) == 1
        assert rows[0].destination_hash == "aa" * 16
        assert rows[0].node_name == "n1"
        assert store2.clear() == 1
        assert store2.list_nodes() == []


def test_format_node_line():
    line = format_node_line(DiscoveredNode(destination_hash="cc" * 16, node_name=None))
    assert line.startswith("cc" * 16)
    assert line.endswith("\t-")


def test_discover_nodes_requires_rns():
    with mock.patch("pip_rns.discover._import_rns", side_effect=ImportError("missing")):
        try:
            discover_nodes(seconds=0)
            raise AssertionError("expected RuntimeError")
        except RuntimeError as exc:
            assert "RNS is required" in str(exc)


def test_doctor_includes_discover():
    with tempfile.TemporaryDirectory() as tmp:
        checks = run_doctor(online=False, config_dir=tmp)
    names = {c.name for c in checks}
    assert "discover" in names
    assert "rns-python" in names
