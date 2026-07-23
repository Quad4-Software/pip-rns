"""Wheel file parsing without external dependencies."""

import os
import re
import zipfile


WHEEL_FILENAME_RE = re.compile(
    r"^(?P<name>[^-]+)-(?P<version>[^-]+)"
    r"(?:-(?P<build>\d[^-]*))?"
    r"-(?P<pyver>[^-]+)-(?P<abi>[^-]+)-(?P<plat>[^-]+)\.whl$",
    re.IGNORECASE,
)


def parse_wheel_filename(filename):
    """Parse wheel filename into components. Returns dict or None."""
    base = os.path.basename(filename)
    m = WHEEL_FILENAME_RE.match(base)
    if not m:
        return None
    return {
        "filename": base,
        "name": m.group("name").replace("_", "-").lower(),
        "version": m.group("version"),
        "build": m.group("build"),
        "pyver": m.group("pyver"),
        "abi": m.group("abi"),
        "plat": m.group("plat"),
    }


def read_wheel_metadata(wheel_path):
    """Extract name, version, requires-dist from a wheel file."""
    info = parse_wheel_filename(wheel_path)
    if info is None:
        raise ValueError("Invalid wheel filename: {0}".format(wheel_path))

    requires_dist = []
    with zipfile.ZipFile(wheel_path, "r") as zf:
        metadata_name = None
        for name in zf.namelist():
            if name.endswith(".dist-info/METADATA"):
                metadata_name = name
                break
            if name.endswith(".dist-info/WHEEL"):
                continue
        if metadata_name:
            raw = zf.read(metadata_name).decode("utf-8", errors="replace")
            for line in raw.splitlines():
                if line.startswith("Requires-Dist:"):
                    dep = line.split(":", 1)[1].strip()
                    requires_dist.append(dep)
                elif line.startswith("Name:"):
                    info["name"] = line.split(":", 1)[1].strip().lower()
                elif line.startswith("Version:"):
                    info["version"] = line.split(":", 1)[1].strip()

    info["requires_dist"] = requires_dist
    return info


def _python_tag(version):
    major, minor = version.split(".")[:2]
    return "cp{0}{1}".format(major, minor)


def _cp_tag_number(tag):
    match = re.match(r"^cp(\d+)$", tag)
    if not match:
        return None
    return int(match.group(1))


def _pyver_matches(wheel_py, py_version, abi):
    major, minor = py_version.split(".")[:2]
    universal = {
        "py{0}{1}".format(major, minor),
        "py{0}".format(major),
        "py2.py3",
        "py3",
        "py2",
        _python_tag(py_version),
    }
    if wheel_py in universal:
        return True
    if any(tag in wheel_py.split(".") for tag in universal):
        return True
    if "abi3" in abi and wheel_py.startswith("cp"):
        wheel_num = _cp_tag_number(wheel_py)
        target_num = _cp_tag_number(_python_tag(py_version))
        if wheel_num is not None and target_num is not None:
            return wheel_num <= target_num
    if wheel_py.startswith("cp"):
        return wheel_py == _python_tag(py_version)
    return False


def _abi_matches(abi, py_version):
    if abi in ("none", "any"):
        return True
    if "abi3" in abi:
        return True
    target = _python_tag(py_version)
    if abi == target or abi.startswith(target + "-"):
        return True
    return False


def _arch_tokens(tag):
    t = tag.lower()
    tokens = set()
    if "x86_64" in t or "amd64" in t:
        tokens.add("x86_64")
    if "aarch64" in t or "arm64" in t:
        tokens.add("aarch64")
    if "i686" in t or t.endswith("win32"):
        tokens.add("i686")
    return tokens


def _plat_family(tag):
    t = tag.lower()
    if t == "any":
        return "any"
    if t.startswith("win"):
        return "win"
    if t.startswith("macosx"):
        return "macosx"
    if t.startswith("manylinux") or t.startswith("musllinux") or t.startswith("linux"):
        return "linux"
    if t.startswith("freebsd"):
        return "freebsd"
    return "other"


def _plat_compatible(wheel_plat, target_plat):
    if wheel_plat == "any" or target_plat == "any":
        return True
    if wheel_plat == target_plat:
        return True

    tags = wheel_plat.split(".")
    if target_plat in tags:
        return True

    target_family = _plat_family(target_plat)
    target_arch = _arch_tokens(target_plat)

    for tag in tags:
        if tag == target_plat:
            return True
        if _plat_family(tag) != target_family and target_family != "any":
            continue
        if not target_arch:
            if target_family == _plat_family(tag):
                return True
            continue
        if target_arch & _arch_tokens(tag):
            return True
    return False


def wheel_matches_platform(wheel_info, py_version, platform_tag):
    """
    Check if a wheel is compatible with the target Python and platform.

    py_version: e.g. '3.8'
    platform_tag: e.g. 'win_amd64' or 'any'
    """
    wheel_py = wheel_info.get("pyver", "")
    abi = wheel_info.get("abi", "none")
    py_ok = _pyver_matches(wheel_py, py_version, abi)

    plat = wheel_info.get("plat", "any")
    plat_ok = _plat_compatible(plat, platform_tag)
    abi_ok = _abi_matches(abi, py_version)
    return py_ok and plat_ok and abi_ok


def pick_best_wheel(candidates, py_version, platform_tag):
    """Select the best matching wheel from a list of wheel info dicts."""
    compatible = [
        w for w in candidates if wheel_matches_platform(w, py_version, platform_tag)
    ]
    if not compatible:
        return None

    # Prefer exact platform match, then none-any, then first
    def sort_key(w):
        plat = w.get("plat", "any")
        exact = 0 if plat == platform_tag or platform_tag in plat.split(".") else 1
        arch = 0 if _arch_tokens(platform_tag) & _arch_tokens(plat.split(".")[0]) else 1
        any_plat = 0 if plat == "any" else 1
        return (exact, arch, any_plat, w.get("filename", ""))

    compatible.sort(key=sort_key)
    return compatible[0]
