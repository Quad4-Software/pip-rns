"""Tests for opip PEP 440 version compare and stable-preferring resolve."""

from opip.resolver import (
    _cmp_version,
    _is_prerelease,
    _spec_allows_prerelease,
    _version_sort_key,
    parse_requirement,
    select_wheel_url,
    version_matches,
)


def test_prerelease_less_than_final():
    assert _cmp_version("3.5b0", "3.5") < 0
    assert _cmp_version("3.5", "3.5b0") > 0
    assert _cmp_version("4.16.0rc2", "4.16.0") < 0
    assert _cmp_version("1.0a1", "1.0b1") < 0
    assert _cmp_version("1.0b1", "1.0rc1") < 0
    assert _cmp_version("1.0rc1", "1.0") < 0
    assert _cmp_version("1.0.dev1", "1.0a1") < 0
    assert _cmp_version("1.0", "1.0.post1") < 0


def test_version_matches_rejects_pre_for_stable_floor():
    assert not version_matches("3.5b0", ">=3.5")
    assert version_matches("3.5", ">=3.5")
    assert version_matches("3.6", ">=3.5")
    assert version_matches("3.5b0", ">=3.5b0")
    assert version_matches("3.5b0", "==3.5b0")
    assert not version_matches("3.5b0", "==3.5")


def test_is_prerelease_and_spec_allows():
    assert _is_prerelease("3.5b0")
    assert _is_prerelease("4.16.0rc2")
    assert _is_prerelease("1.0.dev1")
    assert not _is_prerelease("3.5")
    assert not _is_prerelease("1.0.post1")
    assert _spec_allows_prerelease("==3.5b0")
    assert _spec_allows_prerelease(">=4.16.0rc1")
    assert not _spec_allows_prerelease(">=3.5")
    assert not _spec_allows_prerelease("")


def test_sort_prefers_final_over_pre():
    versions = ["3.5b0", "3.4", "3.5", "3.5rc1"]
    ordered = sorted(versions, key=_version_sort_key)
    assert ordered == ["3.4", "3.5b0", "3.5rc1", "3.5"]


def _fake_pypi(*versions):
    releases = {}
    for ver in versions:
        releases[ver] = [
            {
                "filename": f"pkg-{ver}-py3-none-any.whl",
                "packagetype": "bdist_wheel",
                "url": f"https://example.test/pkg-{ver}.whl",
                "digests": {"sha256": "abc"},
            },
        ]
    return {"releases": releases, "info": {"version": versions[-1]}}


def test_select_wheel_prefers_stable_over_pre():
    data = _fake_pypi("3.5b0", "3.5")
    req = parse_requirement("pyserial>=3.5")
    wheel = select_wheel_url(data, req, "3.14", "manylinux2014_x86_64")
    assert wheel["version"] == "3.5"


def test_select_wheel_unpinned_skips_newer_pre():
    data = _fake_pypi("3.4", "3.5b0")
    req = parse_requirement("pyserial")
    wheel = select_wheel_url(data, req, "3.14", "manylinux2014_x86_64")
    assert wheel["version"] == "3.4"


def test_select_wheel_explicit_pre_allowed():
    data = _fake_pypi("3.5", "3.5b0")
    req = parse_requirement("pyserial==3.5b0")
    wheel = select_wheel_url(data, req, "3.14", "manylinux2014_x86_64")
    assert wheel["version"] == "3.5b0"


def test_select_wheel_falls_back_to_pre_when_only_option():
    data = _fake_pypi("3.5b0")
    req = parse_requirement("pyserial")
    wheel = select_wheel_url(data, req, "3.14", "manylinux2014_x86_64")
    assert wheel["version"] == "3.5b0"
