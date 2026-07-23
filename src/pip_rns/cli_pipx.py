"""pipx-rns CLI: pipx-only variant with install/inject/update/list/uninstall."""

from __future__ import annotations

import argparse
import os
import sys

from .aliases import init as alias_init
from .completion_cmd import install_completions
from .core import inject, install, list_packages, uninstall
from .core import update as update_fn
from .doctor import print_doctor, run_doctor
from .indexes import init as index_init
from .installer import InstallerError, format_installer_error
from .errors import UserCancelled
from .ui import header, init as ui_init
from .version import __version__


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pipx-rns",
        description="Install Python packages from Reticulum (rns://) via pipx",
        epilog=(
            "Examples:\n"
            "  pipx-rns install 06a54b505bb67b25ef3f8097e8001edc/public/LXMFy\n"
            "  pipx-rns install repo@v1.0.0\n"
            "  pipx-rns inject myvenv 06a54b50.../public/MyApp\n"
            "  pipx-rns update 06a54b505bb67b25ef3f8097e8001edc/public/LXMFy"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version="pipx-rns {0}".format(__version__),
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Disable colored output"
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Never prompt (also: CI, PIP_RNS_NO_INTERACTIVE, non-TTY).",
    )
    parser.add_argument(
        "--config",
        metavar="DIR",
        help="Config directory for aliases",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("install", help="Install a package from a remote via pipx")
    p.add_argument("remote")
    p.add_argument("--ref", metavar="TAG", help="Git tag, branch or commit to checkout")
    p.add_argument("--editable", "-e", action="store_true")
    p.add_argument(
        "--use-cache",
        action="store_true",
        help="Cache clone locally; reuse cache when offline",
    )
    p.add_argument(
        "--from-release",
        action="store_true",
        help="Require a release .whl (fail if none)",
    )
    p.add_argument(
        "--from-source",
        "-s",
        action="store_true",
        help=(
            "Force clone/install from source (skip release probe). "
            "Also implied by branch-like refs such as @master or @main"
        ),
    )
    p.add_argument(
        "--verify",
        metavar="IDENTITY",
        help=(
            "Pin required release signer identity. "
            "Release .rsm/.rsg are verified by default via rngit"
        ),
    )
    p.add_argument("extra", nargs="*")

    p = sub.add_parser("inject", help="Inject a package into an existing pipx venv")
    p.add_argument("venv", help="Name of the target pipx venv")
    p.add_argument("remote")
    p.add_argument("--ref", metavar="TAG")
    p.add_argument("--use-cache", action="store_true")
    p.add_argument("extra", nargs="*")

    p = sub.add_parser(
        "update",
        help="Force-reinstall a package from a remote via pipx",
    )
    p.add_argument("remote")
    p.add_argument("--ref", metavar="TAG")
    p.add_argument("--use-cache", action="store_true")
    p.add_argument("--from-release", action="store_true")
    p.add_argument(
        "--from-source",
        "-s",
        action="store_true",
        help="Force clone from source (also implied by @master/@main)",
    )
    p.add_argument(
        "--verify",
        metavar="IDENTITY",
        help=(
            "Pin required release signer identity. "
            "Release .rsm/.rsg are verified by default via rngit"
        ),
    )
    p.add_argument("extra", nargs="*")

    sub.add_parser("list", help="List pipx-installed packages")

    p = sub.add_parser("uninstall", help="Uninstall a pipx-installed package")
    p.add_argument("package")

    p = sub.add_parser("doctor", help="Check pip-rns environment health")
    p.add_argument("--online", action="store_true")
    p.add_argument(
        "--remote",
        metavar="RNS_URL",
        default=None,
        help="Remote to probe with --online (required when --online is set)",
    )

    p = sub.add_parser("completion", help="Install shell completions")
    cp = p.add_subparsers(dest="completion_command", required=True)
    a = cp.add_parser("install", help="Install completions for the current shell")
    a.add_argument("--shell", choices=("bash", "zsh", "fish"), default=None)
    a.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    ui_init(no_color=args.no_color)
    no_interactive = bool(getattr(args, "no_interactive", False))

    cfg = getattr(args, "config", None) or os.environ.get("PIP_RNS_CONFIG")
    alias_init(cfg)
    index_init()

    if args.command == "doctor":
        print(f"{header('⤵ Doctor')}")
        raise SystemExit(
            print_doctor(
                run_doctor(
                    online=args.online,
                    online_remote=args.remote,
                    config_dir=cfg,
                )
            )
        )

    if args.command == "completion":
        if args.completion_command == "install":
            try:
                for line in install_completions(shell=args.shell, dry_run=args.dry_run):
                    print(line)
            except (ValueError, FileNotFoundError) as exc:
                print(str(exc), file=sys.stderr)
                raise SystemExit(1) from exc
        return

    ref = getattr(args, "ref", None)
    use_cache = getattr(args, "use_cache", False)
    from_release = getattr(args, "from_release", False)
    from_source = getattr(args, "from_source", False)
    verify_identity = getattr(args, "verify", None)

    if from_release and from_source:
        print("Use either --from-release or --from-source, not both.", file=sys.stderr)
        raise SystemExit(2)

    if args.command == "install":
        try:
            install(
                args.remote,
                installer="pipx",
                editable=args.editable,
                extra_args=args.extra or None,
                ref=ref,
                use_cache=use_cache,
                from_release=from_release,
                from_source=from_source,
                verify_identity=verify_identity,
                no_interactive=no_interactive,
                config_dir=cfg,
            )
        except UserCancelled as exc:
            print(str(exc) or "Cancelled.", file=sys.stderr)
            raise SystemExit(130) from exc
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            raise SystemExit(130)
        except InstallerError as exc:
            print(format_installer_error(exc), file=sys.stderr)
            raise SystemExit(1) from exc
    elif args.command == "inject":
        try:
            inject(
                args.remote,
                args.venv,
                extra_args=args.extra or None,
                ref=ref,
                use_cache=use_cache,
            )
        except UserCancelled as exc:
            print(str(exc) or "Cancelled.", file=sys.stderr)
            raise SystemExit(130) from exc
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            raise SystemExit(130)
        except InstallerError as exc:
            print(format_installer_error(exc), file=sys.stderr)
            raise SystemExit(1) from exc
    elif args.command == "update":
        try:
            update_fn(
                args.remote,
                installer="pipx",
                extra_args=args.extra or None,
                ref=ref,
                use_cache=use_cache,
                from_release=from_release,
                from_source=from_source,
                verify_identity=verify_identity,
                no_interactive=no_interactive,
                config_dir=cfg,
            )
        except UserCancelled as exc:
            print(str(exc) or "Cancelled.", file=sys.stderr)
            raise SystemExit(130) from exc
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            raise SystemExit(130)
        except InstallerError as exc:
            print(format_installer_error(exc), file=sys.stderr)
            raise SystemExit(1) from exc
    elif args.command == "list":
        list_packages(installer="pipx")
    elif args.command == "uninstall":
        uninstall(args.package, installer="pipx")


if __name__ == "__main__":
    main()
