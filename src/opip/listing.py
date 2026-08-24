"""List bundles and installed packages."""

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
    if not bundles:
        return "No bundles registered."
    lines = ["{:<24} {:<8} {:<12} {}".format("NAME", "WHEELS", "PYTHON", "PATH")]
    lines.append("-" * 72)
    for b in bundles:
        lines.append(
            "{:<24} {:<8} {:<12} {}".format(
                b.get("name", "")[:24],
                str(b.get("wheel_count", "")),
                b.get("python_version", ""),
                b.get("path", ""),
            )
        )
    return "\n".join(lines)


def format_install_table(installs):
    if not installs:
        return "No bundle installs recorded."
    lines = ["{:<24} {}".format("BUNDLE", "PACKAGES")]
    lines.append("-" * 56)
    for i in installs:
        pkgs = ", ".join(i.get("packages", []))
        lines.append("{:<24} {}".format(i.get("bundle", "")[:24], pkgs))
    return "\n".join(lines)


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
                security.get("integrity"), security.get("authenticity")
            )
        )
    if has_signature(bundle_path):
        lines.append("Signature: RSG sidecar present")
    platforms = manifest.get("platforms")
    if platforms and manifest.get("platform") == "universal":
        lines.append("Includes: {}".format(", ".join(platforms)))
    lines.extend(["", "Requirements:"])
    for req in manifest.get("requirements", []):
        lines.append(f"  {req}")
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
            "  {} {} ({}{})".format(w.get("package"), w.get("version"), src, prov)
        )
    return "\n".join(lines)
