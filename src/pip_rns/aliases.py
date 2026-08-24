"""Alias manager: short remote names stored in a plain-text file.

File location (no extension):
  Linux:   ~/.config/pip-rns/aliases           (or $XDG_CONFIG_HOME/pip-rns/aliases)
  Windows: %APPDATA%/pip-rns/aliases

Custom location via --config DIR or PIP_RNS_CONFIG env var.

Format (one alias per line, skips bad lines silently):
  myapp=06a54b505bb67b25ef3f8097e8001edc/public/MyApp
  lxmfy=06a54b505bb67b25ef3f8097e8001edc/public/LXMFy
"""

from __future__ import annotations

import os
from pathlib import Path

_manager: AliasManager | None = None


def init(config_dir: str | None = None) -> None:
    global _manager
    _manager = AliasManager(config_dir)


def get_manager() -> AliasManager | None:
    return _manager


def _default_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", ".")) / "pip-rns"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "pip-rns"
    return Path.home() / ".config" / "pip-rns"


class AliasManager:
    """Manages a flat key=value alias file. Malformed lines are silently skipped."""

    def __init__(self, config_dir: str | None = None) -> None:
        base = Path(config_dir) if config_dir else _default_dir()
        self._path = base / "aliases"
        self._aliases: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            text = self._path.read_text()
        except Exception:
            return
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if key and val:
                self._aliases[key] = val

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"{k}={v}" for k, v in sorted(self._aliases.items())]
        self._path.write_text("\n".join(lines) + "\n")

    def get(self, name: str) -> str | None:
        return self._aliases.get(name)

    def set(self, name: str, remote: str) -> None:
        self._aliases[name] = remote
        self.save()

    def remove(self, name: str) -> None:
        self._aliases.pop(name, None)
        self.save()

    def list(self) -> dict[str, str]:
        return dict(self._aliases)

    def resolve(self, text: str) -> str:
        return self._aliases.get(text, text)
