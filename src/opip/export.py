# Copyright (c) 2026, Quad4 (quad4.io)
"""Export bundles for sharing on sneakernet or other offline transfer."""

import os
import shutil

from opip.bundle import verify_bundle
from opip.signing import has_signature, signature_path
from opip.storage import Store


class ExportError(Exception):
    pass


def export_bundle(source, output_path, store=None):
    """Copy a verified bundle to output_path for sharing.

    source: registered bundle name or path to .opip file.
    """
    store = store or Store()
    bundle_path = _resolve_source(source, store)

    errors, manifest = verify_bundle(bundle_path)
    if errors:
        raise ExportError("Bundle failed verification:\n" + "\n".join(errors))

    if not output_path.endswith(".opip"):
        output_path = output_path + ".opip"

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    shutil.copy2(bundle_path, output_path)
    if has_signature(bundle_path):
        shutil.copy2(signature_path(bundle_path), signature_path(output_path))
    return output_path, manifest


def _resolve_source(source, store):
    if os.path.isfile(source):
        return os.path.abspath(source)

    entry = store.get_bundle(source)
    if entry and os.path.isfile(entry["path"]):
        return entry["path"]

    install = store.get_install(source)
    if install and install.get("bundle_path"):
        path = install["bundle_path"]
        if os.path.isfile(path):
            return path

    raise ExportError(f"Bundle not found: {source}")
