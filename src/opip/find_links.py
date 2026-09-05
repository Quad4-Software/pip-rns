# Copyright (c) 2026, Quad4 (quad4.io)
"""Local wheel directory discovery for air-gap create."""

from __future__ import annotations

import glob
import os

from opip.integrity import file_hash
from opip.resolver import normalize_name
from opip.wheel import parse_wheel_filename, pick_best_wheel, read_wheel_metadata


def list_find_links_dirs(find_links):
    """Normalize find-links to a list of existing directories."""
    if not find_links:
        return []
    if isinstance(find_links, str):
        find_links = [find_links]
    dirs = []
    for item in find_links:
        path = os.path.abspath(os.path.expanduser(item))
        if os.path.isdir(path):
            dirs.append(path)
    return dirs


def scan_wheels(find_links):
    """Return list of local wheel candidate dicts.

    Each entry: filename, path, name, version, digests, url (file://), parsed tags.
    """
    candidates = []
    for directory in list_find_links_dirs(find_links):
        pattern = os.path.join(directory, "*.whl")
        for path in sorted(glob.glob(pattern)):
            filename = os.path.basename(path)
            parsed = parse_wheel_filename(filename)
            if not parsed:
                continue
            try:
                meta = read_wheel_metadata(path)
                name = normalize_name(meta["name"])
                version = meta["version"]
            except Exception:
                name = normalize_name(parsed.get("name") or "")
                version = parsed.get("version") or ""
            digest = file_hash(path)
            entry = dict(parsed)
            entry.update(
                {
                    "filename": filename,
                    "path": path,
                    "name": name,
                    "package": name,
                    "version": version,
                    "url": "file://" + path,
                    "digests": {"sha256": digest},
                    "requires_dist": [],
                    "_local": True,
                },
            )
            candidates.append(entry)
    return candidates


def pick_local_wheel(candidates, req_info, py_version, platform_tag):
    """Pick best matching local wheel for a requirement."""
    from opip.resolver import version_matches

    name = req_info["name"]
    spec = req_info.get("spec") or ""
    matching = []
    for c in candidates:
        if normalize_name(c.get("name") or c.get("package") or "") != name:
            continue
        version = c.get("version") or ""
        if spec and not version_matches(version, spec):
            continue
        matching.append(c)
    if not matching:
        return None
    return pick_best_wheel(matching, py_version, platform_tag)


def specs_from_pins(
    pins,
    find_links,
    py_version,
    platform_tag,
    offline=False,
    index_url=None,
):
    """Build wheel specs from exact name==version pins using find-links and/or index.

    pins: list of {"name", "version", "sha256"?} or requirement strings name==ver
    """
    from opip.resolver import (
        ResolutionError,
        fetch_pypi_json,
        parse_requirement,
        select_wheel_url,
    )

    candidates = scan_wheels(find_links)
    specs = []
    missing = []

    for pin in pins:
        if isinstance(pin, str):
            info = parse_requirement(pin)
            if not info:
                continue
            name = info["name"]
            version = None
            sha = None
            if info["spec"].startswith("=="):
                version = info["spec"][2:].strip()
            req_info = {
                "name": name,
                "spec": f"=={version}" if version else info["spec"],
            }
        else:
            name = normalize_name(pin["name"])
            version = pin.get("version")
            sha = pin.get("sha256")
            req_info = {"name": name, "spec": f"=={version}" if version else ""}

        local = pick_local_wheel(candidates, req_info, py_version, platform_tag)
        if local:
            if sha and local["digests"].get("sha256") != sha:
                raise ResolutionError(
                    "Hash mismatch for local wheel {}: expected {}, got {}".format(
                        local["filename"],
                        sha[:16],
                        local["digests"]["sha256"][:16],
                    ),
                )
            specs.append(local)
            continue

        if offline:
            missing.append(f"{name}=={version}" if version else name)
            continue

        try:
            pypi_data = fetch_pypi_json(name, index_url=index_url)
            wheel = select_wheel_url(pypi_data, req_info, py_version, platform_tag)
        except ResolutionError as exc:
            missing.append(str(exc))
            continue
        if sha:
            digests = wheel.setdefault("digests", {})
            if digests.get("sha256") and digests["sha256"] != sha:
                raise ResolutionError(
                    "Hash mismatch for {}: lock {}, index {}".format(
                        name,
                        sha[:16],
                        digests["sha256"][:16],
                    ),
                )
            digests["sha256"] = sha
        specs.append(wheel)

    if missing:
        raise ResolutionError(
            "Could not locate wheels (offline={}):\n  {}".format(
                offline,
                "\n  ".join(missing),
            ),
        )
    return specs
