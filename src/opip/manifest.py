"""Bundle manifest schema and serialization."""

import json
from datetime import datetime, timezone


MANIFEST_VERSION = "2"
MANIFEST_VERSION_LEGACY = "1"
BUNDLE_EXTENSION = ".opip"
SUPPORTED_VERSIONS = (MANIFEST_VERSION, MANIFEST_VERSION_LEGACY)


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_manifest(
    name, requirements, wheels, python_version, platform_tag, extras=None
):
    """Build a new bundle manifest dict."""
    manifest = {
        "version": MANIFEST_VERSION,
        "name": name,
        "created": utc_now_iso(),
        "python_version": python_version,
        "platform": platform_tag,
        "requirements": list(requirements),
        "wheels": wheels,
        "security": {
            "integrity": "sha256",
            "authenticity": "reticulum-rsg",
            "provenance": "pypi-digest",
        },
    }
    if extras:
        manifest.update(extras)
    return manifest


def load_manifest(data):
    """Parse manifest from dict or JSON string."""
    if isinstance(data, str):
        data = json.loads(data)
    version = data.get("version")
    if version not in SUPPORTED_VERSIONS:
        raise ValueError("Unsupported manifest version: {0}".format(version))
    return data


def dump_manifest(manifest):
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"
