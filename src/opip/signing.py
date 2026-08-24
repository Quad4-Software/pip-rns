"""Bundle authenticity signing and verification (Reticulum RSG via rnid)."""

import os
import re
import shutil
import subprocess

RSG_EXTENSION = ".rsg"

SIGNATURE_VALID_RE = re.compile(r"Signature is valid", re.IGNORECASE)
SIGNED_BY_RE = re.compile(
    r"signed by\s+<?([0-9a-fA-F]{32})>?",
    re.IGNORECASE,
)


class SigningError(Exception):
    pass


def _check_rnid():
    if shutil.which("rnid") is None:
        raise SigningError(
            "rnid not found on PATH (needed to sign and verify bundles). "
            "Install via: pip install rns"
        )


def signature_path(bundle_path):
    """Return the RSG sidecar path for a bundle file."""
    return bundle_path + RSG_EXTENSION


def has_signature(bundle_path):
    """Return True if an RSG signature sidecar exists for the bundle."""
    return os.path.isfile(signature_path(bundle_path))


def sign_bundle(bundle_path, identity_path):
    """
    Sign a bundle file with a Reticulum identity.

    Writes a .rsg sidecar next to the bundle. Returns the signature path.
    """
    _check_rnid()
    bundle_path = os.path.abspath(bundle_path)
    sig_path = signature_path(bundle_path)
    result = subprocess.run(
        ["rnid", "-f", "-i", identity_path, "-s", bundle_path, "-w", sig_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise SigningError(f"Bundle signing failed: {err}")
    return sig_path


def parse_signer_identity(output):
    """Extract hex identity hash from rnid or rngit verify output."""
    if not output:
        return None
    match = SIGNED_BY_RE.search(output)
    if match:
        return match.group(1).lower()
    return None


def verify_bundle_signature(bundle_path, signer=None):
    """
    Verify the .rsg signature for a bundle file.

    When signer is None, rnid validates against the pubkey embedded in the
    modern .rsg (automatic authenticity check). When signer is set, require
    that exact identity.

    Returns list of error strings (empty if valid or unsigned).
    """
    errors, _identity = verify_bundle_signature_info(bundle_path, signer=signer)
    return errors


def verify_bundle_signature_info(bundle_path, signer=None):
    """
    Verify the .rsg signature for a bundle file.

    Returns (errors, signing_identity_hex_or_None).
    Empty errors means valid or unsigned.
    """
    bundle_path = os.path.abspath(bundle_path)
    sig_path = signature_path(bundle_path)
    if not os.path.isfile(sig_path):
        return [], None

    try:
        _check_rnid()
    except SigningError as exc:
        return [str(exc)], None

    cmd = ["rnid", "-V", bundle_path]
    if signer is not None:
        cmd = ["rnid", "-i", signer, "-V", bundle_path]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    output = (result.stdout or "") + (result.stderr or "")
    identity = parse_signer_identity(output)

    if result.returncode != 0:
        err = output.strip()
        if signer is None and "legacy" in err.lower():
            return [
                "Legacy .rsg requires --signer IDENTITY or OPIP_SIGNER "
                "to verify authenticity."
            ], None
        return [f"Signature check failed for {bundle_path}: {err}"], identity

    if not SIGNATURE_VALID_RE.search(output):
        return [f"Signature check failed for {bundle_path}"], identity

    return [], identity
