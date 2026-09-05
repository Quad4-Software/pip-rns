# Copyright (c) 2026, Quad4 (quad4.io)
"""SHA-256 integrity computation and verification for bundles."""

import hashlib
import json
import os

ALGORITHM = "sha256"
CHUNK_SIZE = 65536


def file_hash(path):
    """Return hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def data_hash(data):
    """Return hex SHA-256 digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def build_integrity(file_paths, base_dir=None):
    """Build integrity manifest mapping relative paths to hashes.

    file_paths: iterable of absolute or relative file paths inside the bundle.
    base_dir: root used to compute relative paths.
    """
    entries = {}
    for path in sorted(file_paths):
        abs_path = os.path.abspath(path)
        if base_dir:
            rel = os.path.relpath(abs_path, base_dir).replace("\\", "/")
        else:
            rel = os.path.basename(abs_path)
        entries[rel] = file_hash(abs_path)
    return {"algorithm": ALGORITHM, "files": entries}


def dump_integrity(integrity):
    return json.dumps(integrity, indent=2, sort_keys=True) + "\n"


def load_integrity(data):
    if isinstance(data, str):
        data = json.loads(data)
    if data.get("algorithm") != ALGORITHM:
        raise ValueError("Unsupported hash algorithm: {}".format(data.get("algorithm")))
    return data


def _resolve_integrity_path(base_dir, rel_path):
    """Resolve rel_path under base_dir or return an error string."""
    if not rel_path or not isinstance(rel_path, str):
        return None, f"Invalid integrity path: {rel_path}"
    normalized = rel_path.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
        return None, f"Absolute integrity path rejected: {rel_path}"
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None, f"Path traversal in integrity entry: {rel_path}"
    if not parts:
        return None, f"Empty integrity path: {rel_path}"
    base = os.path.abspath(base_dir)
    full = os.path.abspath(os.path.join(base, *parts))
    try:
        common = os.path.commonpath([base, full])
    except ValueError:
        return None, f"Integrity path escapes base: {rel_path}"
    if common != base:
        return None, f"Integrity path escapes base: {rel_path}"
    return full, None


def verify_integrity(base_dir, integrity, all_files=None):
    """Verify files listed in integrity exist and match.

    If all_files is provided (absolute paths under base_dir), also fail when
    disk contains files not listed in the integrity manifest.
    """
    errors = []
    listed = set()
    for rel_path, expected in integrity.get("files", {}).items():
        full, path_err = _resolve_integrity_path(base_dir, rel_path)
        if path_err:
            errors.append(path_err)
            continue
        listed.add(os.path.relpath(full, base_dir).replace("\\", "/"))
        if not expected:
            errors.append(f"Empty hash for {rel_path}")
            continue
        if not os.path.isfile(full):
            errors.append(f"Missing file: {rel_path}")
            continue
        actual = file_hash(full)
        if actual != expected:
            errors.append(
                f"Hash mismatch for {rel_path}:"
                f" expected {expected[:16]}, got {actual[:16]}",
            )

    if all_files is not None:
        for full in all_files:
            rel = os.path.relpath(full, base_dir).replace("\\", "/")
            if rel not in listed:
                errors.append(f"Unlisted file present: {rel}")

    return errors


def collect_files(directory, exclude=None):
    """Recursively collect all file paths under directory."""
    exclude = set(exclude or [])
    result = []
    for root, _dirs, files in os.walk(directory):
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, directory).replace("\\", "/")
            if rel in exclude:
                continue
            result.append(full)
    return result
