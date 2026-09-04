"""Fetch .opip bundles from Reticulum rngit remotes (stdlib + subprocess)."""

import fnmatch
import os
import shutil
import subprocess

from opip.fetch import FetchError
from opip.remote_resolve import resolve_remote_source
from opip.sidecar import copy_sidecar_from_dir
from pip_rns.releases import (
    _normalize_remote,
    _pick_opip,
    fetch_release_bundle,
    release_info,
)


def _parse_ref(remote):
    last_slash = remote.rfind("/")
    last_at = remote.rfind("@")
    artifact = None
    if last_at > last_slash:
        ref_part = remote[last_at + 1 :]
        if ":" in ref_part:
            ref, artifact = ref_part.split(":", 1)
        else:
            ref = ref_part
        remote = remote[:last_at]
    else:
        ref = None
    return _normalize_remote(remote), ref, artifact


def _check_rns_available():
    if shutil.which("git-remote-rns") is not None:
        return
    if shutil.which("git") is None:
        raise FetchError("git is not installed. Install git to fetch bundles over RNS.")
    raise FetchError("git-remote-rns not found on PATH. Install via: pipx install rns")


def _clone_repo(remote, dest_dir, ref=None):
    _check_rns_available()
    args = ["git", "clone"]
    if ref:
        args.extend(["--branch", ref, "--depth", "1"])
    args.extend([remote, dest_dir])
    try:
        subprocess.run(args, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or "").strip()
        raise FetchError(f"RNS clone failed for {remote}: {err}")


def fetch_rns_bundle(source, dest_dir, verify_identity=None):
    """Fetch a .opip bundle from an rns:// remote.

    Supports:
      rns://id/group/repo
      rns://id/group/repo@tag
      rns://id/group/repo@tag:bundle.opip
      identity/group/repo (normalized to rns://)
      pip-rns alias names (resolved via PIP_RNS_CONFIG)
    """
    source = resolve_remote_source(source)
    remote, ref, artifact = _parse_ref(source)
    os.makedirs(dest_dir, exist_ok=True)

    if ref and shutil.which("rngit"):
        try:
            info = release_info(remote, ref)
            picked = _pick_opip(info.get("artifacts", []), artifact)
            if picked:
                bundle_path = fetch_release_bundle(
                    remote,
                    ref,
                    picked,
                    verify_identity=verify_identity,
                )
                return bundle_path.path
        except (RuntimeError, ValueError) as exc:
            raise FetchError(str(exc)) from exc

    clone_dir = os.path.join(dest_dir, "rns-clone")
    _clone_repo(
        remote,
        clone_dir,
        ref=ref if ref and not shutil.which("rngit") else None,
    )
    for root, _dirs, files in os.walk(clone_dir):
        for name in sorted(files):
            if name.endswith(".opip"):
                if (
                    artifact
                    and name != artifact
                    and not fnmatch.fnmatch(name, artifact)
                ):
                    continue
                bundle_path = os.path.join(root, name)
                copy_sidecar_from_dir(bundle_path, root)
                return bundle_path

    raise FetchError(f"No .opip bundle found at {remote}")
