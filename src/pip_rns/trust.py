"""Trusted publisher identities for release verification."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _default_config_dir(config_dir: str | None = None) -> Path:
    if config_dir:
        return Path(config_dir)
    env = os.environ.get("PIP_RNS_CONFIG")
    if env:
        return Path(env)
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", ".")) / "pip-rns"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "pip-rns"
    return Path.home() / ".config" / "pip-rns"


class TrustStore:
    """
    JSON trust store: default signer + per-remote trusted identities.

    File: {config}/trust.json
      {"default": "<identity>", "remotes": {"rns://...": "<identity>"}}
    """

    def __init__(self, config_dir: str | None = None) -> None:
        self._dir = _default_config_dir(config_dir)
        self._path = self._dir / "trust.json"
        self._data: dict[str, Any] = {"default": None, "remotes": {}}
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        remotes = raw.get("remotes") or {}
        if not isinstance(remotes, dict):
            remotes = {}
        self._data = {
            "default": raw.get("default"),
            "remotes": {str(k): str(v) for k, v in remotes.items() if v},
        }

    def save(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @property
    def path(self) -> Path:
        return self._path

    def get_default(self) -> str | None:
        val = self._data.get("default")
        return str(val) if val else None

    def set_default(self, identity: str) -> None:
        self._data["default"] = identity.strip()
        self.save()

    def forget_default(self) -> bool:
        if self._data.get("default"):
            self._data["default"] = None
            self.save()
            return True
        return False

    def get_remote(self, remote: str) -> str | None:
        remotes = self._data.get("remotes") or {}
        val = remotes.get(remote)
        return str(val) if val else None

    def set_remote(self, remote: str, identity: str) -> None:
        remotes = self._data.setdefault("remotes", {})
        remotes[remote] = identity.strip()
        self.save()

    def forget_remote(self, remote: str) -> bool:
        remotes = self._data.get("remotes") or {}
        if remote in remotes:
            del remotes[remote]
            self.save()
            return True
        return False

    def list_all(self) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        default = self.get_default()
        if default:
            rows.append(("default", default))
        remotes = self._data.get("remotes") or {}
        for key in sorted(remotes):
            rows.append((key, remotes[key]))
        return rows

    def resolve(self, remote: str, explicit: str | None = None) -> str | None:
        """Explicit pin wins, then per-remote, then default."""
        if explicit:
            return explicit.strip()
        pinned = self.get_remote(remote)
        if pinned:
            return pinned
        return self.get_default()


def resolve_verify_identity(
    remote: str,
    *,
    explicit: str | None = None,
    insecure: bool = False,
    config_dir: str | None = None,
) -> str | None:
    """
    Resolve signer identity for release verification.

    When insecure is True, return None (rngit still validates crypto without pin).
    """
    if insecure:
        return None
    return TrustStore(config_dir).resolve(remote, explicit=explicit)
