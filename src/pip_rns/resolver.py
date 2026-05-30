"""URL resolution and remote repository cloning for custom protocol schemes."""

from __future__ import annotations

import hashlib
import os
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
        check_rns_available()
        super().clone(url, dest, ref=ref)

    def update(self, url: str, dest: Path, ref: str | None = None) -> None:
        check_rns_available()
        super().update(url, dest, ref=ref)


register_scheme("rns", RnsResolver)


class Resolver:
    """Facade that normalizes a remote string, selects the right resolver, and produces a local clone."""

    def resolve(
        self,
        remote: str,
        editable: bool = False,
        ref: str | None = None,
        use_cache: bool = False,
    ) -> Path:
        from .aliases import get_manager as get_alias_mgr
        from .indexes import get_manager as get_index_mgr

        amgr = get_alias_mgr()
        if amgr:
            remote = amgr.resolve(remote)
        imgr = get_index_mgr()
        if imgr:
            remote = imgr.resolve(remote)
        url = normalize_url(remote)

        # Local paths: return directly, no clone needed
        if url.startswith(("/", "~", ".")):
            return Path(url).resolve()

        resolver = get_resolver(url)

        if editable:
            dest = PERSISTENT_DIR / repo_hash(url)
            if dest.exists():
                resolver.update(url, dest, ref=ref)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                resolver.clone(url, dest, ref=ref)
            return dest

        if use_cache:
            cache_key = repo_hash(f"{url}@{ref}" if ref else url)
            dest = CACHE_DIR / cache_key
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                resolver.clone(url, dest, ref=ref)
            return dest

        tmpdir = Path(tempfile.mkdtemp())
        resolver.clone(url, tmpdir, ref=ref)
        return tmpdir
