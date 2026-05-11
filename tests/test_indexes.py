"""Tests for indexes.py — plain-text parsing and resolution."""

from __future__ import annotations

from pip_rns.indexes import _parse_plain

# -- _parse_plain --


def test_parse_plain_basic():
    result = _parse_plain("pkg-a=111/aaa/pkg-a\npkg-b=222/bbb/pkg-b")
    assert result == {"pkg-a": "111/aaa/pkg-a", "pkg-b": "222/bbb/pkg-b"}


def test_parse_plain_skips_comments():
    result = _parse_plain("# comment\npkg-a=111/aaa/pkg-a\n")
    assert result == {"pkg-a": "111/aaa/pkg-a"}


def test_parse_plain_skips_empty_lines():
    result = _parse_plain("pkg-a=111/aaa/pkg-a\n\n\npkg-b=222/bbb/pkg-b")
    assert result == {"pkg-a": "111/aaa/pkg-a", "pkg-b": "222/bbb/pkg-b"}


def test_parse_plain_skips_lines_without_equals():
    result = _parse_plain("pkg-a=111/aaa/pkg-a\ncorrupt\npkg-b=222/bbb/pkg-b")
    assert result == {"pkg-a": "111/aaa/pkg-a", "pkg-b": "222/bbb/pkg-b"}


def test_parse_plain_strips_whitespace():
    result = _parse_plain("  pkg-a  =  111/aaa/pkg-a  \n")
    assert result == {"pkg-a": "111/aaa/pkg-a"}


def test_parse_plain_empty_input():
    assert _parse_plain("") == {}
    assert _parse_plain("   ") == {}


def test_parse_plain_handles_empty_value():
    result = _parse_plain("pkg-a=\n")
    assert result == {}


def test_parse_plain_handles_empty_key():
    result = _parse_plain("=111/aaa/pkg-a\n")
    assert result == {}


# -- resolve --


def test_resolve_unknown_returns_original():
    from pip_rns.indexes import IndexManager

    mgr = IndexManager()
    mgr._packages = {"known": "abc/def/known"}
    assert mgr.resolve("unknown") == "unknown"


def test_resolve_known_returns_mapped():
    from pip_rns.indexes import IndexManager

    mgr = IndexManager()
    mgr._packages = {"known": "abc/def/known"}
    assert mgr.resolve("known") == "abc/def/known"
