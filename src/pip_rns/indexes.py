"""Remote package index manager: register, sync, and resolve short names from RNS-hosted indexes.

An index is an rngit repository containing a plain-text packages file:
  lxmfy=926baefe.../quad4/LXMFy

Indexes are registered by URL, cloned on sync, and merged into a local mapping.
Resolution order: local aliases -> indexes -> raw path.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from .retry import retry


_manager: IndexManager | None = None


def init() -> None:
    global _manager
    _manager = IndexManager()


def get_manager() -> IndexManager | None:
    return _manager


def _config_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", ".")) / "pip-rns"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg) / "pip-rns" if xdg else Path.home() / ".config" / "pip-rns"


def _data_dir() -> Path:
    return Path.home() / ".local" / "share" / "pip-rns" / "index-data"


def _parse_plain(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        if k and v:
            result[k] = v
    return result


class IndexManager:
    """Manages registered index URLs and their synced package mappings."""

    def __init__(self) -> None:
        self._urls_file = _config_dir() / "indexes"
        self._data_dir = _data_dir()
        self._urls: list[str] = []
        self._packages: dict[str, str] = {}
        self._load_urls()
        self._load_packages()

    def _load_urls(self) -> None:
        if not self._urls_file.exists():
            return
        for line in self._urls_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                self._urls.append(line)

    def _save_urls(self) -> None:
        self._urls_file.parent.mkdir(parents=True, exist_ok=True)
        self._urls_file.write_text("\n".join(self._urls) + "\n")

    def _load_packages(self) -> None:
        pkg = self._data_dir / "packages"
        if not pkg.exists():
            return
        try:
            self._packages = _parse_plain(pkg.read_text())
        except Exception:
            self._packages = {}

    def _save_packages(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        lines = [f"{k}={v}" for k, v in sorted(self._packages.items())]
        (self._data_dir / "packages").write_text("\n".join(lines) + "\n")

    def add(self, url: str) -> None:
        if url not in self._urls:
            self._urls.append(url)
            self._save_urls()

    def remove(self, url: str) -> None:
        self._urls = [u for u in self._urls if u != url]
        self._save_urls()
        self._packages = {}
        self.sync()

    def list(self) -> list[str]:
        return list(self._urls)

    def packages(self) -> dict[str, str]:
        return dict(self._packages)

    @retry(max_attempts=3, delay=1.0, backoff=2.0)
    def _clone(self, url: str, dest: Path) -> None:
        subprocess.run(["git", "clone", "--depth", "1", url, str(dest)], check=True)

    def search(self, query: str) -> dict[str, str]:
        query = query.lower()
        return {k: v for k, v in self._packages.items() if query in k.lower()}

    def sync(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        for url in self._urls:
            key = hashlib.sha256(url.encode()).hexdigest()[:16]
            dest = self._data_dir / "repos" / key

            if dest.exists():
                try:
                    subprocess.run(
                        ["git", "-C", str(dest), "pull"],
                        check=True,
                        capture_output=True,
                    )
                except Exception:
                    pass
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    self._clone(url, dest)
                except Exception:
                    continue

            pkg = dest / "packages"
            if pkg.exists():
                try:
                    data = _parse_plain(pkg.read_text())
                    for k in data:
                        if k in merged:
                            import sys

                            print(
                                f"  warning: {k} already defined, using {url}",
                                file=sys.stderr,
                            )
                    merged.update(data)
                except Exception:
                    pass

        self._packages = merged
        self._save_packages()
        return merged

    def resolve(self, text: str) -> str:
        return self._packages.get(text, text)
