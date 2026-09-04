"""Unified package catalog from aliases, indexes, and discovery."""

from __future__ import annotations

from dataclasses import dataclass

from opip.interactive import is_noninteractive

from .aliases import get_manager as get_alias_mgr
from .discover import DiscoverStore
from .errors import UserCancelled
from .indexes import get_manager as get_index_mgr
from .ui import bold, dim, yellow


@dataclass
class CatalogEntry:
    name: str
    remote: str
    source: str
    has_wheel: bool = False
    latest_tag: str | None = None


def _read_line(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError as exc:
        raise UserCancelled("Cancelled.") from exc
    except KeyboardInterrupt as exc:
        raise UserCancelled("Interrupted.") from exc


def all_entries(config_dir: str | None = None) -> list[CatalogEntry]:
    """Merge aliases, indexes, and discovered packages.

    Priority on name collision: alias > index > discover.
    """
    merged: dict[str, CatalogEntry] = {}

    store = DiscoverStore(config_dir)
    for raw in store.list_packages():
        name = str(raw.get("name", "")).strip().lower()
        remote = raw.get("remote")
        if not name or not remote:
            continue
        merged[name] = CatalogEntry(
            name=name,
            remote=str(remote),
            source="discover",
            has_wheel=bool(raw.get("has_wheel")),
            latest_tag=str(raw["latest_tag"]) if raw.get("latest_tag") else None,
        )

    imgr = get_index_mgr()
    if imgr is not None:
        for name, remote in imgr.packages().items():
            key = name.strip().lower()
            if not key:
                continue
            merged[key] = CatalogEntry(
                name=key,
                remote=remote,
                source="index",
            )

    amgr = get_alias_mgr()
    if amgr is not None:
        for name, remote in amgr.list().items():
            key = name.strip().lower()
            if not key:
                continue
            prev = merged.get(key)
            merged[key] = CatalogEntry(
                name=key,
                remote=remote,
                source="alias",
                has_wheel=prev.has_wheel if prev else False,
                latest_tag=prev.latest_tag if prev else None,
            )

    return [merged[k] for k in sorted(merged.keys())]


def search(query: str, config_dir: str | None = None) -> list[CatalogEntry]:
    """Substring search on package names."""
    q = query.strip().lower()
    if not q:
        return all_entries(config_dir)
    return [e for e in all_entries(config_dir) if q in e.name]


def offer_package_picker(
    config_dir: str | None = None,
    *,
    no_interactive: bool = False,
) -> str:
    """Interactive numbered picker. Returns selected package name.

    Raises UserCancelled on abort. Raises RuntimeError when non-interactive.
    """
    if is_noninteractive(no_interactive):
        raise RuntimeError(
            "No package specified. Use: pip-rns install <name> or pip-rns browse --install",
        )

    entries = all_entries(config_dir)
    if not entries:
        raise RuntimeError("No packages in catalog. Run: pip-rns browse")

    print(f"\n{yellow('Select a package to install')}")
    for i, entry in enumerate(entries[:50], start=1):
        wheel = (
            f"wheel:{entry.latest_tag}"
            if entry.has_wheel and entry.latest_tag
            else ("wheel" if entry.has_wheel else "no-wheel")
        )
        print(f"  {i}) {bold(entry.name)}  {dim(entry.source)}  {dim(wheel)}")
        print(f"     {dim(entry.remote)}")
    if len(entries) > 50:
        print(f"  {dim(f'... and {len(entries) - 50} more (use pip-rns search)')}")

    raw = _read_line("Pick number or name (q to quit): ")
    if not raw or raw.lower() in ("q", "quit", "abort"):
        raise UserCancelled("Aborted.")
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(entries[:50]):
            return entries[idx].name
        raise UserCancelled("Invalid selection.")
    key = raw.strip().lower()
    for entry in entries:
        if entry.name == key:
            return entry.name
    raise UserCancelled(f"Unknown package: {raw}")
