"""Tests for indexes.py — plain-text parsing, JSON parsing, and resolution."""

from __future__ import annotations

from pip_rns.indexes import IndexManager


def _make_mgr() -> IndexManager:
    return IndexManager()


def test_parse_plain_basic():
    mgr = _make_mgr()
    text = "pkg-a=111/aaa/pkg-a\npkg-b=222/bbb/pkg-b"
    result = mgr._parse_plain(text)
    assert result == {"pkg-a": "111/aaa/pkg-a", "pkg-b": "222/bbb/pkg-b"}


def test_parse_plain_skips_comments():
    mgr = _make_mgr()
    text = "# this is a comment\npkg-a=111/aaa/pkg-a\n"
    result = mgr._parse_plain(text)
    assert result == {"pkg-a": "111/aaa/pkg-a"}


def test_parse_plain_skips_empty_lines():
    mgr = _make_mgr()
    text = "pkg-a=111/aaa/pkg-a\n\n\npkg-b=222/bbb/pkg-b"
    result = mgr._parse_plain(text)
    assert result == {"pkg-a": "111/aaa/pkg-a", "pkg-b": "222/bbb/pkg-b"}


def test_parse_plain_skips_lines_without_equals():
    mgr = _make_mgr()
    text = "pkg-a=111/aaa/pkg-a\ncorrupt-line\npkg-b=222/bbb/pkg-b"
    result = mgr._parse_plain(text)
    assert result == {"pkg-a": "111/aaa/pkg-a", "pkg-b": "222/bbb/pkg-b"}


def test_parse_plain_strips_whitespace():
    mgr = _make_mgr()
    text = "  pkg-a  =  111/aaa/pkg-a  \n"
    result = mgr._parse_plain(text)
    assert result == {"pkg-a": "111/aaa/pkg-a"}


def test_parse_plain_empty_input():
    mgr = _make_mgr()
    assert mgr._parse_plain("") == {}
    assert mgr._parse_plain("   ") == {}


def test_parse_plain_handles_empty_value():
    mgr = _make_mgr()
    text = "pkg-a=\n"
    result = mgr._parse_plain(text)
    assert result == {}


def test_parse_plain_handles_empty_key():
    mgr = _make_mgr()
    text = "=111/aaa/pkg-a\n"
    result = mgr._parse_plain(text)
    assert result == {}


def test_resolve_unknown_returns_original():
    mgr = _make_mgr()
    mgr._packages = {"known-pkg": "abc/def/known"}
    result = mgr.resolve("unknown-pkg")
    assert result == "unknown-pkg"


def test_resolve_known_returns_mapped():
    mgr = _make_mgr()
    mgr._packages = {"known-pkg": "abc/def/known"}
    result = mgr.resolve("known-pkg")
    assert result == "abc/def/known"
