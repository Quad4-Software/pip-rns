"""pip-rns CLI: install/update/list/uninstall packages from custom protocol remotes."""

from __future__ import annotations

import argparse
import os

from .aliases import get_manager as get_alias_mgr
from .aliases import init as alias_init
from .core import install, list_packages, uninstall
from .core import update as update_fn
from .indexes import get_manager as get_index_mgr
from .indexes import init as index_init
from .ui import bold, green, header, init as ui_init


def _add_common_install_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--pipx", action="store_true", help="Use pipx instead of pip")
    p.add_argument("--uv", action="store_true", help="Use uv instead of pip")
    p.add_argument(
        "--poetry", action="store_true", help="Use poetry add instead of pip",
    )
    p.add_argument(
        "--ref", metavar="TAG", help="Git tag, branch or commit to checkout",
    )
    p.add_argument(
        "--editable", "-e", action="store_true",
        help="Install in editable mode (persistent clone)",
    )
    p.add_argument(
        "--use-cache", action="store_true",
        help="Cache clone locally; reuse cache when offline",
    )


def _config(args) -> str | None:
    return getattr(args, "config", None) or os.environ.get("PIP_RNS_CONFIG")


def _boot(args) -> None:
    alias_init(_config(args))
    index_init()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pip-rns",
        description="Install Python packages from Reticulum (rns://) remotes",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument(
        "--config", metavar="DIR", help="Config directory for aliases + indexes",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- install ---
    p = sub.add_parser("install", help="Install a package from a remote")
    p.add_argument(
        "remote", help="Remote path, rns:// URL, alias name, or index package",
    )
    _add_common_install_args(p)
    p.add_argument("--venv", metavar="PATH", help="Install into a virtualenv at PATH")
    p.add_argument("extra", nargs="*", help="Extra arguments passed to the installer")

    # --- update ---
    p = sub.add_parser("update", help="Reinstall a package from a remote (force latest)")
    p.add_argument("remote")
    _add_common_install_args(p)
    p.add_argument("--venv", metavar="PATH")
    p.add_argument("extra", nargs="*")

    # --- list ---
    p = sub.add_parser("list", help="List installed packages")
    p.add_argument("--pipx", action="store_true")
    p.add_argument("--uv", action="store_true")
    p.add_argument("--poetry", action="store_true")

    # --- uninstall ---
    p = sub.add_parser("uninstall", help="Uninstall a package")
    p.add_argument("package")
    p.add_argument("--pipx", action="store_true")
    p.add_argument("--uv", action="store_true")
    p.add_argument("--poetry", action="store_true")

    # --- alias ---
    p = sub.add_parser("alias", help="Manage local aliases")
    asp = p.add_subparsers(dest="alias_command", required=True)

    a = asp.add_parser("add", help="Create an alias")
    a.add_argument("name")
    a.add_argument("remote")

    a = asp.add_parser("set", help="Create or update an alias")
    a.add_argument("name")
    a.add_argument("remote")

    a = asp.add_parser("rm", help="Remove an alias")
    a.add_argument("name")

    a = asp.add_parser("ls", help="List all aliases")

    # --- index ---
    p = sub.add_parser("index", help="Manage remote package indexes")
    ip = p.add_subparsers(dest="index_command", required=True)

    a = ip.add_parser("add", help="Register an index URL")
    a.add_argument("url")

    a = ip.add_parser("rm", help="Remove and re-sync an index")
    a.add_argument("url")

    ip.add_parser("ls", help="List registered indexes")

    ip.add_parser("sync", help="Clone/pull all indexes and cache package names")

    ip.add_parser("packages", help="List all available packages from synced indexes")

    args = parser.parse_args()
    ui_init(no_color=args.no_color)

    inst = (
        "poetry" if getattr(args, "poetry", False)
        else "pipx" if getattr(args, "pipx", False)
        else "uv" if getattr(args, "uv", False)
        else "pip"
    )

    if args.command == "alias":
        alias_init(_config(args))
        mgr = get_alias_mgr()
        if args.alias_command in ("add", "set"):
            mgr.set(args.name, args.remote)
            print(f"{green('✔')} alias {bold(args.name)} \u2192 {args.remote}")
        elif args.alias_command == "rm":
            mgr.remove(args.name)
            print(f"{green('✔')} alias {bold(args.name)} removed")
        elif args.alias_command == "ls":
            for name, remote in mgr.list().items():
                print(f"{name}={remote}")
        return

    if args.command == "index":
        index_init()
        mgr = get_index_mgr()
        if args.index_command == "add":
            mgr.add(args.url)
            print(f"{green('✔')} index added: {args.url}")
        elif args.index_command == "rm":
            mgr.remove(args.url)
            print(f"{green('✔')} index removed: {args.url}")
        elif args.index_command == "ls":
            for url in mgr.list():
                print(url)
        elif args.index_command == "sync":
            print(f"{header('⤵ Syncing indexes')}")
            mgr.sync()
            count = len(mgr.packages())
            print(f"{green('✔')} {count} package{'s' if count != 1 else ''} synced")
        elif args.index_command == "packages":
            for name, remote in sorted(mgr.packages().items()):
                print(f"{name}={remote}")
        return

    _boot(args)
    venv = getattr(args, "venv", None)
    ref = getattr(args, "ref", None)
    use_cache = getattr(args, "use_cache", False)

    if args.command == "install":
        install(
            args.remote, installer=inst, editable=args.editable,
            extra_args=args.extra or None, venv=venv, ref=ref,
            use_cache=use_cache,
        )
    elif args.command == "update":
        update_fn(
            args.remote, installer=inst, editable=args.editable,
            extra_args=args.extra or None, venv=venv, ref=ref,
            use_cache=use_cache,
        )
    elif args.command == "list":
        list_packages(installer=inst)
    elif args.command == "uninstall":
        uninstall(args.package, installer=inst)


if __name__ == "__main__":
    main()
