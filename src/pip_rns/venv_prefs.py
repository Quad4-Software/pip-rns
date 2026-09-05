# Copyright (c) 2026, Quad4 (quad4.io)
"""Remembered virtualenv destinations for pip-rns installs."""

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


class VenvPrefs:
    """JSON-backed preferred venv paths (default + per-remote)."""

    def __init__(self, config_dir: str | None = None) -> None:
        self._dir = _default_config_dir(config_dir)
        self._path = self._dir / "venvs.json"
        self._data: dict[str, Any] = {"default": None, "remotes": {}}
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(raw, dict):
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

    def get_default(self) -> str | None:
        val = self._data.get("default")
        return str(val) if val else None

    def set_default(self, path: str) -> None:
        self._data["default"] = str(Path(path).expanduser().resolve())
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

    def set_remote(self, remote: str, path: str) -> None:
        remotes = self._data.setdefault("remotes", {})
        remotes[remote] = str(Path(path).expanduser().resolve())
        self.save()

    def forget_remote(self, remote: str) -> bool:
        remotes = self._data.get("remotes") or {}
        if remote in remotes:
            del remotes[remote]
            self._data["remotes"] = remotes
            self.save()
            return True
        return False

    def resolve(self, remote: str, cli_venv: str | None = None) -> str | None:
        """CLI --venv > per-remote > default > None."""
        if cli_venv:
            return str(Path(cli_venv).expanduser().resolve())
        remembered = self.get_remote(remote)
        if remembered:
            return remembered
        return self.get_default()

    def list_all(self) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        default = self.get_default()
        if default:
            rows.append(("default", default))
        remotes = self._data.get("remotes") or {}
        rows.extend((key, remotes[key]) for key in sorted(remotes))
        return rows


def maybe_remember_venv(
    prefs: VenvPrefs,
    remote: str,
    venv: str | None,
    *,
    venv_explicit: bool = False,
    remember: bool = False,
    forget: bool = False,
    no_interactive: bool = False,
) -> None:
    """Save or prompt to remember venv after a successful install."""
    from opip.interactive import is_noninteractive

    if forget:
        prefs.forget_remote(remote)
        return
    if not venv:
        return
    if remember:
        prefs.set_remote(remote, venv)
        print(f"Remembered venv for {remote}: {venv}")
        return
    if not venv_explicit or is_noninteractive(no_interactive):
        return
    existing = prefs.get_remote(remote)
    if existing and os.path.abspath(existing) == os.path.abspath(venv):
        return
    try:
        sys_stdout_write = __import__("sys").stdout.write
        sys_stdout_flush = __import__("sys").stdout.flush
        sys_stdout_write(f"Remember {venv} for {remote}? [y/N] ")
        sys_stdout_flush()
        answer = input().strip().lower()
    except EOFError:
        answer = ""
    if answer in ("y", "yes"):
        prefs.set_remote(remote, venv)
        print(f"Remembered venv for {remote}: {venv}")
