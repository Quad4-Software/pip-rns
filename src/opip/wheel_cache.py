"""Shared wheel cache to avoid re-downloading identical wheels across bundles."""

import os
import shutil

from opip.integrity import file_hash
from opip.safe_zip import safe_artifact_name
from opip.storage import default_cache_dir


def wheel_cache_dir():
    path = os.path.join(default_cache_dir(), "wheels")
    os.makedirs(path, exist_ok=True)
    return path


def cache_path(filename, expected_hash=None):
    base = wheel_cache_dir()
    safe_name = safe_artifact_name(filename)
    if expected_hash:
        return os.path.join(base, "{0}-{1}".format(expected_hash[:16], safe_name))
    return os.path.join(base, safe_name)


def lookup_wheel(filename, expected_hash=None):
    """Return cached wheel path if present and hash matches."""
    path = cache_path(filename, expected_hash)
    if not os.path.isfile(path):
        path = cache_path(filename, None)
    if not os.path.isfile(path):
        return None
    if expected_hash and file_hash(path) != expected_hash:
        return None
    return path


def store_wheel(wheel_path, filename=None, expected_hash=None):
    """Copy a wheel into the shared cache."""
    filename = safe_artifact_name(filename or os.path.basename(wheel_path))
    digest = expected_hash or file_hash(wheel_path)
    dest = cache_path(filename, digest)
    if not os.path.isfile(dest):
        shutil.copy2(wheel_path, dest)
    return dest
