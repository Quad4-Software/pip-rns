"""Fetch .opip bundles from Reticulum rngit remotes (stdlib + subprocess)."""

import fnmatch
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from opip.fetch import FetchError


def _normalize_remote(remote):
    remote = remote.strip()
    if not remote.lower().startswith("rns://"):
        return "rns://" + remote
    return remote


def _parse_ref(remote):
    last_slash = remote.rfind("/")
    last_at = remote.rfind("@")
    artifact = None
    if last_at > last_slash:
        ref_part = remote[last_at + 1:]
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
    raise FetchError(
        "git-remote-rns not found on PATH. Install via: pipx install rns"
    )


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
        raise FetchError("RNS clone failed for {0}: {1}".format(remote, err))


def _parse_release_view(text):
    info = {}
    artifacts = []
    in_artifacts = False
    for line in text.splitlines():
        if line.startswith("Release :"):
            info["tag"] = line.split(":", 1)[1].strip()
        elif line.startswith("Artifacts"):
            in_artifacts = True
            continue
        elif in_artifacts and line.startswith(" - "):
            match = re.match(r" - (.+) \(([0-9.]+) (B|KB|MB|GB)\)", line)
            if match:
                artifacts.append({"name": match.group(1).strip()})
        elif in_artifacts and line.startswith("="):
            continue
    info["artifacts"] = artifacts
    return info


def _pick_opip_artifact(artifacts, pattern=None):
    names = [a["name"] for a in artifacts if a["name"].endswith(".opip")]
    if not names:
        return None
    if pattern:
        matches = [n for n in names if fnmatch.fnmatch(n, pattern)]
        if matches:
            return matches[0]
        if pattern in names:
            return pattern
        raise FetchError("No .opip artifact matching {0} in release".format(pattern))
    if len(names) == 1:
        return names[0]
    return sorted(names)[0]


def _fetch_release_artifact(remote, tag, artifact):
    remote = _normalize_remote(remote)
    pattern = artifact if any(c in artifact for c in "*?[]") else artifact
    target = "{0}:{1}".format(tag, pattern)
    cmd = ["rngit", "release", remote, "fetch", target]
    workdir = tempfile.mkdtemp(prefix="opip-rns-fetch-")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=workdir, timeout=7200)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            raise FetchError("rngit release fetch failed: {0}".format(err[:300]))

        matches = [
            path for path in Path(workdir).iterdir()
            if path.is_file()
            and fnmatch.fnmatch(path.name, pattern)
            and not path.name.endswith(".rsm")
        ]
        if not matches and not any(c in pattern for c in "*?[]"):
            exact = Path(workdir) / artifact
            if exact.is_file():
                matches = [exact]
        if not matches:
            raise FetchError("rngit release fetch did not produce {0}".format(artifact))

        dest = os.path.join(tempfile.gettempdir(), matches[0].name)
        if os.path.exists(dest):
            os.remove(dest)
        shutil.move(str(matches[0]), dest)
        return dest
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def fetch_rns_bundle(source, dest_dir):
    """
    Fetch a .opip bundle from an rns:// remote.

    Supports:
      rns://id/group/repo
      rns://id/group/repo@tag
      rns://id/group/repo@tag:bundle.opip
      identity/group/repo (normalized to rns://)
    """
    remote, ref, artifact = _parse_ref(source)
    os.makedirs(dest_dir, exist_ok=True)

    if ref and shutil.which("rngit"):
        cmd = ["rngit", "release", remote, "view", ref]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            info = _parse_release_view(result.stdout)
            picked = _pick_opip_artifact(info.get("artifacts", []), artifact)
            if picked:
                return _fetch_release_artifact(remote, ref, picked)

    clone_dir = os.path.join(dest_dir, "rns-clone")
    _clone_repo(remote, clone_dir, ref=ref if ref and not shutil.which("rngit") else None)
    for root, _dirs, files in os.walk(clone_dir):
        for name in sorted(files):
            if name.endswith(".opip"):
                if artifact and name != artifact and not fnmatch.fnmatch(name, artifact):
                    continue
                return os.path.join(root, name)

    raise FetchError("No .opip bundle found at {0}".format(remote))
