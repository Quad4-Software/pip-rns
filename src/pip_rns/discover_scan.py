"""Scan discovered rngit nodes for Python-installable repositories."""

from __future__ import annotations

import contextlib
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .discover import DiscoveredNode, _import_rns
from .indexes import _parse_plain
from .releases import _pick_whl, list_releases, release_info
from .ui import dim

GROUP_LINK_RE = re.compile(r"/page/group\.mu`[^]]*g=([^|\]]+)")
REPO_LINK_RE = re.compile(r"/page/repo\.mu`[^]]*g=([^|]+)\|r=([^|\]]+)")

# Common index repo paths on rngit nodes (packages file inside)
INDEX_CANDIDATES = (
    "public/packages",
    "public/index",
    "index/packages",
    "public/pip-index",
)


@dataclass
class DiscoveredPackage:
    """A Python-oriented repo found on a discovered rngit node."""

    name: str
    remote: str
    destination_hash: str
    group: str
    repo: str
    has_wheel: bool = False
    latest_tag: str | None = None
    source: str = "scan"
    heard_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "remote": self.remote,
            "destination_hash": self.destination_hash,
            "group": self.group,
            "repo": self.repo,
            "has_wheel": self.has_wheel,
            "latest_tag": self.latest_tag,
            "source": self.source,
            "heard_at": self.heard_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DiscoveredPackage | None:
        name = raw.get("name")
        remote = raw.get("remote")
        dest = raw.get("destination_hash")
        group = raw.get("group")
        repo = raw.get("repo")
        if not (name and remote and dest and group and repo):
            return None
        return cls(
            name=str(name),
            remote=str(remote),
            destination_hash=str(dest),
            group=str(group),
            repo=str(repo),
            has_wheel=bool(raw.get("has_wheel")),
            latest_tag=str(raw["latest_tag"]) if raw.get("latest_tag") else None,
            source=str(raw.get("source") or "scan"),
            heard_at=float(raw.get("heard_at") or 0.0),
        )


def parse_nomad_groups(micron: str) -> list[str]:
    """Extract group names from a Nomad index.mu page body."""
    groups: list[str] = []
    seen: set[str] = set()
    for match in GROUP_LINK_RE.finditer(micron or ""):
        name = urllib.parse.unquote_plus(match.group(1)).strip()
        if name and name not in seen:
            seen.add(name)
            groups.append(name)
    return groups


def parse_nomad_repos(micron: str) -> list[tuple[str, str]]:
    """Extract (group, repo) pairs from a Nomad group.mu page body."""
    repos: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in REPO_LINK_RE.finditer(micron or ""):
        group = urllib.parse.unquote_plus(match.group(1)).strip()
        repo = urllib.parse.unquote_plus(match.group(2)).strip()
        key = (group, repo)
        if group and repo and key not in seen:
            seen.add(key)
            repos.append(key)
    return repos


def remote_for(destination_hash: str, group: str, repo: str) -> str:
    return f"rns://{destination_hash}/{group}/{repo}"


def package_name_for(repo: str, index_name: str | None = None) -> str:
    if index_name:
        return index_name.strip().lower()
    return repo.strip().lower().replace("_", "-")


def check_python_release(remote: str) -> tuple[bool, str | None]:
    """Return (has_wheel, latest_tag) for a remote.

    Uses rngit release list/view. Failures mean unknown (not Python).
    """
    try:
        releases = list_releases(remote)
    except Exception:
        return False, None
    if not releases:
        return False, None
    published = [r for r in releases if r.get("status") == "published"] or list(
        releases,
    )
    for rel in published[:5]:
        tag = rel.get("tag")
        if not tag:
            continue
        try:
            info = release_info(remote, tag)
        except Exception:
            continue
        if _pick_whl(info.get("artifacts") or []):
            return True, tag
    # Repo exists with releases but no wheel yet. Still likely a package host.
    first = published[0].get("tag")
    return False, first if isinstance(first, str) else None


def _await_path(RNS, dest_hash: bytes, timeout: float) -> bool:
    if RNS.Transport.has_path(dest_hash):
        return True
    RNS.Transport.request_path(dest_hash)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if RNS.Transport.has_path(dest_hash):
            return True
        time.sleep(0.05)
    return bool(RNS.Transport.has_path(dest_hash))


