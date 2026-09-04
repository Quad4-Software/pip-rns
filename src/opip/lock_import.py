"""Import pins from uv.lock, poetry.lock, and pip-tools hashed requirements."""

from __future__ import annotations

import os
import re


class LockImportError(Exception):
    pass


def detect_lockfile(project_dir):
    """Return path to a lockfile in project_dir, or None."""
    for name in ("uv.lock", "poetry.lock"):
        path = os.path.join(project_dir, name)
        if os.path.isfile(path):
            return path
    for name in ("requirements.lock", "requirements-lock.txt"):
        path = os.path.join(project_dir, name)
        if os.path.isfile(path):
            return path
    return None


def load_lockfile(path):
    """Load lockfile pins.

    Returns list of dicts: {name, version, sha256?}
    """
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise LockImportError(f"Lockfile not found: {path}")
    base = os.path.basename(path).lower()
    if base == "uv.lock":
        return _parse_uv_lock(path)
    if base == "poetry.lock":
        return _parse_poetry_lock(path)
    return _parse_pip_tools(path)


def _parse_poetry_lock(path):
    text = open(path, encoding="utf-8").read()
    if not text.startswith("[[package]]"):
        text = "\n" + text
    pins = []
    blocks = re.split(
        r"\n\[\[package\]\]\n",
        "\n" + text if not text.startswith("\n") else text,
    )
    # Also handle [[package]] at start
    if text.lstrip().startswith("[[package]]"):
        blocks = re.split(r"\[\[package\]\]\s*\n", text)
    for block in blocks[1:]:
        name = _toml_str(block, "name")
        version = _toml_str(block, "version")
        if not name or not version:
            continue
        sha = None
        files_block = _toml_array_table(block, "files")
        if files_block:
            match = re.search(
                r'hash\s*=\s*["\']sha256:([0-9a-fA-F]+)["\']',
                files_block,
            )
            if match:
                sha = match.group(1).lower()
        if sha is None:
            match = re.search(r'hash\s*=\s*["\']sha256:([0-9a-fA-F]+)["\']', block)
            if match:
                sha = match.group(1).lower()
        pins.append({"name": name, "version": version, "sha256": sha})
    if not pins:
        raise LockImportError(f"No packages found in poetry.lock: {path}")
    return pins


def _parse_uv_lock(path):
    """Minimal uv.lock reader (TOML package tables)."""
    text = open(path, encoding="utf-8").read()
    pins = []
    blocks = re.split(r"\[\[package\]\]\s*\n", text)
    for block in blocks[1:]:
        name = _toml_str(block, "name")
        version = _toml_str(block, "version")
        if not name or not version:
            continue
        source = _toml_table(block, "source")
        if source and "editable" in source:
            continue
        sha = None
        for match in re.finditer(r'hash\s*=\s*["\']sha256:([0-9a-fA-F]+)["\']', block):
            sha = match.group(1).lower()
            break
        pins.append({"name": name, "version": version, "sha256": sha})
    if not pins:
        raise LockImportError(f"No packages found in uv.lock: {path}")
    return pins


def _parse_pip_tools(path):
    """Parse requirements with optional --hash=sha256:... lines."""
    pins = []
    current = None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("--hash="):
                if current is not None:
                    algo_hash = line[len("--hash=") :]
                    if algo_hash.startswith("sha256:"):
                        current["sha256"] = algo_hash.split(":", 1)[1].lower()
                continue
            if line.startswith("-"):
                continue
            # name==version \
            line = line.rstrip("\\").strip()
            match = re.match(r"^([A-Za-z0-9_.-]+)\s*==\s*([^\s\\;]+)", line)
            if not match:
                continue
            current = {
                "name": match.group(1),
                "version": match.group(2),
                "sha256": None,
            }
            pins.append(current)
    if not pins:
        raise LockImportError(f"No pinned packages in {path}")
    return pins


def _toml_str(block, key):
    match = re.search(
        rf'^{re.escape(key)}\s*=\s*["\']([^"\']+)["\']',
        block,
        re.MULTILINE,
    )
    return match.group(1) if match else None


def _toml_table(block, key):
    match = re.search(
        rf"^{re.escape(key)}\s*=\s*\{{([^}}]*)\}}",
        block,
        re.MULTILINE,
    )
    return match.group(1) if match else None


def _toml_array_table(block, key):
    # poetry [[package.files]] style inside package block as files = [...]
    match = re.search(
        rf"^{re.escape(key)}\s*=\s*\[(.*?)\]",
        block,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else None
