"""Dependency resolution via PyPI JSON API (stdlib only)."""

import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from opip import pypi_cache
from opip.wheel import parse_wheel_filename, pick_best_wheel


PYPI_URL = "https://pypi.org/pypi/{package}/json"
PYPI_RELEASE_URL = "https://pypi.org/pypi/{package}/{version}/json"
USER_AGENT = "opip/{0} (+https://github.com/Quad4-Software/pip-rns)".format(
    __import__("opip").__version__
)

UNIVERSAL_PLATFORMS = (
    "win_amd64",
    "win32",
    "manylinux2014_x86_64",
    "manylinux2014_aarch64",
    "macosx_10_9_universal2",
    "macosx_11_0_arm64",
)

_RUNTIME_SKIP_PREFIXES = (
    "sphinx",
    "pytest",
    "mypy",
    "black",
    "flake8",
    "pylint",
    "coverage",
    "tox",
    "nose",
    "mock",
)


class ResolutionError(Exception):
    pass


def normalize_name(name):
    return name.lower().replace("_", "-").replace(".", "-")


def parse_requirement(req):
    """
    Parse a simple requirement string into name and optional version spec.

    Supports: package, package==1.0, package>=1.0, package[extra]
    """
    req = req.strip()
    if not req or req.startswith("#"):
        return None
    extras = None
    if "[" in req:
        name_part, rest = req.split("[", 1)
        extras = rest.rstrip("]").strip()
        req = name_part.strip()
    match = re.match(r"^([A-Za-z0-9_.-]+)\s*(.*)$", req)
    if not match:
        return None
    name = normalize_name(match.group(1))
    spec = match.group(2).strip()
    return {"name": name, "spec": spec, "extras": extras, "raw": req}


def version_matches(version, spec):
    """Check if version satisfies a simple spec (==, >=, <=, ~=, !=)."""
    if not spec:
        return True
    spec = spec.strip().strip("()")
    for part in spec.split(","):
        part = part.strip().strip("()")
        if part.startswith("=="):
            if version != part[2:].strip():
                return False
        elif part.startswith(">="):
            if _cmp_version(version, part[2:].strip()) < 0:
                return False
        elif part.startswith("<="):
            if _cmp_version(version, part[2:].strip()) > 0:
                return False
        elif part.startswith("!="):
            if version == part[2:].strip():
                return False
        elif part.startswith("<"):
            if _cmp_version(version, part[1:].strip()) >= 0:
                return False
        elif part.startswith(">"):
            if _cmp_version(version, part[1:].strip()) <= 0:
                return False
        elif part.startswith("~="):
            base = part[2:].strip()
            if not version.startswith(base.rsplit(".", 1)[0]):
                return False
    return True


def _cmp_version(a, b):
    """Compare two version strings. Returns -1, 0, or 1."""

    def parts(v):
        return [int(x) if x.isdigit() else x for x in re.split(r"[.\-]", v)]

    pa, pb = parts(a), parts(b)
    for i in range(max(len(pa), len(pb))):
        xa = pa[i] if i < len(pa) else 0
        xb = pb[i] if i < len(pb) else 0
        if xa == xb:
            continue
        if isinstance(xa, int) and isinstance(xb, int):
            return -1 if xa < xb else 1
        return -1 if str(xa) < str(xb) else 1
    return 0


