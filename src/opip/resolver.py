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
DEFAULT_INDEX_URL = "https://pypi.org/pypi"
USER_AGENT = "opip/{} (+https://github.com/Quad4-Software/pip-rns)".format(
    __import__("opip").__version__,
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
    """Parse a simple requirement string into name and optional version spec.

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


_PRE_LABEL_ORDER = {
    "a": 0,
    "alpha": 0,
    "b": 1,
    "beta": 1,
    "c": 2,
    "rc": 2,
    "preview": 2,
}

# Release / pre / post / dev subset of PEP 440 (stdlib only).
_VERSION_RE = re.compile(
    r"""
    ^
    (?:(?P<epoch>\d+)!)?
    (?P<release>\d+(?:\.\d+)*)
    (?:
        (?P<pre_l>alpha|beta|preview|a|b|c|rc)
        (?P<pre_n>\d+)?
    )?
    (?:
        \.(?P<post_l>post|rev|r)(?P<post_n>\d+)?
        |
        -(?P<post_n_legacy>\d+)
    )?
    (?:
        \.(?P<dev_l>dev)(?P<dev_n>\d+)?
    )?
    (?:\+(?P<local>[a-z0-9]+(?:[._-][a-z0-9]+)*))?
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _normalize_version_string(version):
    """Strip local tags noise and legacy separators before parse."""
    v = version.strip().lstrip("vV")
    # 1.0-rc1 / 1.0_rc1 -> 1.0rc1
    v = re.sub(
        r"[-_](?=(a|b|c|rc|alpha|beta|preview|post|rev|r|dev)\d*)",
        "",
        v,
        flags=re.IGNORECASE,
    )
    return v


def _parse_version(version):
    """Parse a version into comparable fields.

    Returns (epoch, release_tuple, pre, post, dev) or None.
    pre is (label_rank, num) or None. post/dev are ints or None.
    """
    m = _VERSION_RE.match(_normalize_version_string(version))
    if not m:
        return None
    epoch = int(m.group("epoch") or 0)
    release = tuple(int(x) for x in m.group("release").split("."))
    pre = None
    if m.group("pre_l"):
        label = m.group("pre_l").lower()
        pre = (_PRE_LABEL_ORDER.get(label, 0), int(m.group("pre_n") or 0))
    post = None
    if m.group("post_l") or m.group("post_n_legacy") is not None:
        post = int(m.group("post_n") or m.group("post_n_legacy") or 0)
    dev = None
    if m.group("dev_l"):
        dev = int(m.group("dev_n") or 0)
    return epoch, release, pre, post, dev


def _is_prerelease(version):
    """True for PEP 440 pre-releases and developmental releases."""
    parsed = _parse_version(version)
    if parsed is None:
        return bool(
            re.search(
                r"(?:^|[.\-_])?(?:a|b|c|rc|alpha|beta|preview|dev)\d*",
                version,
                re.IGNORECASE,
            ),
        )
    _epoch, _release, pre, _post, dev = parsed
    return pre is not None or dev is not None


def _spec_allows_prerelease(spec):
    """True when the requirement explicitly pins a pre-release version."""
    if not spec:
        return False
    for part in spec.strip().strip("()").split(","):
        part = part.strip().strip("()")
        for prefix in ("==", ">=", "<=", "!=", "~=", ">", "<"):
            if part.startswith(prefix):
                target = part[len(prefix) :].strip()
                if target and _is_prerelease(target):
                    return True
                break
    return False


def _version_sort_key(version):
    """Sort key aligned with PEP 440 ordering.

    Examples: 1.0.dev1 < 1.0a1 < 1.0b1 < 1.0rc1 < 1.0 < 1.0.post1
    """
    parsed = _parse_version(version)
    if parsed is None:
        return (0, (0,), (2, 0, 0), (0, 0), (1, 0), version)

    epoch, release, pre, post, dev = parsed

    # Developmental releases without a pre segment sort before alphas.
    if pre is None and post is None and dev is not None:
        pre_key = (0, 0, 0)
    elif pre is not None:
        pre_key = (1, pre[0], pre[1])
    else:
        pre_key = (2, 0, 0)

    post_key = (0, 0) if post is None else (1, post)

    if pre is None and post is None and dev is not None:
        # Exclusive .devN: order among themselves by N, still before alphas.
        dev_key = (0, dev)
    elif dev is None:
        dev_key = (1, 0)
    else:
        dev_key = (0, dev)

    return (epoch, release, pre_key, post_key, dev_key, version)


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
    ka, kb = _version_sort_key(a), _version_sort_key(b)
    if ka < kb:
        return -1
    if ka > kb:
        return 1
    return 0


def _index_base(index_url=None):
    base = (index_url or DEFAULT_INDEX_URL).rstrip("/")
    if base.endswith("/json"):
        base = base[: -len("/json")]
    return base


def _pkg_json_url(package, index_url=None):
    return f"{_index_base(index_url)}/{package}/json"


def _rel_json_url(package, version, index_url=None):
    return f"{_index_base(index_url)}/{package}/{version}/json"


def _fetch_url(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_pypi_json(package, timeout=60, index_url=None, offline=False):
    """Fetch package metadata from a Warehouse-compatible JSON index."""
    package = normalize_name(package)
    base = _index_base(index_url)
    cache_key = f"pkg:{base}:{package}"
    cached = pypi_cache.get(cache_key)
    if cached is not None:
        return cached

    if offline:
        raise ResolutionError(
            f"Offline create: no cached metadata for {package} on {base}",
        )

    url = _pkg_json_url(package, index_url)
    try:
        data = _fetch_url(url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ResolutionError(f"Package not found on index: {package}")
        raise ResolutionError(f"Index error for {package}: {exc}")

    pypi_cache.put(cache_key, data)
    return data


def fetch_release_json(package, version, timeout=60, index_url=None, offline=False):
    """Fetch version-specific metadata from index."""
    package = normalize_name(package)
    base = _index_base(index_url)
    cache_key = f"rel:{base}:{package}:{version}"
    cached = pypi_cache.get(cache_key)
    if cached is not None:
        return cached

    if offline:
        return None

    url = _rel_json_url(package, version, index_url)
    try:
        data = _fetch_url(url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise ResolutionError(f"Index error for {package} {version}: {exc}")

    if data is not None:
        pypi_cache.put(cache_key, data)
    return data


def release_requires_dist(
    package, version, pypi_data=None, index_url=None, offline=False,
):
    """Return Requires-Dist list for a package version."""
    if pypi_data is not None:
        info = pypi_data.get("info", {})
        if info.get("version") == version:
            return info.get("requires_dist") or []

    data = fetch_release_json(package, version, index_url=index_url, offline=offline)
    if data is None:
        return []
    info = data.get("info", {})
    return info.get("requires_dist") or []


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


def _pick_wheel_for_version(pypi_data, version, py_version, platform_tag):
    files = get_release_urls(pypi_data, version)
    candidates = []
    for f in files:
        parsed = parse_wheel_filename(f.get("filename", ""))
        if parsed:
            parsed["url"] = f.get("url")
            parsed["digests"] = f.get("digests", {})
            candidates.append(parsed)
    return pick_best_wheel(candidates, py_version, platform_tag)


def select_wheel_url(pypi_data, req_info, py_version, platform_tag):
    """Pick the best wheel URL for a package requirement.

    Prefers final releases. Pre-releases are used only when the requirement
    explicitly asks for one, or when no final release matches.
    """
    name = req_info["name"]
    spec = req_info["spec"]
    releases = pypi_data.get("releases", {})
    versions = sorted(releases.keys(), key=_version_sort_key, reverse=True)
    allow_pre = _spec_allows_prerelease(spec)

    def _try(include_prerelease):
        for version in versions:
            if not include_prerelease and _is_prerelease(version):
                continue
            if spec and not version_matches(version, spec):
                continue
            best = _pick_wheel_for_version(pypi_data, version, py_version, platform_tag)
            if best:
                return best
        return None

    best = _try(include_prerelease=allow_pre)
    if best is None and not allow_pre:
        best = _try(include_prerelease=True)
    if best:
        return best
    raise ResolutionError(
        "No compatible wheel for {} ({}) on {}/{}".format(
            name, spec or "any", py_version, platform_tag,
        ),
    )


def _resolve_one(
    req_info,
    raw,
    is_top,
    py_version,
    platform_tag,
    index_url=None,
    find_links=None,
    offline=False,
):
    name = req_info["name"]
    if not _dep_applies(raw, platform_tag, py_version):
        return None
    if _skip_runtime_dep(name, is_top):
        return None

    if find_links:
        from opip.find_links import pick_local_wheel, scan_wheels

        local = pick_local_wheel(
            scan_wheels(find_links), req_info, py_version, platform_tag,
        )
        if local:
            return local

    try:
        pypi_data = fetch_pypi_json(name, index_url=index_url, offline=offline)
        wheel = select_wheel_url(pypi_data, req_info, py_version, platform_tag)
    except ResolutionError:
        if is_top:
            raise
        return None

    wheel["requires_dist"] = release_requires_dist(
        name,
        wheel["version"],
        pypi_data=pypi_data,
        index_url=index_url,
        offline=offline,
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
    index_url=None,
    find_links=None,
    offline=False,
):
    """Resolve requirements to a list of wheel download specs.

    When platform_tag is ``universal``, wheels for all UNIVERSAL_PLATFORMS are
    merged into one bundle. Install picks compatible wheels on each machine.
    """
    if is_universal_platform(platform_tag):
        return _resolve_universal(
            requirements,
            py_version,
            include_deps,
            jobs,
            progress,
            index_url=index_url,
            find_links=find_links,
            offline=offline,
        )
    return _resolve_single_platform(
        requirements,
        py_version,
        platform_tag,
        include_deps,
        jobs,
        progress,
        index_url=index_url,
        find_links=find_links,
        offline=offline,
    )


def _resolve_universal(
    requirements,
    py_version,
    include_deps,
    jobs,
    progress,
    index_url=None,
    find_links=None,
    offline=False,
):
    merged = {}
    if progress:
        sys.stderr.write(
            f"Universal bundle across {len(UNIVERSAL_PLATFORMS)} platforms\n",
        )
        sys.stderr.flush()

    for plat in UNIVERSAL_PLATFORMS:
        if progress:
            sys.stderr.write(f"  resolving for {plat}...\n")
            sys.stderr.flush()
        specs = _resolve_single_platform(
            requirements,
            py_version,
            plat,
            include_deps,
            jobs,
            progress=False,
            index_url=index_url,
            find_links=find_links,
            offline=offline,
        )
        for spec in specs:
            merged[spec["filename"]] = spec

    if progress:
        sys.stderr.write(f"Universal bundle: {len(merged)} unique wheels\n")
        sys.stderr.flush()
    return list(merged.values())


def _resolve_single_platform(
    requirements,
    py_version,
    platform_tag,
    include_deps=True,
    jobs=8,
    progress=False,
    index_url=None,
    find_links=None,
    offline=False,
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
                f"Resolving {len(pending)} packages ({len(resolved)} done)...\n",
            )
            sys.stderr.flush()

        workers = max(1, min(jobs, len(pending)))
        if workers == 1:
            results = [
                (
                    item,
                    _resolve_one(
                        item[0],
                        item[1],
                        item[2],
                        py_version,
                        platform_tag,
                        index_url=index_url,
                        find_links=find_links,
                        offline=offline,
                    ),
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
                        index_url,
                        find_links,
                        offline,
                    ): (req_info, raw, is_top)
                    for req_info, raw, is_top in pending
                }
                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        results.append((item, future.result()))
                    except ResolutionError:
                        raise

        for (req_info, _, _), wheel in results:
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
        return "win_{}".format("amd64" if bits == 64 else "32")
    if sys.platform == "darwin":
        import platform as plat

        mac_ver = plat.mac_ver()[0].split(".")
        major = mac_ver[0] if mac_ver else "10"
        minor = mac_ver[1] if len(mac_ver) > 1 else "9"
        return f"macosx_{major}_{minor}_x86_64"
    import platform as plat

    machine = plat.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "manylinux2014_x86_64"
    if machine.startswith("aarch64") or machine.startswith("arm64"):
        return "manylinux2014_aarch64"
    if sys.platform.startswith("freebsd"):
        return f"freebsd_{machine}"
    if sys.platform.startswith("openbsd"):
        return f"openbsd_{machine}"
    if sys.platform.startswith("netbsd"):
        return f"netbsd_{machine}"
    return "any"


def detect_python_version():
    return f"{sys.version_info.major}.{sys.version_info.minor}"
