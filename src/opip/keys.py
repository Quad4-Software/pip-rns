"""Signing key generation and loading."""

import hashlib
import json
import os

KEY_VERSION = "opip-signing-key-v1"
KEY_SIZE = 32


def generate_signing_key():
    """Return 32-byte signing key material."""
    return os.urandom(KEY_SIZE)


def key_fingerprint(key_material):
    """Return hex SHA-256 fingerprint for a signing key."""
    return hashlib.sha256(key_material).hexdigest()


def save_signing_key(path, key_material):
    """Write signing key to disk (JSON wrapper, restrictive permissions)."""
    payload = {
        "version": KEY_VERSION,
        "algorithm": "hmac-sha256",
        "key": key_material.hex(),
    }
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def load_signing_key(path):
    """Load signing key bytes from file."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("version") != KEY_VERSION:
        raise ValueError("Unsupported signing key version")
    if data.get("algorithm") != "hmac-sha256":
        raise ValueError("Unsupported signing key algorithm")
    try:
        return bytes.fromhex(data["key"])
    except (KeyError, ValueError) as exc:
        raise ValueError("Invalid signing key file") from exc


def export_public_record(key_material, publisher_name, contact=None):
    """Build publisher trust record (share key fingerprint + metadata)."""
    record = {
        "version": KEY_VERSION,
        "algorithm": "hmac-sha256",
        "key_id": key_fingerprint(key_material),
        "publisher": publisher_name,
    }
    if contact:
        record["contact"] = contact
    return record
