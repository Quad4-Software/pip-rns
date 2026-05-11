"""pipx-rns CLI: pipx-only variant with install/inject/update/list/uninstall."""

from __future__ import annotations

import argparse
import os

from .aliases import init as alias_init
from .core import inject, install, list_packages, uninstall
from .core import update as update_fn
from .indexes import init as index_init
from .ui import init as ui_init


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pipx-rns",
        description="Install Python packages from Reticulum (rns://) via pipx",
        epilog=(
            "Examples:\n"
            "  pipx-rns install 926baefe13daf5178c174f158dae1b45/quad4/LXMFy\n"
            "  pipx-rns install repo@v1.0.0\n"
            "  pipx-rns inject myvenv 926baefe.../quad4/MyApp\n"
            "  pipx-rns update 926baefe13daf5178c174f158dae1b45/quad4/LXMFy"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument(
        "--config", metavar="DIR", help="Config directory for aliases",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("install", help="Install a package from a remote via pipx")
    p.add_argument("remote")
    p.add_argument("--ref", metavar="TAG", help="Git tag, branch or commit to checkout")
    p.add_argument("--editable", "-e", action="store_true")
    p.add_argument(
        "--use-cache", action="store_true",
        help="Cache clone locally; reuse cache when offline",
    )
    p.add_argument(
        "--from-release", action="store_true",
        help="Download and install a .whl from a release instead of cloning source",
    )
    p.add_argument(
        "--verify", metavar="IDENTITY",
        help="Verify .rsg signature with rnid before installing (requires --from-release)",
    )
    p.add_argument("extra", nargs="*")

    p = sub.add_parser("inject", help="Inject a package into an existing pipx venv")
    p.add_argument("venv", help="Name of the target pipx venv")
    p.add_argument("remote")
    p.add_argument("--ref", metavar="TAG")
    p.add_argument("--use-cache", action="store_true")
    p.add_argument("extra", nargs="*")

    p = sub.add_parser(
        "update", help="Force-reinstall a package from a remote via pipx",
    )
    p.add_argument("remote")
    p.add_argument("--ref", metavar="TAG")
    p.add_argument("--use-cache", action="store_true")
    p.add_argument("--from-release", action="store_true")
    p.add_argument(
        "--verify", metavar="IDENTITY",
        help="Verify .rsg signature with rnid before installing (requires --from-release)",
    )
    p.add_argument("extra", nargs="*")

    sub.add_parser("list", help="List pipx-installed packages")

    p = sub.add_parser("uninstall", help="Uninstall a pipx-installed package")
    p.add_argument("package")

    args = parser.parse_args()
    ui_init(no_color=args.no_color)

    cfg = getattr(args, "config", None) or os.environ.get("PIP_RNS_CONFIG")
    alias_init(cfg)
    index_init()

    ref = getattr(args, "ref", None)
    use_cache = getattr(args, "use_cache", False)
    from_release = getattr(args, "from_release", False)
    verify_identity = getattr(args, "verify", None)

    if args.command == "install":
        install(
            args.remote, installer="pipx", editable=args.editable,
            extra_args=args.extra or None, ref=ref, use_cache=use_cache,
            from_release=from_release, verify_identity=verify_identity,
        )
    elif args.command == "inject":
        inject(
            args.remote, args.venv, extra_args=args.extra or None,
            ref=ref, use_cache=use_cache,
        )
    elif args.command == "update":
        update_fn(
            args.remote, installer="pipx",
            extra_args=args.extra or None, ref=ref, use_cache=use_cache,
            from_release=from_release, verify_identity=verify_identity,
        )
    elif args.command == "list":
        list_packages(installer="pipx")
    elif args.command == "uninstall":
        uninstall(args.package, installer="pipx")


if __name__ == "__main__":
    main()
