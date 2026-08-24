"""Lockfile and SBOM generation for bundles."""

import json

from opip.manifest import utc_now_iso

LOCK_FORMAT = "opip-lock/1"
SBOM_FORMAT = "opip-sbom/1"


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
        if w.get("pypi_sha256"):
            pkg["pypi_sha256"] = w["pypi_sha256"]
        if w.get("pypi_url"):
            pkg["pypi_url"] = w["pypi_url"]
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
    """Create sbom.json content (audit-oriented package list)."""
    lock = make_lock(manifest, wheel_entries)
    sbom = {
        "format": SBOM_FORMAT,
        "created": lock["created"],
        "bundle": lock["bundle"],
        "python_version": lock["python_version"],
        "platform": lock["platform"],
        "platforms": lock.get("platforms", []),
        "publisher": publisher,
        "component_count": len(wheel_entries),
        "components": [],
    }
    for pkg in lock["packages"]:
        sbom["components"].append(
            {
                "type": "python-wheel",
                "name": pkg["name"],
                "version": pkg["version"],
                "filename": pkg["filename"],
                "hashes": {
                    "sha256": pkg["sha256"],
                    "pypi_sha256": pkg.get("pypi_sha256"),
                },
                "source": pkg.get("source"),
                "purl": "pkg:pypi/{}@{}".format(pkg["name"], pkg["version"]),
            }
        )
    return sbom


def dump_json(data):
    return json.dumps(data, indent=2, sort_keys=True) + "\n"
