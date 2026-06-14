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
    """
    Build integrity manifest mapping relative paths to hashes.

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
        raise ValueError(
            "Unsupported hash algorithm: {0}".format(data.get("algorithm"))
        )
    return data


def verify_integrity(base_dir, integrity):
    """Verify all files listed in integrity manifest exist and match."""
    errors = []
    for rel_path, expected in integrity.get("files", {}).items():
        full = os.path.join(base_dir, rel_path.replace("/", os.sep))
        if not os.path.isfile(full):
            errors.append("Missing file: {0}".format(rel_path))
            continue
        actual = file_hash(full)
        if actual != expected:
            errors.append(
                "Hash mismatch for {0}: expected {1}, got {2}".format(
                    rel_path, expected[:16], actual[:16]
                )
            )
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
