"""Release artifact downloader via RNS page node.

Downloads artifacts by shelling out to scripts/download_artifact.py
with a system Python (outside any virtualenv), avoiding pipx/RNS issues.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional


def _find_system_python() -> str:
    """Find a Python executable outside any virtualenv/venv."""
    if hasattr(sys, "base_exec_prefix") and sys.prefix != sys.base_exec_prefix:
        base = sys.base_exec_prefix
        for name in ("python3", "python"):
            candidate = Path(base) / "bin" / name
            if candidate.exists():
                return str(candidate)

    for name in ("python3", "python"):
        try:
            result = subprocess.run(
                [name, "-c", "import RNS; print('ok')"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and "ok" in result.stdout:
                return name
        except Exception:
            continue

    return sys.executable


def _script_path() -> Path:
    """Locate download_artifact.py relative to this file."""
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent.parent / "scripts" / "download_artifact.py",
        here.parent / "scripts" / "download_artifact.py",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


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
        msg = f"rngit release view failed: {result.stderr.strip()}"
        raise RuntimeError(msg)
    return _parse_release_view(result.stdout)


def _parse_release_view(text: str) -> dict:
    info: dict = {}
    artifacts: list[dict] = []
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
        msg = f"rngit release list failed: {result.stderr.strip()}"
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


def _pick_whl(artifacts: list[dict]) -> Optional[str]:
    whls = [a["name"] for a in artifacts if a["name"].endswith(".whl") and not a["name"].endswith(".rsg")]
    if not whls:
        return None
    if len(whls) == 1:
        return whls[0]
    preferred = [w for w in whls if "none-any" in w]
    if preferred:
        return preferred[0]
    return whls[0]


def download_artifact(
    dest_hash: bytes,
    group: str,
    repo: str,
    tag: str,
    artifact: str,
    page_node_hash: bytes | None = None,
) -> str:
    """Download a release artifact via the standalone download_artifact.py script."""
    out_path = f"/tmp/{artifact}"
    script = _script_path()

    args = [
        _find_system_python(),
        str(script),
        dest_hash.hex(),
        group,
        repo,
        tag,
        artifact,
    ]
    if page_node_hash:
        args.append(page_node_hash.hex())
    args.append(out_path)

    result = subprocess.run(args, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        msg = f"Download failed: {err[:200]}"
        raise RuntimeError(msg)

    if not os.path.isfile(out_path):
        msg = "Download failed: output file not created"
        raise RuntimeError(msg)

    return out_path