def _await_link(link, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if link.status == link.ACTIVE:
            return True
        if link.status == link.CLOSED:
            return False
        time.sleep(0.05)
    return bool(link.status == link.ACTIVE)


def _link_request(link, path: str, data=None, timeout: float = 30.0) -> bytes | None:
    done = {"ok": False, "data": None, "err": None}

    def _success(receipt):
        try:
            done["data"] = receipt.response
            done["ok"] = True
        except Exception as exc:
            done["err"] = str(exc)

    def _failure(_receipt):
        done["err"] = "request failed"

    try:
        link.request(
            path,
            data=data,
            response_callback=_success,
            failed_callback=_failure,
            timeout=timeout,
        )
    except Exception:
        return None
    deadline = time.time() + timeout
    while time.time() < deadline and not done["ok"] and done["err"] is None:
        time.sleep(0.05)
    if done["ok"] and done["data"] is not None:
        raw = done["data"]
        return raw if isinstance(raw, bytes) else bytes(raw)
    return None


def fetch_nomad_catalog(
    identity_hash: str | None = None,
    *,
    git_destination_hash: str | None = None,
    path_timeout: float = 20.0,
    link_timeout: float = 30.0,
    request_timeout: float = 30.0,
    reticulum_config: str | None = None,
) -> list[tuple[str, str]]:
    """List (group, repo) via Nomad pages when serve_nomadnet is enabled.

    Returns empty list when Nomad is unavailable.
    """
    RNS = _import_rns()
    _reticulum = RNS.Reticulum(configdir=reticulum_config)
    del _reticulum

    identity = None
    if git_destination_hash:
        try:
            git_dh = bytes.fromhex(git_destination_hash)
        except ValueError:
            git_dh = None
        if git_dh is not None:
            _await_path(RNS, git_dh, path_timeout)
            identity = RNS.Identity.recall(git_dh)

    if identity is None and identity_hash:
        try:
            ident_bytes = bytes.fromhex(identity_hash)
        except ValueError:
            return []
        identity = RNS.Identity.recall(ident_bytes, from_identity_hash=True)
        if identity is None:
            # Derive nomad dest from identity hash bytes directly
            nomad_dh = RNS.Destination.hash_from_name_and_identity(
                "nomadnetwork.node",
                ident_bytes,
            )
            if not _await_path(RNS, nomad_dh, path_timeout):
                return []
            identity = RNS.Identity.recall(nomad_dh)
            if identity is None:
                identity = RNS.Identity.recall(ident_bytes, from_identity_hash=True)

    if identity is None:
        return []

    nomad_dh = RNS.Destination.hash_from_name_and_identity(
        "nomadnetwork.node",
        identity,
    )
    if not _await_path(RNS, nomad_dh, path_timeout):
        return []

    dest = RNS.Destination(
        identity,
        RNS.Destination.OUT,
        RNS.Destination.SINGLE,
        "nomadnetwork",
        "node",
    )
    link = RNS.Link(dest)
    if not _await_link(link, link_timeout):
        with contextlib.suppress(Exception):
            link.teardown()
        return []

    try:
        index_raw = _link_request(
            link,
            "/page/index.mu",
            data=None,
            timeout=request_timeout,
        )
        if not index_raw:
            return []
        groups = parse_nomad_groups(index_raw.decode("utf-8", errors="replace"))
        if not groups:
            groups = ["public"]

        repos: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for group in groups:
            page = _link_request(
                link,
                "/page/group.mu",
                data={"var_g": group},
                timeout=request_timeout,
            )
            if not page:
                continue
            for pair in parse_nomad_repos(page.decode("utf-8", errors="replace")):
                if pair not in seen:
                    seen.add(pair)
                    repos.append(pair)
        return repos
    finally:
        with contextlib.suppress(Exception):
            link.teardown()


def probe_packages_indexes(
    destination_hash: str,
    *,
    timeout: float = 120.0,
) -> list[DiscoveredPackage]:
    """Shallow-clone common index repos and parse packages files."""
    found: list[DiscoveredPackage] = []
    now = time.time()
    for path in INDEX_CANDIDATES:
        group, _, repo = path.partition("/")
        remote = remote_for(destination_hash, group, repo)
        tmp = Path(tempfile.mkdtemp(prefix="pip-rns-idx-"))
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", remote, str(tmp / "repo")],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                continue
            pkg_file = tmp / "repo" / "packages"
            if not pkg_file.is_file():
                continue
            mapping = _parse_plain(pkg_file.read_text(encoding="utf-8"))
            for name, target in mapping.items():
                target = target.strip()
                if not target:
                    continue
                if not target.lower().startswith("rns://"):
                    # Relative identity/group/repo or dest/group/repo
                    if target.count("/") == 2:
                        target = "rns://" + target
                    else:
                        target = remote_for(destination_hash, "public", target)
                parts = (
                    target[6:].split("/") if target.lower().startswith("rns://") else []
                )
                if len(parts) != 3:
                    continue
                dest, grp, rep = parts
                found.append(
                    DiscoveredPackage(
                        name=package_name_for(rep, name),
                        remote=f"rns://{dest}/{grp}/{rep}",
                        destination_hash=dest,
                        group=grp,
                        repo=rep,
                        has_wheel=False,
                        latest_tag=None,
                        source="index",
                        heard_at=now,
                    ),
                )
        except Exception:
            continue
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return found


def enrich_with_releases(packages: list[DiscoveredPackage]) -> list[DiscoveredPackage]:
    """Mark packages that publish a release wheel."""
    out: list[DiscoveredPackage] = []
    for pkg in packages:
        has_wheel, tag = check_python_release(pkg.remote)
        pkg.has_wheel = has_wheel
        if tag:
            pkg.latest_tag = tag
        # Keep index entries even without wheels. Nomad-only keep if wheel or index.
        out.append(pkg)
    return out


def scan_node(
    node: DiscoveredNode,
    *,
    reticulum_config: str | None = None,
    check_releases: bool = True,
    on_status: Callable[[str], None] | None = None,
) -> list[DiscoveredPackage]:
    """Find Python packages on one discovered node.

    Strategy:
    1. Try Nomad catalog (group/repo list)
    2. Try common packages-index remotes
    3. Optionally check rngit releases for .whl
    """

    def status(msg: str) -> None:
        if on_status:
            on_status(msg)

    packages: list[DiscoveredPackage] = []
    seen_remotes: set[str] = set()
    now = time.time()

    if node.identity_hash or node.destination_hash:
        status(f"nomad catalog on {node.destination_hash[:12]}...")
        try:
            pairs = fetch_nomad_catalog(
                node.identity_hash,
                git_destination_hash=node.destination_hash,
                reticulum_config=reticulum_config,
            )
        except Exception:
            pairs = []
        for group, repo in pairs:
            remote = remote_for(node.destination_hash, group, repo)
            if remote in seen_remotes:
                continue
            seen_remotes.add(remote)
            packages.append(
                DiscoveredPackage(
                    name=package_name_for(repo),
                    remote=remote,
                    destination_hash=node.destination_hash,
                    group=group,
                    repo=repo,
                    source="nomad",
                    heard_at=now,
                ),
            )

    status(f"index probe on {node.destination_hash[:12]}...")
    for pkg in probe_packages_indexes(node.destination_hash):
        if pkg.remote in seen_remotes:
            # Prefer index name if we already saw the remote via Nomad
            for existing in packages:
                if existing.remote == pkg.remote:
                    existing.name = pkg.name
                    existing.source = "index"
                    break
            continue
        seen_remotes.add(pkg.remote)
        packages.append(pkg)

    if check_releases and packages:
        status(f"checking releases ({len(packages)} repo(s))...")
        packages = enrich_with_releases(packages)

    # Prefer Python-installable: has wheel, or came from a packages index
    preferred = [p for p in packages if p.has_wheel or p.source == "index"]
    return preferred or packages


def scan_nodes(
    nodes: list[DiscoveredNode],
    *,
    reticulum_config: str | None = None,
    check_releases: bool = True,
    on_status: Callable[[str], None] | None = None,
) -> list[DiscoveredPackage]:
    all_pkgs: list[DiscoveredPackage] = []
    for node in nodes:
        all_pkgs.extend(
            scan_node(
                node,
                reticulum_config=reticulum_config,
                check_releases=check_releases,
                on_status=on_status,
            ),
        )
    return all_pkgs


def format_package_line(pkg: DiscoveredPackage) -> str:
    wheel = (
        f"wheel:{pkg.latest_tag}"
        if pkg.has_wheel and pkg.latest_tag
        else ("wheel" if pkg.has_wheel else "no-wheel")
    )
    return f"{pkg.name}\t{pkg.remote}\t{wheel}\t{pkg.source}"


def install_hint(pkg: DiscoveredPackage) -> str:
    return f"pip-rns install {pkg.name}"


def maybe_auto_alias(
    packages: list[DiscoveredPackage],
    alias_mgr,
    *,
    auto: bool = False,
    no_interactive: bool = False,
) -> int:
    """Create aliases for discovered packages without conflicting names.

    Returns count of aliases created.
    """
    from opip.interactive import is_noninteractive

    if is_noninteractive(no_interactive):
        return 0 if not auto else _apply_auto_aliases(packages, alias_mgr)

    candidates: list[DiscoveredPackage] = []
    for pkg in packages:
        existing = alias_mgr.get(pkg.name)
        if existing and existing != pkg.remote:
            print(f"  {dim(f'skip alias {pkg.name}: points elsewhere')}")
            continue
        if existing == pkg.remote:
            continue
        candidates.append(pkg)

    if not candidates:
        return 0

    if not auto:
        try:
            answer = (
                input(f"Alias {len(candidates)} discovered package(s)? [Y/n]: ")
                .strip()
                .lower()
            )
        except (EOFError, KeyboardInterrupt):
            return 0
        if answer in ("n", "no"):
            return 0

    return _apply_auto_aliases(candidates, alias_mgr)


def _apply_auto_aliases(packages: list[DiscoveredPackage], alias_mgr) -> int:
    count = 0
    for pkg in packages:
        existing = alias_mgr.get(pkg.name)
        if existing and existing != pkg.remote:
            continue
        if existing == pkg.remote:
            continue
        alias_mgr.set(pkg.name, pkg.remote)
        count += 1
    return count
