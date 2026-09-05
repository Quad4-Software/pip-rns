# Copyright (c) 2026, Quad4 (quad4.io)
"""URL resolution and remote repository cloning for custom protocol schemes."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .retry import retry

PERSISTENT_DIR = Path.home() / ".local" / "share" / "pip-rns" / "checkouts"
CACHE_DIR = Path.home() / ".local" / "share" / "pip-rns" / "cache"

_REGISTERED_SCHEMES: dict[str, type[BaseResolver]] = {}


def check_rns_available() -> None:
    """Check that git-remote-rns is on PATH before attempting an RNS operation."""
    if shutil.which("git-remote-rns") is not None:
        return
    if shutil.which("git") is None:
        msg = "git is not installed. Install git to use pip-rns."
        raise RuntimeError(msg)
    msg = (
        "git-remote-rns not found on PATH.\n"
        "Install it via: pipx install rns\n"
        "Or set PIP_RNS_PIP=/usr/bin/pip if pip is managed externally."
    )
    raise RuntimeError(msg)


def register_scheme(scheme: str, resolver_cls: type[BaseResolver]) -> None:
    _REGISTERED_SCHEMES[scheme] = resolver_cls


def get_resolver(url: str) -> BaseResolver:
    for scheme, cls in _REGISTERED_SCHEMES.items():
        if url.startswith((f"{scheme}://", f"{scheme}:")):
            return cls()
    msg = f"No resolver registered for URL: {url}"
    raise ValueError(msg)


def normalize_url(remote: str) -> str:
    remote = remote.strip()
    for scheme in _REGISTERED_SCHEMES:
        if remote.startswith((f"{scheme}://", f"{scheme}:")):
            return remote
    if remote.startswith(("/", "~", ".")):
        return remote
    if os.name == "nt" and len(remote) > 1 and remote[1] == ":":
        return remote
    return f"rns://{remote}"


def parse_ref(remote: str) -> tuple[str, str | None]:
    last_slash = remote.rfind("/")
    last_at = remote.rfind("@")
    if last_at > last_slash:
        return remote[:last_at], remote[last_at + 1 :] or None
    return remote, None


_VERSION_REF_RE = re.compile(r"^v?\d+(\.\d+)*([a-zA-Z0-9._+-]*)?$")
_BRANCH_REF_NAMES = frozenset(
    {
        "master",
        "main",
        "trunk",
        "develop",
        "development",
        "dev",
        "head",
        "default",
        "stable",
        "next",
    },
)


def ref_implies_source(ref: str | None) -> bool:
    """True when ref looks like a branch/commit, not a release version tag.

    Version-like refs (v1.2.3, 1.2.3) still prefer release wheels.
    Branch names like master/main skip the release probe.
    """
    if not ref:
        return False
    name = ref.strip()
    if not name:
        return False
    if name.lower() in _BRANCH_REF_NAMES:
        return True
    if _VERSION_REF_RE.match(name):
        return False
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", name):
        return True
    return True


def repo_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


class BaseResolver:
    """Protocol-specific resolver for cloning and updating remote repositories."""

    scheme = ""

    def clone(self, url: str, dest: Path, ref: str | None = None) -> None:
        raise NotImplementedError

    def update(self, url: str, dest: Path, ref: str | None = None) -> None:
        raise NotImplementedError


class GitResolver(BaseResolver):
    """Resolves git-accessible URLs (rns://, https://, etc.) via the git CLI."""

    scheme = ""

    @retry(max_attempts=3, delay=1.0, backoff=2.0)
    def clone(self, url: str, dest: Path, ref: str | None = None) -> None:
        args = ["git", "clone"]
        if ref:
            args.extend(["--branch", ref, "--depth", "1"])
        args.extend([url, str(dest)])
        subprocess.run(args, check=True)

    @retry(max_attempts=3, delay=1.0, backoff=2.0)
    def update(self, url: str, dest: Path, ref: str | None = None) -> None:
        if ref:
            subprocess.run(
                ["git", "-C", str(dest), "fetch", "--depth", "1", "origin", ref],
                check=True,
            )
            subprocess.run(["git", "-C", str(dest), "checkout", ref], check=True)
        else:
            subprocess.run(["git", "-C", str(dest), "pull"], check=True)


class RnsResolver(GitResolver):
    """Resolver for rns:// URLs via the git-remote-rns helper."""

    scheme = "rns"

    def clone(self, url: str, dest: Path, ref: str | None = None) -> None:
        from .progress import RnsWait

        check_rns_available()
        with RnsWait("Waiting on Reticulum (clone)"):
            super().clone(url, dest, ref=ref)

    def update(self, url: str, dest: Path, ref: str | None = None) -> None:
        from .progress import RnsWait

        check_rns_available()
        with RnsWait("Waiting on Reticulum (update)"):
            super().update(url, dest, ref=ref)


register_scheme("rns", RnsResolver)


def _ensure_clone(
    resolver: BaseResolver,
    url: str,
    dest: Path,
    *,
    ref: str | None,
    update_existing: bool,
) -> str:
    """Clone into dest, or update an existing checkout.

    Returns a short status label: 'cloned', 'updated', or 'cached'.
    Cleans up incomplete dest on interrupt.
    """
    git_dir = dest / ".git"
    try:
        if dest.exists() and git_dir.exists():
            if update_existing:
                resolver.update(url, dest, ref=ref)
                return "updated"
            return "cached"
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        resolver.clone(url, dest, ref=ref)
        return "cloned"
    except KeyboardInterrupt:
        if dest.exists() and not git_dir.exists():
            shutil.rmtree(dest, ignore_errors=True)
        raise
    except Exception:
        if dest.exists() and not git_dir.exists():
            shutil.rmtree(dest, ignore_errors=True)
        raise


class OfflineError(RuntimeError):
    """Raised when --offline needs network or a missing cache."""


class Resolver:
    """Normalize a remote, pick a resolver, and produce a local clone."""

    def resolve(
        self,
        remote: str,
        editable: bool = False,
        ref: str | None = None,
        use_cache: bool = False,
        offline: bool = False,
    ) -> Path:
        from .aliases import get_manager as get_alias_mgr
        from .indexes import get_manager as get_index_mgr

        amgr = get_alias_mgr()
        if amgr:
            remote = amgr.resolve(remote)
        imgr = get_index_mgr()
        if imgr:
            remote = imgr.resolve(remote)
        # Discovered Python packages from pip-rns discover scan
        if "/" not in remote and "://" not in remote:
            try:
                from .discover import DiscoverStore

                found = DiscoverStore().resolve_package(remote)
                if found:
                    remote = found
            except Exception:
                pass
        url = normalize_url(remote)

        # Local paths: return directly, no clone needed
        if url.startswith(("/", "~", ".")):
            return Path(url).resolve()

        resolver = get_resolver(url)

        # RNS clones are expensive. Prefer persistent cache + fetch unless disabled.
        if (
            not editable
            and not use_cache
            and url.startswith("rns://")
            and os.environ.get("PIP_RNS_NO_CACHE", "").strip()
            not in ("1", "true", "yes")
        ):
            use_cache = True

        if offline:
            use_cache = True

        if editable:
            dest = PERSISTENT_DIR / repo_hash(url)
            if offline:
                git_dir = dest / ".git"
                if dest.exists() and git_dir.exists():
                    self.last_status = "cached"
                    return dest
                raise OfflineError(
                    f"Offline: no editable clone at {dest}. "
                    "Clone once online, then retry with --offline.",
                )
            status = _ensure_clone(resolver, url, dest, ref=ref, update_existing=True)
            self.last_status = status
            return dest

        if use_cache:
            cache_key = repo_hash(f"{url}@{ref}" if ref else url)
            dest = CACHE_DIR / cache_key
            if offline:
                git_dir = dest / ".git"
                if dest.exists() and git_dir.exists():
                    self.last_status = "cached"
                    return dest
                raise OfflineError(
                    f"Offline: no cached clone for {url}. "
                    "Install once online (or use a local path / .opip), "
                    "then retry with --offline.",
                )
            status = _ensure_clone(
                resolver,
                url,
                dest,
                ref=ref,
                update_existing=not offline,
            )
            self.last_status = status
            return dest

        if offline:
            raise OfflineError(
                "Offline: source install requires a cache hit or local path. "
                "Use --use-cache online first, or install from a release / .opip.",
            )

        tmpdir = Path(tempfile.mkdtemp(prefix="pip-rns-"))
        try:
            resolver.clone(url, tmpdir, ref=ref)
        except BaseException:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise
        self.last_status = "cloned"
        return tmpdir
