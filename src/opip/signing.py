"""Bundle authenticity signing and verification (HMAC-SHA256, stdlib only)."""

import hashlib
import hmac
import json

from opip.integrity import data_hash
from opip.keys import key_fingerprint

AUTH_ALGORITHM = "hmac-sha256-v1"
AUTH_FILE = "authenticity.json"


def sign_integrity(integrity_bytes, key_material, publisher, key_id=None):
    """Sign integrity.json bytes. Returns authenticity dict."""
    digest = data_hash(integrity_bytes)
    signature = hmac.new(key_material, digest.encode("ascii"), hashlib.sha256).hexdigest()
    return {
        "version": "1",
        "algorithm": AUTH_ALGORITHM,
        "publisher": publisher,
        "key_id": key_id or key_fingerprint(key_material),
        "integrity_sha256": digest,
        "signature": signature,
    }


def verify_authenticity(integrity_bytes, authenticity, trust_key=None):
    """
    Verify authenticity.json against integrity.json bytes.

    Returns list of error strings (empty if valid or not signed).
    """
    if not authenticity:
        return []

    errors = []
    if authenticity.get("algorithm") != AUTH_ALGORITHM:
        errors.append("Unsupported authenticity algorithm")
        return errors

    digest = data_hash(integrity_bytes)
    if authenticity.get("integrity_sha256") != digest:
        errors.append("Authenticity record does not match integrity.json digest")

    if trust_key is None:
        errors.append("No trust key provided")
        return errors

    expected_key_id = key_fingerprint(trust_key)
    if authenticity.get("key_id") != expected_key_id:
        errors.append(
            "Signing key fingerprint mismatch (expected {0}, got {1})".format(
                expected_key_id[:16], str(authenticity.get("key_id", ""))[:16]
            )
        )

    signature = authenticity.get("signature", "")
    expected = hmac.new(trust_key, digest.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        errors.append("Authenticity signature verification failed")

    return errors


def dump_authenticity(record):
    return json.dumps(record, indent=2, sort_keys=True) + "\n"


def load_authenticity(data):
    if isinstance(data, str):
        return json.loads(data)
    return data
