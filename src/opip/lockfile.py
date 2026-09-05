# Copyright (c) 2026, Quad4 (quad4.io)
"""Lockfile and CycloneDX SBOM generation for bundles."""

import json
import uuid

from opip.manifest import utc_now_iso

LOCK_FORMAT = "opip-lock/1"
CYCLONEDX_SPEC = "1.5"


def make_lock(manifest, wheel_entries):
    """Create lock.json content."""
    packages = []
    for w in sorted(wheel_entries, key=lambda x: x.get("package", "")):
        pkg = {
            "name": w.get("package"),
            "version": w.get("version"),
            "filename": w.get("filename"),
            "sha256": w.get("sha256"),
            "source": w.get("source", "pypi"),
        }
        source_sha = w.get("source_sha256") or w.get("pypi_sha256")
        if source_sha:
            pkg["pypi_sha256"] = source_sha
            pkg["source_sha256"] = source_sha
        source_url = w.get("source_url") or w.get("pypi_url")
        if source_url:
            pkg["pypi_url"] = source_url
            pkg["source_url"] = source_url
        if w.get("provenance_verified") is not None:
            pkg["provenance_verified"] = w["provenance_verified"]
        if w.get("built_from"):
            pkg["built_from"] = w["built_from"]
        packages.append(pkg)

    return {
        "format": LOCK_FORMAT,
        "created": manifest.get("created") or utc_now_iso(),
        "bundle": manifest.get("name"),
        "python_version": manifest.get("python_version"),
        "platform": manifest.get("platform"),
        "platforms": manifest.get("platforms", []),
        "requirements": manifest.get("requirements", []),
        "pinned_requirements": manifest.get("pinned_requirements", []),
        "packages": packages,
    }


def make_sbom(manifest, wheel_entries, publisher=None):
    """Create CycloneDX 1.5 JSON SBOM."""
    components = []
    for w in sorted(wheel_entries, key=lambda x: x.get("package", "")):
        name = w.get("package") or "unknown"
        version = w.get("version") or "0"
        hashes = []
        if w.get("sha256"):
            hashes.append({"alg": "SHA-256", "content": w["sha256"]})
        source_sha = w.get("source_sha256") or w.get("pypi_sha256")
        if source_sha and source_sha != w.get("sha256"):
            hashes.append({"alg": "SHA-256", "content": source_sha})
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "bom-ref": f"pkg:pypi/{name}@{version}",
                "purl": f"pkg:pypi/{name}@{version}",
                "hashes": hashes,
                "properties": [
                    {"name": "opip:filename", "value": w.get("filename") or ""},
                    {"name": "opip:source", "value": w.get("source") or "pypi"},
                ],
            },
        )

    metadata = {
        "timestamp": manifest.get("created") or utc_now_iso(),
        "component": {
            "type": "application",
            "name": manifest.get("name") or "opip-bundle",
            "version": "0",
        },
        "properties": [
            {
                "name": "opip:python_version",
                "value": str(manifest.get("python_version") or ""),
            },
            {
                "name": "opip:platform",
                "value": str(manifest.get("platform") or ""),
            },
        ],
    }
    if publisher:
        tools = {
            "components": [
                {
                    "type": "application",
                    "name": "opip",
                    "publisher": publisher.get("name") or "opip",
                },
            ],
        }
        metadata["tools"] = tools
        if publisher.get("identity"):
            metadata["properties"].append(
                {"name": "opip:publisher_identity", "value": publisher["identity"]},
            )

    return {
        "bomFormat": "CycloneDX",
        "specVersion": CYCLONEDX_SPEC,
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": metadata,
        "components": components,
    }


def dump_json(data):
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def load_lock(data):
    if isinstance(data, str):
        data = json.loads(data)
    return data


def diff_locks(old_packages, new_packages):
    """Compare package lists by (filename, sha256).

    Returns dict with added, removed, changed, unchanged lists of filenames.
    """
    old_map = {
        p.get("filename"): p.get("sha256") for p in old_packages if p.get("filename")
    }
    new_map = {
        p.get("filename"): p.get("sha256") for p in new_packages if p.get("filename")
    }
    added = sorted(set(new_map) - set(old_map))
    removed = sorted(set(old_map) - set(new_map))
    changed = sorted(
        f
        for f in set(old_map) & set(new_map)
        if old_map[f] and new_map[f] and old_map[f] != new_map[f]
    )
    unchanged = sorted(f for f in set(old_map) & set(new_map) if f not in changed)
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
    }