def _fetch_url(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_pypi_json(package, timeout=60):
    """Fetch package metadata from PyPI."""
    package = normalize_name(package)
    cache_key = "pkg:" + package
    cached = pypi_cache.get(cache_key)
    if cached is not None:
        return cached

    url = PYPI_URL.format(package=package)
    try:
        data = _fetch_url(url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ResolutionError("Package not found on PyPI: {0}".format(package))
        raise ResolutionError("PyPI error for {0}: {1}".format(package, exc))

    pypi_cache.put(cache_key, data)
    return data


def fetch_release_json(package, version, timeout=60):
    """Fetch version-specific metadata from PyPI."""
    package = normalize_name(package)
    cache_key = "rel:{0}:{1}".format(package, version)
    cached = pypi_cache.get(cache_key)
    if cached is not None:
        return cached

    url = PYPI_RELEASE_URL.format(package=package, version=version)
    try:
        data = _fetch_url(url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise ResolutionError(
            "PyPI error for {0} {1}: {2}".format(package, version, exc)
        )

    if data is not None:
        pypi_cache.put(cache_key, data)
    return data


def release_requires_dist(package, version, pypi_data=None):
    """Return Requires-Dist list for a package version."""
    if pypi_data is not None:
        info = pypi_data.get("info", {})
        if info.get("version") == version:
            return info.get("requires_dist") or []

    data = fetch_release_json(package, version)
    if data is None:
        return []
    info = data.get("info", {})
    return info.get("requires_dist") or []


def _version_sort_key(version):
    parts = []
    for piece in re.split(r"[.\-_]", version):
        if not piece:
            continue
        if piece.isdigit():
            parts.append((0, int(piece)))
        else:
            parts.append((1, piece))
    return parts


def get_release_urls(pypi_data, version):
    """Return list of download URLs for a specific release version."""
    releases = pypi_data.get("releases", {})
    files = releases.get(version, [])
    return [f for f in files if f.get("packagetype") == "bdist_wheel"]


def _dep_applies(dep_string, platform_tag, py_version):
    """Return False when a Requires-Dist marker excludes the target platform."""
    if ";" not in dep_string:
        return True
    _name, marker = dep_string.split(";", 1)
    marker = marker.strip().lower()
    if "extra" in marker:
        return False
    if "sys_platform" in marker:
        win = platform_tag.startswith("win")
        linux = platform_tag.startswith(("linux", "manylinux", "musllinux"))
        mac = platform_tag.startswith("macosx")
        if 'sys_platform == "win32"' in marker or "sys_platform == 'win32'" in marker:
            return win
        if "win32" in marker and "!=" in marker:
            return not win
        if "linux" in marker and "==" in marker:
            return linux
        if "darwin" in marker and "==" in marker:
            return mac
    if "python_version" in marker:
        if ">=" in marker:
            match = re.search(r'python_version\s*>=\s*["\']([^"\']+)', marker)
            if match and _cmp_version(py_version, match.group(1)) < 0:
                return False
        if "<" in marker:
            match = re.search(r'python_version\s*<\s*["\']([^"\']+)', marker)
            if match and _cmp_version(py_version, match.group(1)) >= 0:
                return False
    return True


def _skip_runtime_dep(name, is_top):
    if is_top:
        return False
    norm = normalize_name(name)
    for prefix in _RUNTIME_SKIP_PREFIXES:
        if norm == prefix or norm.startswith(prefix + "-"):
            return True
    return False


def select_wheel_url(pypi_data, req_info, py_version, platform_tag):
    """Pick the best wheel URL for a package requirement."""
    name = req_info["name"]
    spec = req_info["spec"]
    releases = pypi_data.get("releases", {})
    versions = sorted(releases.keys(), key=_version_sort_key, reverse=True)
    for version in versions:
        if spec and not version_matches(version, spec):
            continue
        files = get_release_urls(pypi_data, version)
        candidates = []
        for f in files:
            parsed = parse_wheel_filename(f.get("filename", ""))
            if parsed:
                parsed["url"] = f.get("url")
                parsed["digests"] = f.get("digests", {})
                candidates.append(parsed)
        best = pick_best_wheel(candidates, py_version, platform_tag)
        if best:
            return best
    raise ResolutionError(
        "No compatible wheel for {0} ({1}) on {2}/{3}".format(
            name, spec or "any", py_version, platform_tag
        )
    )


def _resolve_one(req_info, raw, is_top, py_version, platform_tag):
    name = req_info["name"]
    if not _dep_applies(raw, platform_tag, py_version):
        return None
    if _skip_runtime_dep(name, is_top):
        return None

    try:
        pypi_data = fetch_pypi_json(name)
        wheel = select_wheel_url(pypi_data, req_info, py_version, platform_tag)
    except ResolutionError:
        if is_top:
            raise
        return None

    wheel["requires_dist"] = release_requires_dist(
        name, wheel["version"], pypi_data=pypi_data
    )
    wheel["_pypi_data"] = pypi_data
    return wheel


def is_universal_platform(platform_tag):
    return platform_tag == "universal"


def resolve_requirements(
    requirements,
    py_version,
    platform_tag,
    include_deps=True,
    jobs=8,
    progress=False,
):
    """
    Resolve requirements to a list of wheel download specs.

    When platform_tag is ``universal``, wheels for all UNIVERSAL_PLATFORMS are
    merged into one bundle. Install picks compatible wheels on each machine.
    """
    if is_universal_platform(platform_tag):
        return _resolve_universal(
            requirements, py_version, include_deps, jobs, progress
        )
    return _resolve_single_platform(
        requirements, py_version, platform_tag, include_deps, jobs, progress
    )


def _resolve_universal(requirements, py_version, include_deps, jobs, progress):
    merged = {}
    if progress:
        sys.stderr.write(
            "Universal bundle across {0} platforms\n".format(len(UNIVERSAL_PLATFORMS))
        )
        sys.stderr.flush()

    for plat in UNIVERSAL_PLATFORMS:
        if progress:
            sys.stderr.write("  resolving for {0}...\n".format(plat))
            sys.stderr.flush()
        specs = _resolve_single_platform(
            requirements,
            py_version,
            plat,
            include_deps,
            jobs,
            progress=False,
        )
        for spec in specs:
            merged[spec["filename"]] = spec

    if progress:
        sys.stderr.write("Universal bundle: {0} unique wheels\n".format(len(merged)))
        sys.stderr.flush()
    return list(merged.values())


def _resolve_single_platform(
    requirements,
    py_version,
    platform_tag,
    include_deps=True,
    jobs=8,
    progress=False,
):
    resolved = {}
    queue = []

    for raw in requirements:
        info = parse_requirement(raw)
        if info:
            queue.append((info, raw, True))

    while queue:
        pending = []
        seen = set()
        for req_info, raw, is_top in queue:
            name = req_info["name"]
            if name in resolved or name in seen:
                continue
            seen.add(name)
            pending.append((req_info, raw, is_top))
        queue = []

        if not pending:
            break

        if progress:
            sys.stderr.write(
                "Resolving {0} packages ({1} done)...\n".format(
                    len(pending), len(resolved)
                )
            )
            sys.stderr.flush()

        workers = max(1, min(jobs, len(pending)))
        if workers == 1:
            results = [
                (
                    item,
                    _resolve_one(item[0], item[1], item[2], py_version, platform_tag),
                )
                for item in pending
            ]
        else:
            results = []
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(
                        _resolve_one,
                        req_info,
                        raw,
                        is_top,
                        py_version,
                        platform_tag,
                    ): (req_info, raw, is_top)
                    for req_info, raw, is_top in pending
                }
                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        results.append((item, future.result()))
                    except ResolutionError:
                        raise

        for (req_info, raw, is_top), wheel in results:
            if wheel is None:
                continue
            name = req_info["name"]
            wheel.pop("_pypi_data", None)
            resolved[name] = wheel

            if include_deps:
                for dep in wheel.get("requires_dist") or []:
                    if not _dep_applies(dep, platform_tag, py_version):
                        continue
                    dep_clean = re.split(r"[;\[]", dep)[0].strip()
                    dep_info = parse_requirement(dep_clean)
                    if dep_info and dep_info["name"] not in resolved:
                        queue.append((dep_info, dep, False))

    return list(resolved.values())


def detect_platform():
    """Detect current platform tag for wheel selection."""
    if sys.platform == "win32":
        import struct

        bits = struct.calcsize("P") * 8
        return "win_{0}".format("amd64" if bits == 64 else "32")
    if sys.platform == "darwin":
        import platform as plat

        mac_ver = plat.mac_ver()[0].split(".")
        major = mac_ver[0] if mac_ver else "10"
        minor = mac_ver[1] if len(mac_ver) > 1 else "9"
        return "macosx_{0}_{1}_x86_64".format(major, minor)
    import platform as plat

    machine = plat.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "manylinux2014_x86_64"
    if machine.startswith("aarch64") or machine.startswith("arm64"):
        return "manylinux2014_aarch64"
    if sys.platform.startswith("freebsd"):
        return "freebsd_{0}".format(machine)
    if sys.platform.startswith("openbsd"):
        return "openbsd_{0}".format(machine)
    if sys.platform.startswith("netbsd"):
        return "netbsd_{0}".format(machine)
    return "any"


def detect_python_version():
    return "{0}.{1}".format(sys.version_info.major, sys.version_info.minor)
