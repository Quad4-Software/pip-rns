"""Tests for default release signature verification behavior."""

from __future__ import annotations

from unittest import mock

from pip_rns.releases import (
    _parse_fetch_verify,
    release_has_signatures,
)
from tests.support import SkipTest


def test_release_has_signatures_true():
    artifacts = [
        {"name": "pkg-1.0.0-py3-none-any.whl", "size": "14.72 KB"},
        {"name": "pkg-1.0.0-py3-none-any.whl.rsg", "size": "230 B"},
    ]
    assert release_has_signatures(artifacts) is True


def test_release_has_signatures_false():
    artifacts = [
        {"name": "pkg-1.0.0-py3-none-any.whl", "size": "14.72 KB"},
        {"name": "pkg-1.0.0.tar.gz", "size": "17.07 KB"},
    ]
    assert release_has_signatures(artifacts) is False


def test_parse_fetch_verify_extracts_signer():
    stdout = (
        "Release manifest validated, signed by <e46112d44649266d71fe2193e00a4710>\n"
        "Fetching 1 artifact...\n"
    )
    verified, signer = _parse_fetch_verify(stdout)
    assert verified is True
    assert signer == "e46112d44649266d71fe2193e00a4710"


def test_parse_fetch_verify_unverified():
    verified, signer = _parse_fetch_verify("Fetching artifact...\n")
    assert verified is False
    assert signer is None


def test_fetch_passes_no_signer_by_default():
    """Default fetch must not require -s. rngit still validates .rsm/.rsg."""
    from pip_rns.releases import fetch_release_artifact

    fake = mock.Mock(
        returncode=0,
        stdout=(
            "Release manifest validated, signed by <e46112d44649266d71fe2193e00a4710>\n"
        ),
        stderr="",
    )
    with mock.patch("pip_rns.releases.subprocess.run", return_value=fake) as run:
        with mock.patch(
            "pip_rns.releases.tempfile.mkdtemp",
            return_value="/tmp/pip-rns-fetch-x",
        ):
            with mock.patch("pip_rns.releases.shutil.rmtree"):
                with mock.patch("pip_rns.progress.RnsWait"):
                    try:
                        fetch_release_artifact("rns://aabb/g/r", "v1", "pkg.whl")
                    except Exception:
                        pass
    assert run.called
    cmd = run.call_args[0][0]
    assert cmd[0] == "rngit"
    assert "-s" not in cmd


def test_fetch_pins_signer_when_verify_identity_set():
    from pip_rns.releases import fetch_release_artifact

    fake = mock.Mock(
        returncode=0,
        stdout=(
            "Release manifest validated, signed by <e46112d44649266d71fe2193e00a4710>\n"
        ),
        stderr="",
    )
    with mock.patch("pip_rns.releases.subprocess.run", return_value=fake) as run:
        with mock.patch(
            "pip_rns.releases.tempfile.mkdtemp",
            return_value="/tmp/pip-rns-fetch-y",
        ):
            with mock.patch("pip_rns.releases.shutil.rmtree"):
                with mock.patch("pip_rns.progress.RnsWait"):
                    try:
                        fetch_release_artifact(
                            "rns://aabb/g/r",
                            "v1",
                            "pkg.whl",
                            verify_identity="e46112d44649266d71fe2193e00a4710",
                        )
                    except Exception:
                        pass
    cmd = run.call_args[0][0]
    assert "-s" in cmd
    assert "e46112d44649266d71fe2193e00a4710" in cmd


def test_live_download_auto_verify():
    """Optional: fetch .whl with default auto verify (no --verify pin)."""
    import os

    if not os.environ.get("PIP_RNS_TEST_LIVE"):
        raise SkipTest("set PIP_RNS_TEST_LIVE=1 to run")
    try:
        from pip_rns.releases import (
            _pick_whl,
            fetch_release_artifact,
            release_info,
        )
    except ImportError:
        raise SkipTest("pip-rns not installed in current Python")

    remote = "rns://06a54b505bb67b25ef3f8097e8001edc/public/rns-page-node"
    tag = "v1.6.0"

    info = release_info(remote, tag)
    assert release_has_signatures(info.get("artifacts", [])) is True
    whl = _pick_whl(info.get("artifacts", []))
    assert whl is not None

    fetched = fetch_release_artifact(remote, tag, whl)
    assert os.path.isfile(fetched.path)
    assert fetched.verified is True
    assert fetched.signer is not None

    os.unlink(fetched.path)
