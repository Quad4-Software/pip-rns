"""Bundle authenticity signing and verification (Reticulum RSG via rnid)."""

import os
import re
import shutil
import subprocess

RSG_EXTENSION = ".rsg"

SIGNATURE_VALID_RE = re.compile(r"Signature is valid", re.IGNORECASE)


class SigningError(Exception):
    pass


def _check_rnid():
    if shutil.which("rnid") is None:
        raise SigningError(
            "rnid not found on PATH. Install via: pip install rns"
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
        raise SigningError("Bundle signing failed: {0}".format(err))
    return sig_path


def verify_bundle_signature(bundle_path, signer=None):
    """
    Verify the .rsg signature for a bundle file.

    Returns list of error strings (empty if valid or unsigned).
    """
    bundle_path = os.path.abspath(bundle_path)
    sig_path = signature_path(bundle_path)
    if not os.path.isfile(sig_path):
        return []

    if signer is None:
        return ["Bundle is signed but no signer identity provided (--signer)"]

    _check_rnid()
    result = subprocess.run(
        ["rnid", "-i", signer, "-V", bundle_path, sig_path],
        capture_output=True,
        text=True,
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        err = output.strip()
        return ["Signature verification failed: {0}".format(err)]
    if not SIGNATURE_VALID_RE.search(output):
        return ["Signature verification failed"]
    return []
