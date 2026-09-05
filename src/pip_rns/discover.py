# Copyright (c) 2026, Quad4 (quad4.io)
"""Discover rngit repository nodes via Reticulum announces."""

from __future__ import annotations

import contextlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RNGIT_ASPECT = "git.repositories"


@dataclass
class DiscoveredNode:
    """An announced rngit repositories destination."""

    destination_hash: str
    identity_hash: str | None = None
    node_name: str | None = None
    heard_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "destination_hash": self.destination_hash,
            "identity_hash": self.identity_hash,
            "node_name": self.node_name,
            "heard_at": self.heard_at,
        }


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


class DiscoverStore:
    """Persist recently discovered rngit nodes and Python packages."""

    def __init__(self, config_dir: str | None = None) -> None:
        self._dir = _default_config_dir(config_dir)
        self._path = self._dir / "discovered.json"
        self._nodes: dict[str, DiscoveredNode] = {}
        self._packages: dict[str, dict[str, Any]] = {}
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        items = raw.get("nodes") or []
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            dest = item.get("destination_hash")
            if not dest:
                continue
            self._nodes[str(dest)] = DiscoveredNode(
                destination_hash=str(dest),
                identity_hash=(
                    str(item["identity_hash"]) if item.get("identity_hash") else None
                ),
                node_name=str(item["node_name"]) if item.get("node_name") else None,
                heard_at=float(item.get("heard_at") or 0.0),
            )
        pkgs = raw.get("packages") or []
        if isinstance(pkgs, list):
            for item in pkgs:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                remote = item.get("remote")
                if name and remote:
                    self._packages[str(name).lower()] = dict(item)

    def save(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "nodes": [
                n.as_dict()
                for n in sorted(
                    self._nodes.values(),
                    key=lambda x: (-x.heard_at, x.destination_hash),
                )
            ],
            "packages": [self._packages[k] for k in sorted(self._packages.keys())],
        }
        self._path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def upsert(self, node: DiscoveredNode) -> None:
        self._nodes[node.destination_hash] = node

    def merge(self, nodes: list[DiscoveredNode]) -> int:
        for node in nodes:
            prev = self._nodes.get(node.destination_hash)
            if prev and not node.node_name and prev.node_name:
                node.node_name = prev.node_name
            if prev and not node.identity_hash and prev.identity_hash:
                node.identity_hash = prev.identity_hash
            self._nodes[node.destination_hash] = node
        self.save()
        return len(nodes)

    def merge_packages(self, packages: list[Any]) -> int:
        """Merge scanned packages. Accepts DiscoveredPackage or dict."""
        count = 0
        for pkg in packages:
            if hasattr(pkg, "as_dict"):
                data = pkg.as_dict()
            elif isinstance(pkg, dict):
                data = dict(pkg)
            else:
                continue
            name = str(data.get("name") or "").lower()
            if not name or not data.get("remote"):
                continue
            data["name"] = name
            prev = self._packages.get(name)
            if prev and prev.get("has_wheel") and not data.get("has_wheel"):
                data["has_wheel"] = True
                data["latest_tag"] = data.get("latest_tag") or prev.get("latest_tag")
            self._packages[name] = data
            count += 1
        self.save()
        return count

    def list_nodes(self) -> list[DiscoveredNode]:
        return sorted(
            self._nodes.values(),
            key=lambda x: (-x.heard_at, x.destination_hash),
        )

    def list_packages(self) -> list[dict[str, Any]]:
        return [self._packages[k] for k in sorted(self._packages.keys())]

    def get_package(self, name: str) -> dict[str, Any] | None:
        """Return full package metadata for a short name, or None."""
        key = name.strip().lower()
        if not key:
            return None
        item = self._packages.get(key)
        if not item:
            return None
        return dict(item)

    def resolve_package(self, name: str) -> str | None:
        """Resolve a short package name to an rns:// remote."""
        item = self.get_package(name)
        if not item:
            return None
        remote = item.get("remote")
        return str(remote) if remote else None

    def clear(self) -> int:
        n = len(self._nodes)
        self._nodes.clear()
        self._packages.clear()
        self.save()
        return n

    def clear_packages(self) -> int:
        n = len(self._packages)
        self._packages.clear()
        self.save()
        return n


def _decode_node_name(app_data: Any) -> str | None:
    if app_data is None:
        return None
    if isinstance(app_data, bytes):
        text = app_data.decode("utf-8", errors="replace")
    else:
        text = str(app_data)
    line = text.splitlines()[0].strip() if text else ""
    return line[:120] or None


class _GitReposHandler:
    aspect_filter = RNGIT_ASPECT

    def __init__(self) -> None:
        self.found: dict[str, DiscoveredNode] = {}

    def received_announce(
        self,
        destination_hash,
        announced_identity,
        app_data,
        *args,
    ) -> None:
        dest = (
            destination_hash.hex()
            if hasattr(destination_hash, "hex")
            else bytes(destination_hash).hex()
        )
        identity = None
        if announced_identity is not None and hasattr(announced_identity, "hash"):
            identity = announced_identity.hash.hex()
        self.found[dest] = DiscoveredNode(
            destination_hash=dest,
            identity_hash=identity,
            node_name=_decode_node_name(app_data),
            heard_at=time.time(),
        )


def _import_rns():
    """Import RNS. Soft dependency for discovery only."""
    import RNS

    return RNS


def discover_nodes(
    *,
    seconds: float = 30.0,
    reticulum_config: str | None = None,
    on_announce=None,
) -> list[DiscoveredNode]:
    """Listen for rngit git.repositories announces.

    Requires the RNS Python package (same stack as rngit).
    Soft dependency so pip-rns still installs without RNS.
    """
    try:
        RNS = _import_rns()
    except ImportError as exc:
        raise RuntimeError(
            "RNS is required for discovery. Install with: pip install rns",
        ) from exc

    # Keep a reference so Reticulum stays initialized for the listen window
    _reticulum = RNS.Reticulum(configdir=reticulum_config)
    del _reticulum

    handler = _GitReposHandler()

    class _Handler:
        aspect_filter = RNGIT_ASPECT

        def received_announce(
            self,
            destination_hash,
            announced_identity,
            app_data,
            *args,
        ):
            handler.received_announce(
                destination_hash,
                announced_identity,
                app_data,
                *args,
            )
            if on_announce is not None:
                dest = (
                    destination_hash.hex()
                    if hasattr(destination_hash, "hex")
                    else bytes(destination_hash).hex()
                )
                node = handler.found.get(dest)
                if node is not None:
                    on_announce(node)

    h = _Handler()
    RNS.Transport.register_announce_handler(h)
    try:
        time.sleep(max(0.0, float(seconds)))
    finally:
        with contextlib.suppress(Exception):
            RNS.Transport.deregister_announce_handler(h)

    return sorted(
        handler.found.values(),
        key=lambda n: (n.node_name or "", n.destination_hash),
    )


def format_node_line(node: DiscoveredNode) -> str:
    name = node.node_name or "-"
    return f"{node.destination_hash}\t{name}"
