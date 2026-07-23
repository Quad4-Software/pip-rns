"""Tests for releases.py. URL parsing, artifact picking, release view parsing."""

from __future__ import annotations

from pip_rns.releases import (
    _parse_rns_url,
    _pick_opip,
    _pick_whl,
    _parse_release_view,
    _parse_release_list,
    _rsg_name_for_artifact,
    release_has_signatures,
)
from tests.support import SkipTest


def test_parse_rns_url_valid():
    dest, group, repo = _parse_rns_url("rns://aabbccdd11223344/mygroup/myrepo")
    assert dest.hex() == "aabbccdd11223344"
    assert group == "mygroup"
    assert repo == "myrepo"


def test_parse_rns_url_auto_prefix():
    dest, group, repo = _parse_rns_url("aabbccdd11223344/mygroup/myrepo")
    assert dest.hex() == "aabbccdd11223344"
    assert group == "mygroup"
    assert repo == "myrepo"


def test_parse_rns_url_strips_whitespace():
    dest, group, repo = _parse_rns_url("  aabbccdd11223344/mygroup/myrepo  ")
    assert dest.hex() == "aabbccdd11223344"


def test_parse_rns_url_invalid_protocol():
    try:
        _parse_rns_url("https://example.com/repo/foo/bar")
        assert False, "should have raised"
    except ValueError as e:
        assert "Invalid URL components" in str(e)


def test_parse_rns_url_invalid_components():
    try:
        _parse_rns_url("rns://aabbccdd/missing")
        assert False, "should have raised"
    except ValueError as e:
        assert "Invalid URL components" in str(e)


def test_pick_whl_prefers_none_any():
    artifacts = [
        {"name": "pkg-1.0-cp39-cp39-linux_x86_64.whl", "size": "1 MB"},
        {"name": "pkg-1.0-py3-none-any.whl", "size": "1 MB"},
    ]
    assert _pick_whl(artifacts) == "pkg-1.0-py3-none-any.whl"


def test_pick_whl_single():
    artifacts = [{"name": "pkg-1.0-py3-none-any.whl", "size": "1 MB"}]
    assert _pick_whl(artifacts) == "pkg-1.0-py3-none-any.whl"


def test_pick_whl_ignores_rsg():
    artifacts = [
        {"name": "pkg.whl.rsg", "size": "230 B"},
        {"name": "pkg.whl", "size": "1 MB"},
    ]
    assert _pick_whl(artifacts) == "pkg.whl"


def test_pick_whl_none():
    assert _pick_whl([]) is None
    assert _pick_whl([{"name": "pkg.tar.gz", "size": "1 MB"}]) is None


def test_pick_opip_single():
    artifacts = [{"name": "my-bundle.opip", "size": "5 MB"}]
    assert _pick_opip(artifacts) == "my-bundle.opip"


def test_pick_opip_pattern():
    artifacts = [
        {"name": "linux.opip", "size": "5 MB"},
        {"name": "win.opip", "size": "6 MB"},
    ]
    assert _pick_opip(artifacts, "win.opip") == "win.opip"


def test_rsg_name_for_artifact():
    assert _rsg_name_for_artifact("bundle.opip") == "bundle.opip.rsg"


SAMPLE_RELEASE_VIEW = """Release : v1.0.0
Status  : published
Created : 2026-05-11 01:18:58
Thanks  : 0

Release Notes
=============

Notes here

Artifacts (3)
=============
 - pkg-1.0.0-py3-none-any.whl (14.72 KB)
 - pkg-1.0.0.tar.gz (17.07 KB)
 - pkg-1.0.0-py3-none-any.whl.rsg (230 B)
"""


def test_parse_release_view():
    info = _parse_release_view(SAMPLE_RELEASE_VIEW)
    assert info["tag"] == "v1.0.0"
    assert info["status"] == "published"
    assert len(info["artifacts"]) == 3
    assert info["artifacts"][0]["name"] == "pkg-1.0.0-py3-none-any.whl"
    assert info["artifacts"][2]["name"] == "pkg-1.0.0-py3-none-any.whl.rsg"
    assert release_has_signatures(info["artifacts"]) is True


SAMPLE_RELEASE_LIST = """Tag          Status     Created              Objs  Notes
------------------------------------------------------------------
v1.0.0       published  2026-05-11 01:18     2     Release notes
v0.1.0       published  2026-05-10 23:13     2     Initial release
"""


def test_parse_release_list():
    releases = _parse_release_list(SAMPLE_RELEASE_LIST)
    assert len(releases) == 2
    assert releases[0]["tag"] == "v1.0.0"
    assert releases[0]["status"] == "published"
    assert releases[1]["tag"] == "v0.1.0"


def test_live_release_list():
    """Optional: list releases for rns-page-node (requires RNS + rngit)."""
    import os

    if not os.environ.get("PIP_RNS_TEST_LIVE"):
        raise SkipTest("set PIP_RNS_TEST_LIVE=1 to run")
    try:
        from pip_rns.releases import list_releases
    except ImportError:
        raise SkipTest("pip-rns not installed in current Python")

    releases = list_releases(
        "rns://06a54b505bb67b25ef3f8097e8001edc/public/rns-page-node"
    )
    assert len(releases) >= 1
    assert any(r["tag"] == "v1.6.0" for r in releases)


def test_live_release_view():
    """Optional: view v1.6.0 release (requires RNS + rngit)."""
    import os

    if not os.environ.get("PIP_RNS_TEST_LIVE"):
        raise SkipTest("set PIP_RNS_TEST_LIVE=1 to run")
    try:
        from pip_rns.releases import release_info
    except ImportError:
        raise SkipTest("pip-rns not installed in current Python")

    info = release_info(
        "rns://06a54b505bb67b25ef3f8097e8001edc/public/rns-page-node", "v1.6.0"
    )
    assert info["status"] == "published"
    whls = [
        a
        for a in info["artifacts"]
        if a["name"].endswith(".whl") and not a["name"].endswith(".rsg")
    ]
    assert len(whls) >= 1
    assert release_has_signatures(info["artifacts"]) is True


def test_live_download_and_verify():
    """Optional: fetch and pin-verify .whl from v1.6.0 (requires RNS + rngit)."""
    import os

    if not os.environ.get("PIP_RNS_TEST_LIVE"):
        raise SkipTest("set PIP_RNS_TEST_LIVE=1 to run")
    try:
        from pip_rns.releases import release_info, fetch_release_artifact, _pick_whl
    except ImportError:
        raise SkipTest("pip-rns not installed in current Python")

    remote = "rns://06a54b505bb67b25ef3f8097e8001edc/public/rns-page-node"
    tag = "v1.6.0"
    verify_id = "e46112d44649266d71fe2193e00a4710"

    info = release_info(remote, tag)
    whl = _pick_whl(info.get("artifacts", []))
    assert whl is not None

    fetched = fetch_release_artifact(remote, tag, whl, verify_identity=verify_id)
    assert os.path.isfile(fetched.path)
    assert fetched.verified is True
    assert fetched.signer == verify_id

    os.unlink(fetched.path)
