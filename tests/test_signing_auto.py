"""Tests for automatic .rsg verification without pinned signer."""

from __future__ import annotations

import os
import tempfile

from opip.signing import parse_signer_identity, verify_bundle_signature_info
from tests.support import SkipTest


def test_parse_signer_identity():
    text = "Signature is valid, the file x was signed by <aabbccddeeff00112233445566778899>"
    assert parse_signer_identity(text) == "aabbccddeeff00112233445566778899"
    assert parse_signer_identity("no signer here") is None


def test_live_rnid_auto_verify_without_identity():
    """Optional: sign a file and verify with rnid without -i."""
    import shutil
    import subprocess

    if not os.environ.get("PIP_RNS_TEST_LIVE"):
        raise SkipTest("set PIP_RNS_TEST_LIVE=1 to run")
    if shutil.which("rnid") is None:
        raise SkipTest("rnid not on PATH")

    with tempfile.TemporaryDirectory() as tmp:
        ident = os.path.join(tmp, "id")
        target = os.path.join(tmp, "artifact.bin")
        with open(target, "wb") as fh:
            fh.write(b"pip-rns-auto-verify-test\n")
        gen = subprocess.run(
            ["rnid", "-g", ident],
            capture_output=True,
            text=True,
        )
        assert gen.returncode == 0, gen.stderr or gen.stdout
        signed = subprocess.run(
            ["rnid", "-f", "-i", ident, "-s", target, "-w", target + ".rsg"],
            capture_output=True,
            text=True,
        )
        assert signed.returncode == 0, signed.stderr or signed.stdout

        errors, identity = verify_bundle_signature_info(target)
        assert errors == []
        assert identity is not None
        assert len(identity) == 32

        pinned_bad = verify_bundle_signature_info(
            target,
            signer="e46112d44649266d71fe2193e00a4710",
        )
        assert pinned_bad[0]
