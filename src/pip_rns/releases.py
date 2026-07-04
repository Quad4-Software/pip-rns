"""Release metadata and artifact downloads via rngit."""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


def _parse_rns_url(url: str) -> tuple[bytes, str, str]:
    url = url.strip()
    if not url.lower().startswith("rns://"):
        url = "rns://" + url
    parts = url[6:].split("/")
    if len(parts) != 3:
        msg = f"Invalid URL components: {url}"
        raise ValueError(msg)
    try:
        dest_hash = bytes.fromhex(parts[0])
    except Exception as e:
        msg = f"Invalid destination hash: {e}"
        raise ValueError(msg)
    return dest_hash, parts[1], parts[2]


def _normalize_remote(remote: str) -> str:
    remote = remote.strip()
    if not remote.lower().startswith("rns://"):
        return "rns://" + remote
    return remote


def release_info(remote: str, tag: str) -> dict:
    """Get release info via rngit release view (subprocess)."""
    remote = _normalize_remote(remote)
    cmd = ["rngit", "release", remote, "view", tag]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        msg = f"rngit release view failed: {result.stderr.strip() or result.stdout.strip()}"
        raise RuntimeError(msg)
    return _parse_release_view(result.stdout)


def _parse_release_view(text: str) -> dict:
    info: dict = {}
    artifacts: list[dict[str, str]] = []
    in_artifacts = False
    for line in text.splitlines():
        if line.startswith("Release :"):
            info["tag"] = line.split(":", 1)[1].strip()
        elif line.startswith("Status  :"):
            info["status"] = line.split(":", 1)[1].strip()
        elif line.startswith("Artifacts"):
            in_artifacts = True
            continue
        elif in_artifacts and line.startswith(" - "):
            m = re.match(r" - (.+) \(([0-9.]+) (B|KB|MB|GB)\)", line)
            if m:
                artifacts.append({"name": m.group(1).strip(), "size": m.group(2) + " " + m.group(3)})
        elif in_artifacts and line.startswith("="):
            continue
    info["artifacts"] = artifacts
    return info


def list_releases(remote: str) -> list[dict]:
    """List releases via rngit release list (subprocess)."""
    remote = _normalize_remote(remote)
    cmd = ["rngit", "release", remote, "list"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        msg = f"rngit release list failed: {result.stderr.strip() or result.stdout.strip()}"
        raise RuntimeError(msg)
    return _parse_release_list(result.stdout)


def _parse_release_list(text: str) -> list[dict]:
    releases: list[dict] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0] != "Tag":
            releases.append({
                "tag": parts[0],
                "status": parts[1],
                "created": parts[2] + " " + parts[3],
            })
    return releases


def _pick_whl(artifacts: list[dict[str, str]]) -> Optional[str]:
    whls = [a["name"] for a in artifacts if a["name"].endswith(".whl") and not a["name"].endswith(".rsg")]
    if not whls:
        return None
    if len(whls) == 1:
        return whls[0]
    preferred = [w for w in whls if "none-any" in w]
    if preferred:
        return preferred[0]
    return whls[0]


def _pick_opip(artifacts: list[dict[str, str]], pattern: str | None = None) -> Optional[str]:
    names = [a["name"] for a in artifacts if a["name"].endswith(".opip")]
    if not names:
        return None
    if pattern:
        matches = [n for n in names if fnmatch.fnmatch(n, pattern)]
        if matches:
            return matches[0]
        if pattern in names:
            return pattern
        msg = f"No .opip artifact matching {pattern} in release"
        raise ValueError(msg)
    if len(names) == 1:
        return names[0]
    return sorted(names)[0]


def _rsg_name_for_artifact(artifact: str) -> str:
    return f"{artifact}.rsg"


def _copy_sidecar_if_present(
    remote: str,
    tag: str,
    artifact: str,
    bundle_path: str,
    *,
    verify_identity: str | None = None,
) -> None:
    rsg_dest = f"{bundle_path}.rsg"
    if os.path.isfile(rsg_dest):
        return
    rsg_artifact = _rsg_name_for_artifact(os.path.basename(artifact))
    try:
        info = release_info(remote, tag)
    except RuntimeError:
        return
    names = {a["name"] for a in info.get("artifacts", [])}
    if rsg_artifact not in names:
        return
    fetched = fetch_release_artifact(
        remote, tag, rsg_artifact, verify_identity=verify_identity,
    )
    if fetched != rsg_dest:
        shutil.copy2(fetched, rsg_dest)
    if fetched != bundle_path and os.path.isfile(fetched):
        try:
            os.unlink(fetched)
        except OSError:
            pass


def fetch_release_bundle(
    remote: str,
    tag: str,
    artifact: str,
    *,
    verify_identity: str | None = None,
) -> str:
    """Download a .opip bundle and its .rsg sidecar when published."""
    bundle_path = fetch_release_artifact(
        remote, tag, artifact, verify_identity=verify_identity,
    )
    _copy_sidecar_if_present(
        remote, tag, artifact, bundle_path, verify_identity=verify_identity,
    )
    return bundle_path


def _fetch_pattern(artifact: str) -> str:
    if any(c in artifact for c in "*?[]"):
        return artifact
    return artifact


def fetch_release_artifact(
    remote: str,
    tag: str,
    artifact: str,
    *,
    verify_identity: str | None = None,
) -> str:
    """Download a release artifact via rngit release fetch; returns a file path."""
    remote = _normalize_remote(remote)
    pattern = _fetch_pattern(artifact)
    target = f"{tag}:{pattern}"

    cmd = ["rngit", "release"]
    if verify_identity:
        cmd.extend(["-s", verify_identity])
    cmd.extend([remote, "fetch", target])

    workdir = tempfile.mkdtemp(prefix="pip-rns-fetch-")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=workdir, timeout=7200)
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            msg = f"rngit release fetch failed: {err[:300]}"
            raise RuntimeError(msg)

        matches = [
            p for p in Path(workdir).iterdir()
            if p.is_file() and fnmatch.fnmatch(p.name, pattern) and not p.name.endswith(".rsm")
        ]
        if not matches and not any(c in pattern for c in "*?[]"):
            exact = Path(workdir) / artifact
            if exact.is_file():
                matches = [exact]

        if not matches:
            msg = f"rngit release fetch did not produce {artifact}"
            raise RuntimeError(msg)

        src = matches[0]
        out_path = Path(tempfile.gettempdir()) / src.name
        if out_path.exists():
            out_path.unlink()
        shutil.move(str(src), str(out_path))
        return str(out_path)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
