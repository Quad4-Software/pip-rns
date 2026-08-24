"""Fetch bundles from git, HTTP, FTP, RNS, and local paths."""

import os
import shutil
import tempfile

from opip.fetch import FetchError, fetch_file, fetch_git
from opip.manifest import BUNDLE_EXTENSION
from opip.remote_resolve import resolve_remote_source
from opip.rns_fetch import fetch_rns_bundle
from opip.sidecar import copy_sidecar_from_dir, fetch_sidecar_if_available


def is_rns_source(source):
    if source.startswith("rns://"):
        return True
    if "://" in source:
        return False
    parts = source.strip("/").split("/")
    return len(parts) >= 3 and all(parts)


def is_git_source(source):
    return (
        source.startswith("git+")
        or source.startswith("git://")
        or source.endswith(".git")
        or "github.com" in source
        and "#" in source
        and BUNDLE_EXTENSION in source
    )


def parse_git_source(source):
    """
    Parse git-style sources.

    Formats:
      git+https://host/repo.git#ref:path/to/bundle.opip
      git+https://host/repo.git@ref:subpath/bundle.opip
      https://host/repo.git (entire repo, find .opip)
    """
    ref = None
    subpath = None
    url = source

    if source.startswith("git+"):
        url = source[4:]

    if "#" in url:
        url, fragment = url.split("#", 1)
        if ":" in fragment:
            ref, subpath = fragment.split(":", 1)
        else:
            subpath = fragment
    elif "@" in url and not url.startswith("git@"):
        base, maybe_ref = url.rsplit("@", 1)
        if "/" not in maybe_ref and "." not in maybe_ref:
            url = base
            ref = maybe_ref

    return url, ref, subpath


def acquire_bundle(source, dest_dir=None, timeout=300, verify_identity=None):
    """
    Download or locate a bundle file from any supported source.

    Returns absolute path to the .opip bundle file.
    """
    dest_dir = dest_dir or tempfile.mkdtemp(prefix="opip-acquire-")
    os.makedirs(dest_dir, exist_ok=True)

    if os.path.isfile(source) and source.endswith(BUNDLE_EXTENSION):
        return os.path.abspath(source)

    if source.endswith(BUNDLE_EXTENSION) and os.path.isfile(source):
        return os.path.abspath(source)

    source = resolve_remote_source(source)

    git_cleanup = None
    try:
        if is_rns_source(source):
            return fetch_rns_bundle(source, dest_dir, verify_identity=verify_identity)

        if is_git_source(source) or source.startswith("git+"):
            url, ref, subpath = parse_git_source(source)
            target, git_cleanup = fetch_git(url, dest_dir, ref=ref, subpath=subpath)
            if os.path.isfile(target) and target.endswith(BUNDLE_EXTENSION):
                copy_sidecar_from_dir(target, os.path.dirname(target))
                return os.path.abspath(target)
            bundle = find_bundle_in_dir(target)
            if bundle:
                copy_sidecar_from_dir(bundle, os.path.dirname(bundle))
                return bundle
            raise FetchError(f"No {BUNDLE_EXTENSION} bundle found in git repository")

        basename = os.path.basename(source.split("?")[0].split("#")[0])
        if not basename.endswith(BUNDLE_EXTENSION):
            basename = f"bundle{BUNDLE_EXTENSION}"
        dest = os.path.join(dest_dir, basename)
        fetch_file(source, dest, timeout=timeout)
        fetch_sidecar_if_available(dest, source_url=source, timeout=timeout)
        return os.path.abspath(dest)

    except FetchError:
        if git_cleanup:
            shutil.rmtree(git_cleanup, ignore_errors=True)
        raise


def find_bundle_in_dir(directory):
    """Find first .opip file in directory tree."""
    for root, _dirs, files in os.walk(directory):
        for name in sorted(files):
            if name.endswith(BUNDLE_EXTENSION):
                return os.path.join(root, name)
    return None
