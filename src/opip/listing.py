# Copyright (c) 2026, Quad4 (quad4.io)
"""List bundles and installed packages."""

import json

from opip.bundle import bundle_info
from opip.signing import has_signature
from opip.storage import Store


def list_bundles(store=None):
    """Return registered bundle entries."""
    store = store or Store()
    return store.list_bundles()


def list_installed(store=None):
    """Return install records."""
    store = store or Store()
    return store.list_installs()


def format_bundle_table(bundles):
    """Return a fixed-width table of registered bundles."""
    if not bundles:
        return "No bundles registered."
    lines = ["{:<24} {:<8} {:<12} {}".format("NAME", "WHEELS", "PYTHON", "PATH")]
    lines.append("-" * 72)
    lines.extend(
        "{:<24} {:<8} {:<12} {}".format(
            b.get("name", "")[:24],
            str(b.get("wheel_count", "")),
            b.get("python_version", ""),
            b.get("path", ""),
        )
        for b in bundles
    )
    return "\n".join(lines)


def format_install_table(installs):
    """Return a fixed-width table of recorded bundle installs."""
    if not installs:
        return "No bundle installs recorded."
    lines = ["{:<24} {}".format("BUNDLE", "PACKAGES")]
    lines.append("-" * 56)
    for i in installs:
        pkgs = ", ".join(i.get("packages", []))
        lines.append("{:<24} {}".format(i.get("bundle", "")[:24], pkgs))
    return "\n".join(lines)


def bundles_as_json(bundles):
    """Serialize registered bundles for --json list."""
    return json.dumps(bundles, indent=2, sort_keys=True)


def installs_as_json(installs):
    """Serialize install records for --json list installed."""
    return json.dumps(installs, indent=2, sort_keys=True)


def bundle_info_dict(bundle_path):
    """Structured metadata for --json info."""
    manifest = bundle_info(bundle_path)
    return {
        "name": manifest.get("name"),
        "created": manifest.get("created"),
        "python_version": manifest.get("python_version"),
        "platform": manifest.get("platform"),
        "platforms": manifest.get("platforms") or [],
        "wheel_count": len(manifest.get("wheels", [])),
        "manifest_version": manifest.get("version"),
        "security": manifest.get("security"),
        "signature": has_signature(bundle_path),
        "requirements": list(manifest.get("requirements") or []),
        "packages": [
            {
                "name": w.get("package"),
                "version": w.get("version"),
                "filename": w.get("filename"),
                "source": w.get("source", "pypi"),
            }
            for w in manifest.get("wheels", [])
        ],
    }


def verify_result_dict(ok, path, errors, manifest):
    """Structured verify result for --json verify."""
    summary = None
    if manifest:
        summary = {
            "name": manifest.get("name"),
            "python_version": manifest.get("python_version"),
            "platform": manifest.get("platform"),
            "wheel_count": len(manifest.get("wheels", [])),
            "manifest_version": manifest.get("version"),
        }
    return {
        "ok": bool(ok),
        "path": path,
        "errors": list(errors or []),
        "manifest_summary": summary,
    }


def show_bundle_info(bundle_path):
    """Return formatted info for a bundle file."""
    manifest = bundle_info(bundle_path)
    lines = [
        "Name:     {}".format(manifest.get("name")),
        "Created:  {}".format(manifest.get("created")),
        "Python:   {}".format(manifest.get("python_version")),
        "Platform: {}".format(manifest.get("platform")),
        "Wheels:   {}".format(len(manifest.get("wheels", []))),
        "Manifest: v{}".format(manifest.get("version", "?")),
    ]
    security = manifest.get("security")
    if security:
        lines.append(
            "Security: integrity={}, authenticity={}".format(
                security.get("integrity"),
                security.get("authenticity"),
            ),
        )
    if has_signature(bundle_path):
        lines.append("Signature: RSG sidecar present")
    platforms = manifest.get("platforms")
    if platforms and manifest.get("platform") == "universal":
        lines.append("Includes: {}".format(", ".join(platforms)))
    lines.extend(["", "Requirements:"])
    lines.extend(f"  {req}" for req in manifest.get("requirements", []))
    lines.append("")
    lines.append("Packages:")
    for w in manifest.get("wheels", []):
        src = w.get("source", "pypi")
        prov = ""
        if w.get("pypi_sha256"):
            prov = " pypi-sha256"
        elif w.get("source") == "local":
            prov = " local"
        lines.append(
            "  {} {} ({}{})".format(w.get("package"), w.get("version"), src, prov),
        )
    return "\n".join(lines)
