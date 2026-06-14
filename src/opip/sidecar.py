"""Fetch .rsg signature sidecars alongside .opip bundles."""

import os
import shutil

from opip.fetch import FetchError, fetch_file
from opip.signing import signature_path


def copy_sidecar_from_dir(bundle_path, directory):
    """Copy a matching .rsg sidecar from directory when present."""
    sidecar_name = os.path.basename(signature_path(bundle_path))
    candidate = os.path.join(directory, sidecar_name)
    if os.path.isfile(candidate):
        shutil.copy2(candidate, signature_path(bundle_path))


def fetch_sidecar_if_available(bundle_path, source_url=None, timeout=120):
    """Best-effort fetch of a .rsg sidecar for a downloaded bundle."""
    dest = signature_path(bundle_path)
    if os.path.isfile(dest):
        return
    if not source_url:
        return
    if source_url.startswith(("http://", "https://", "ftp://")):
        sidecar_url = source_url + ".rsg"
        try:
            fetch_file(sidecar_url, dest, timeout=timeout)
        except FetchError:
            pass
