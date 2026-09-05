# Copyright (c) 2026, Quad4 (quad4.io)
"""Reticulum identity management for bundle signing."""

import os
import re
import shutil
import subprocess

IDENTITY_HASH_RE = re.compile(r"<([0-9a-f]{32})>")


class IdentityError(Exception):
    pass


def _check_rnid():
    if shutil.which("rnid") is None:
        raise IdentityError("rnid not found on PATH. Install via: pip install rns")


def generate_identity(path):
    """Generate a new Reticulum identity and save to path."""
    _check_rnid()
    path = os.path.abspath(path)
    result = subprocess.run(
        ["rnid", "-g", path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise IdentityError(f"rnid identity generation failed: {err}")
    return path


def identity_hash(identity):
    """Return hex identity hash from a path or 32-char hash string."""
    identity = identity.strip()
    if len(identity) == 32 and all(c in "0123456789abcdef" for c in identity):
        return identity
    _check_rnid()
    result = subprocess.run(
        ["rnid", "-i", identity, "-p"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise IdentityError(f"Failed to read identity: {err}")
    for line in result.stdout.splitlines():
        if "Identity Hash" in line:
            match = IDENTITY_HASH_RE.search(line)
            if match:
                return match.group(1)
    raise IdentityError("Could not parse identity hash from rnid output")


def export_public_record(identity, publisher_name, contact=None):
    """Build publisher trust record (share identity hash + metadata)."""
    record = {
        "version": "reticulum-identity-v1",
        "identity": identity_hash(identity),
        "publisher": publisher_name,
    }
    if contact:
        record["contact"] = contact
    return record
