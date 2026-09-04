"""Safe zip extraction with Zip Slip and zip-bomb guards."""

import contextlib
import os
import stat
import zipfile

MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
CHUNK_SIZE = 65536


class UnsafeZipError(Exception):
    pass


def safe_member_path(dest_dir, member_name):
    """Resolve member_name under dest_dir or raise UnsafeZipError.

    Rejects absolute paths, drive letters, and .. segments.
    """
    if not member_name or member_name.endswith("/"):
        return None

    if "\x00" in member_name:
        raise UnsafeZipError(f"NUL in zip member path rejected: {member_name!r}")

    name = member_name.replace("\\", "/")
    if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        raise UnsafeZipError(f"Absolute zip member path rejected: {member_name}")

    parts = [p for p in name.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise UnsafeZipError(f"Path traversal in zip member: {member_name}")
    if not parts:
        return None

    dest_root = os.path.abspath(dest_dir)
    dest = os.path.abspath(os.path.join(dest_root, *parts))
    try:
        common = os.path.commonpath([dest_root, dest])
    except ValueError:
        raise UnsafeZipError(f"Zip member escapes destination: {member_name}")
    if common != dest_root:
        raise UnsafeZipError(f"Zip member escapes destination: {member_name}")
    return dest


def _is_symlink_member(info):
    """Return True if ZipInfo looks like a symlink (Unix external attrs)."""
    if not hasattr(info, "external_attr"):
        return False
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def extract_zip_safe(
    zip_path,
    dest_dir,
    max_member_bytes=MAX_MEMBER_BYTES,
    max_total_bytes=MAX_TOTAL_BYTES,
):
    """Extract zip_path into dest_dir with path and size checks.

    Raises UnsafeZipError on traversal, symlinks, or size limits.
    """
    os.makedirs(dest_dir, exist_ok=True)
    dest_root = os.path.abspath(dest_dir)
    total = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir() or info.filename.endswith("/"):
                continue
            if _is_symlink_member(info):
                raise UnsafeZipError(f"Symlink zip member rejected: {info.filename}")
            if info.file_size > max_member_bytes:
                raise UnsafeZipError(
                    f"Zip member too large ({info.file_size} bytes): {info.filename}",
                )
            total += info.file_size
            if total > max_total_bytes:
                raise UnsafeZipError(
                    f"Zip total uncompressed size exceeds limit ({max_total_bytes} bytes)",
                )

            dest = safe_member_path(dest_root, info.filename)
            if dest is None:
                continue

            parent = os.path.dirname(dest)
            if parent:
                try:
                    os.makedirs(parent, exist_ok=True)
                except OSError as exc:
                    raise UnsafeZipError(
                        f"Cannot create parent for zip member {info.filename}: {exc}",
                    )

            if os.path.isdir(dest):
                raise UnsafeZipError(
                    f"Zip member path is an existing directory: {info.filename}",
                )
            if os.path.lexists(dest) and os.path.islink(dest):
                raise UnsafeZipError(
                    f"Refusing to overwrite symlink at zip member path: {info.filename}",
                )

            written = 0
            try:
                with open(dest, "wb") as out:
                    with zf.open(info, "r") as src:
                        while True:
                            chunk = src.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            written += len(chunk)
                            if written > max_member_bytes:
                                with contextlib.suppress(OSError):
                                    os.remove(dest)
                                raise UnsafeZipError(
                                    f"Zip member exceeded size limit while reading: {info.filename}",
                                )
                            out.write(chunk)
            except OSError as exc:
                raise UnsafeZipError(
                    f"Cannot open zip member destination {info.filename}: {exc}",
                ) from exc


def safe_artifact_name(filename):
    """Return a basename-only artifact name or raise ValueError.

    Rejects empty names, path separators, and .. components.
    """
    if filename is None:
        raise ValueError("Empty artifact filename")
    name = str(filename).strip()
    if not name:
        raise ValueError("Empty artifact filename")
    if "/" in name or "\\" in name:
        raise ValueError(
            f"Artifact filename must not contain path separators: {filename}",
        )
    base = os.path.basename(name)
    if base != name or base in (".", "..") or ".." in base:
        raise ValueError(f"Unsafe artifact filename: {filename}")
    return base


def contain_path(root_dir, rel_path):
    """Join rel_path under root_dir and ensure the result stays inside root_dir.

    Raises ValueError on escape.
    """
    if rel_path is None or str(rel_path).strip() == "":
        raise ValueError("Empty relative path")
    if "\x00" in str(rel_path):
        raise ValueError(f"NUL in path rejected: {rel_path!r}")
    root = os.path.abspath(root_dir)
    normalized = str(rel_path).replace("\\", "/")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError(f"Path escapes root: {rel_path}")
    if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
        raise ValueError(f"Absolute path rejected: {rel_path}")
    target = os.path.abspath(os.path.join(root, *parts))
    try:
        common = os.path.commonpath([root, target])
    except ValueError:
        raise ValueError(f"Path escapes root: {rel_path}")
    if common != root:
        raise ValueError(f"Path escapes root: {rel_path}")
    return target
