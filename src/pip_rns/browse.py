"""Guided browse: listen, save, scan, alias, and optional install."""

from __future__ import annotations

import sys
from typing import Callable

from opip.interactive import is_noninteractive

from .aliases import get_manager as get_alias_mgr
from .catalog import offer_package_picker
from .discover import DiscoverStore, discover_nodes
from .discover_scan import (
    DiscoveredPackage,
    format_package_line,
    install_hint,
    maybe_auto_alias,
    scan_nodes,
)
from .ui import bold, dim, green, header


def run_browse(
    *,
    config_dir: str | None = None,
    seconds: float = 60.0,
    reticulum_config: str | None = None,
    no_listen: bool = False,
    no_scan: bool = False,
    check_releases: bool = True,
    auto_alias: bool = False,
    do_install: bool = False,
    no_interactive: bool = False,
    on_status: Callable[[str], None] | None = None,
    install_kwargs: dict | None = None,
) -> list[DiscoveredPackage]:
    """Listen for rngit nodes, scan for Python packages, optionally alias and install.

    Returns cataloged packages after scan (may be empty).
    """
    status = on_status or (lambda m: print(f"  {dim(m)}"))
    store = DiscoverStore(config_dir)
    noninteractive = is_noninteractive(no_interactive)
    pkgs: list[DiscoveredPackage] = []

    if not no_listen:
        if noninteractive:
            print(
                "Non-interactive: skipping listen. Use saved nodes or drop --no-interactive.",
                file=sys.stderr,
            )
        else:
            print(
                f"{header('Browse')} listening for "
                f"{bold('git.repositories')} "
                f"{dim(f'({seconds:g}s)')}",
            )

            def _on_node(node):
                label = node.node_name or "-"
                print(f"  {green('heard')} {node.destination_hash}  {dim(label)}")

            nodes = discover_nodes(
                seconds=seconds,
                reticulum_config=reticulum_config,
                on_announce=_on_node,
            )
            if nodes:
                store.merge(nodes)
                print(f"{green('saved')} {len(nodes)} node(s)")
            else:
                print(f"  {dim('no announces heard')}")

    nodes = store.list_nodes()
    if no_scan:
        for raw in store.list_packages():
            pkg = DiscoveredPackage.from_dict(raw)
            if pkg is not None:
                pkgs.append(pkg)
    elif not nodes:
        if noninteractive:
            raise RuntimeError("No saved nodes. Run pip-rns browse on a TTY first.")
        print(f"  {dim('no nodes to scan')}")
    else:
        print(f"{header('Scan')} {len(nodes)} node(s) for Python packages")
        pkgs = scan_nodes(
            nodes,
            reticulum_config=reticulum_config,
            check_releases=check_releases,
            on_status=status,
        )
        store.merge_packages(pkgs)

    if pkgs:
        amgr = get_alias_mgr()
        if amgr is not None:
            created = maybe_auto_alias(
                pkgs,
                amgr,
                auto=auto_alias,
                no_interactive=no_interactive,
            )
            if created:
                print(f"{green('aliased')} {created} package(s)")

    catalog = store.list_packages()
    if catalog:
        print(f"{header('Packages')} {len(catalog)} in catalog")
        for raw in catalog:
            pkg = DiscoveredPackage.from_dict(raw)
            if pkg is None:
                continue
            print(f"  {format_package_line(pkg)}")
            print(f"    {dim(install_hint(pkg))}")
    else:
        print(f"  {dim('no Python packages found')}")

    should_offer = do_install or (not noninteractive and catalog and not no_interactive)
    if should_offer and (do_install or _prompt_install()):
        name = offer_package_picker(config_dir, no_interactive=no_interactive)
        from .core import install

        kwargs = dict(install_kwargs or {})
        kwargs.setdefault("no_interactive", no_interactive)
        kwargs.setdefault("config_dir", config_dir)
        install(name, **kwargs)

    out: list[DiscoveredPackage] = []
    for raw in catalog:
        pkg = DiscoveredPackage.from_dict(raw)
        if pkg is not None:
            out.append(pkg)
    return out


def _prompt_install() -> bool:
    try:
        answer = input("Install a package now? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("y", "yes")
