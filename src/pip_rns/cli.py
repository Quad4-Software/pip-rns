"""pip-rns CLI: install/update/list/uninstall packages from custom protocol remotes."""

from __future__ import annotations

import argparse
import os
import sys

from .aliases import get_manager as get_alias_mgr
from .aliases import init as alias_init
from .bundle_cmd import dispatch as bundle_dispatch
from .bundle_cmd import register_parsers as register_bundle_parsers
from .completion_cmd import install_completions
from .core import install, list_packages, uninstall
from .core import update as update_fn
from .doctor import print_doctor, run_doctor
from .indexes import get_manager as get_index_mgr
from .indexes import init as index_init
from .installer import InstallerError, format_installer_error
from .releases import list_releases, release_info
from .ui import bold, dim, green, header, init as ui_init
from .venv_prefs import VenvPrefs
from .version import __version__


def _add_common_install_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--pipx", action="store_true", help="Use pipx instead of pip")
    p.add_argument("--uv", action="store_true", help="Use uv instead of pip")
    p.add_argument(
        "--poetry",
        action="store_true",
        help="Use poetry add instead of pip",
    )
    p.add_argument(
        "--ref",
        metavar="TAG",
        help="Git tag, branch or commit to checkout",
    )
    p.add_argument(
        "--editable",
        "-e",
        action="store_true",
        help="Install in editable mode (persistent clone)",
    )
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
        action="store_true",
        help="Force clone/install from source (skip release probe)",
    )
    p.add_argument(
        "--verify",
        metavar="IDENTITY",
        help=(
            "Pin required release signer identity. "
            "Release .rsm/.rsg are verified by default via rngit"
        ),
    )
    p.add_argument(
        "--remember-venv",
        action="store_true",
        help="Remember --venv for this remote without prompting",
    )
    p.add_argument(
        "--forget-venv",
        action="store_true",
        help="Forget any remembered venv for this remote",
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
        epilog=(
            "Examples:\n"
            "  pip-rns install 06a54b505bb67b25ef3f8097e8001edc/public/LXMFy\n"
            "  pip-rns install --pipx repo@v1.0.0\n"
            "  pip-rns alias add myapp 06a54b50.../public/MyApp\n"
            "  pip-rns install myapp -- --break-system-packages\n"
            "  pip-rns index add rns://identity/group/index\n"
            "  pip-rns index sync && pip-rns index search lxmf\n"
            "  pip-rns doctor\n"
            "  pip-rns completion install"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version="pip-rns {0}".format(__version__),
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
        help="Config directory for aliases + indexes",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("install", help="Install a package from a remote")
    p.add_argument(
        "remote",
        help="Remote path, rns:// URL, alias name, or index package",
    )
    _add_common_install_args(p)
    p.add_argument("--venv", metavar="PATH", help="Install into a virtualenv at PATH")
    p.add_argument("extra", nargs="*", help="Extra arguments passed to the installer")

    p = sub.add_parser(
        "update", help="Reinstall a package from a remote (force latest)"
    )
    p.add_argument("remote")
    _add_common_install_args(p)
    p.add_argument("--venv", metavar="PATH")
    p.add_argument("extra", nargs="*")

    p = sub.add_parser("list", help="List installed packages")
    p.add_argument("--pipx", action="store_true")
    p.add_argument("--uv", action="store_true")
    p.add_argument("--poetry", action="store_true")

    p = sub.add_parser("uninstall", help="Uninstall a package")
    p.add_argument("package")
    p.add_argument("--pipx", action="store_true")
    p.add_argument("--uv", action="store_true")
    p.add_argument("--poetry", action="store_true")

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

    p = sub.add_parser("index", help="Manage remote package indexes")
    ip = p.add_subparsers(dest="index_command", required=True)
    a = ip.add_parser("add", help="Register an index URL")
    a.add_argument("url")
    a = ip.add_parser("rm", help="Remove and re-sync an index")
    a.add_argument("url")
    ip.add_parser("ls", help="List registered indexes")
    ip.add_parser("sync", help="Clone/pull all indexes and cache package names")
    a = ip.add_parser("list", help="List all available packages from synced indexes")
    a = ip.add_parser("search", help="Search packages by name across synced indexes")
    a.add_argument("query")
    ip.add_parser("packages", help=argparse.SUPPRESS)

    p = sub.add_parser("release", help="Manage and inspect releases on remote repos")
    rp = p.add_subparsers(dest="release_command", required=True)
    a = rp.add_parser("list", help="List releases for a remote repo")
    a.add_argument("remote", help="rns:// URL of the repository")
    a = rp.add_parser("view", help="View details of a specific release")
    a.add_argument("remote")
    a.add_argument("tag")

    p = sub.add_parser("venv", help="Remembered virtualenv destinations")
    vp = p.add_subparsers(dest="venv_command", required=True)
    vp.add_parser("list", help="List remembered venvs")
    a = vp.add_parser("set", help="Set remembered venv (remote URL or 'default')")
    a.add_argument("name", help="Remote rns:// URL or 'default'")
    a.add_argument("path", help="Virtualenv path")
    a = vp.add_parser("forget", help="Forget remembered venv")
    a.add_argument("name", help="Remote rns:// URL or 'default'")

    p = sub.add_parser("doctor", help="Check pip-rns environment health")
    p.add_argument(
        "--online",
        action="store_true",
        help="Also probe release list for a remote you choose",
    )
    p.add_argument(
        "--remote",
        metavar="RNS_URL",
        default=None,
        help="Remote to probe with --online (required when --online is set)",
    )

    p = sub.add_parser("completion", help="Install shell completions")
    cp = p.add_subparsers(dest="completion_command", required=True)
    a = cp.add_parser("install", help="Install completions for the current shell")
    a.add_argument(
        "--shell",
        choices=("bash", "zsh", "fish"),
        default=None,
        help="Shell (default: detect from $SHELL)",
    )
    a.add_argument(
        "--dry-run", action="store_true", help="Show actions without copying"
    )

    register_bundle_parsers(sub)

    args = parser.parse_args()
    ui_init(no_color=args.no_color)
    no_interactive = bool(getattr(args, "no_interactive", False))

    inst = (
        "poetry"
        if getattr(args, "poetry", False)
        else "pipx"
        if getattr(args, "pipx", False)
        else "uv"
        if getattr(args, "uv", False)
        else "pip"
    )

    if args.command == "alias":
        alias_init(_config(args))
        alias_mgr = get_alias_mgr()
        assert alias_mgr is not None
        if args.alias_command in ("add", "set"):
            alias_mgr.set(args.name, args.remote)
            print(f"{green('✔')} alias {bold(args.name)} \u2192 {args.remote}")
        elif args.alias_command == "rm":
            alias_mgr.remove(args.name)
            print(f"{green('✔')} alias {bold(args.name)} removed")
        elif args.alias_command == "ls":
            for name, remote in alias_mgr.list().items():
                print(f"{name}={remote}")
        return

    if args.command == "index":
        index_init()
        index_mgr = get_index_mgr()
        assert index_mgr is not None
        if args.index_command == "add":
            index_mgr.add(args.url)
            print(f"{green('✔')} index added: {args.url}")
        elif args.index_command == "rm":
            index_mgr.remove(args.url)
            print(f"{green('✔')} index removed: {args.url}")
        elif args.index_command == "ls":
            for url in index_mgr.list():
                print(url)
        elif args.index_command == "sync":
            print(f"{header('⤵ Syncing indexes')}")
            index_mgr.sync()
            count = len(index_mgr.packages())
            print(f"{green('✔')} {count} package{'s' if count != 1 else ''} synced")
        elif args.index_command in ("list", "packages"):
            for name, remote in sorted(index_mgr.packages().items()):
                print(f"{name}={remote}")
        elif args.index_command == "search":
            results = index_mgr.search(args.query)
            if results:
                for name, remote in sorted(results.items()):
                    print(f"{name}={remote}")
            else:
                print(f"  no packages match {bold(repr(args.query))}")
        return

    if args.command == "release":
        if args.release_command == "list":
            print(f"{header('⤵ Releases')} {bold(args.remote)}")
            for rel in list_releases(args.remote):
                tag = rel.get("tag", "?")
                status = dim(rel.get("status", ""))
                print(f"  {bold(tag)} {status}")
        elif args.release_command == "view":
            info = release_info(args.remote, args.tag)
            print(f"{header('⤵ Release')} {bold(info.get('tag', args.tag))}")
            print(f"  status: {info.get('status', '?')}")
            print("  artifacts:")
            for a in info.get("artifacts", []):
                print(f"    - {a['name']} ({a['size']})")
        return

    if args.command == "bundle":
        bundle_dispatch(args, _config(args))
        return

    if args.command == "doctor":
        print(f"{header('⤵ Doctor')}")
        code = print_doctor(
            run_doctor(
                online=args.online,
                online_remote=args.remote,
                config_dir=_config(args),
            )
        )
        raise SystemExit(code)

    if args.command == "completion":
        if args.completion_command == "install":
            try:
                lines = install_completions(shell=args.shell, dry_run=args.dry_run)
            except (ValueError, FileNotFoundError) as exc:
                print(str(exc), file=sys.stderr)
                raise SystemExit(1) from exc
            for line in lines:
                print(line)
        return

    if args.command == "venv":
        prefs = VenvPrefs(_config(args))
        if args.venv_command == "list":
            rows = prefs.list_all()
            if not rows:
                print("No remembered venvs.")
            for name, path in rows:
                print(f"{name}\t{path}")
        elif args.venv_command == "set":
            if args.name == "default":
                prefs.set_default(args.path)
            else:
                prefs.set_remote(args.name, args.path)
            print(f"{green('✔')} remembered {args.name} -> {args.path}")
        elif args.venv_command == "forget":
            ok = (
                prefs.forget_default()
                if args.name == "default"
                else prefs.forget_remote(args.name)
            )
            if ok:
                print(f"{green('✔')} forgot {args.name}")
            else:
                print(f"No remembered venv for {args.name}")
        return

    _boot(args)

    venv = getattr(args, "venv", None)
    ref = getattr(args, "ref", None)
    use_cache = getattr(args, "use_cache", False)
    from_release = getattr(args, "from_release", False)
    from_source = getattr(args, "from_source", False)
    verify_identity = getattr(args, "verify", None)

    if from_release and from_source:
        print("Use either --from-release or --from-source, not both.", file=sys.stderr)
        raise SystemExit(2)

    install_kwargs = dict(
        installer=inst,
        editable=getattr(args, "editable", False),
        extra_args=getattr(args, "extra", None) or None,
        venv=venv,
        ref=ref,
        use_cache=use_cache,
        from_release=from_release,
        from_source=from_source,
        verify_identity=verify_identity,
        venv_explicit=venv is not None,
        remember_venv=getattr(args, "remember_venv", False),
        forget_venv=getattr(args, "forget_venv", False),
        no_interactive=no_interactive,
        config_dir=_config(args),
    )

    if args.command == "install":
        try:
            install(args.remote, **install_kwargs)
        except InstallerError as exc:
            print(format_installer_error(exc), file=sys.stderr)
            raise SystemExit(1) from exc
    elif args.command == "update":
        try:
            update_fn(args.remote, **install_kwargs)
        except InstallerError as exc:
            print(format_installer_error(exc), file=sys.stderr)
            raise SystemExit(1) from exc
    elif args.command == "list":
        list_packages(installer=inst)
    elif args.command == "uninstall":
        uninstall(args.package, installer=inst)


if __name__ == "__main__":
    main()
