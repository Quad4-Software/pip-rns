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
from .discover import (
    DiscoverStore,
    discover_nodes,
    format_node_line,
)
from .discover_scan import (
    format_package_line,
    install_hint,
    scan_nodes,
)
from .doctor import print_doctor, run_doctor
from .export_cmd import export_release
from .indexes import get_manager as get_index_mgr
from .indexes import init as index_init
from .installer import InstallerError, format_installer_error
from .errors import UserCancelled
from .releases import list_releases, release_info
from .resolver import OfflineError
from .trust import TrustStore
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
        help="Cache clone locally. Reuse cache when offline",
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
            "Also uses pip-rns trust store when unset. "
            "Release .rsm/.rsg are verified by default via rngit"
        ),
    )
    p.add_argument(
        "--insecure",
        action="store_true",
        help=(
            "Allow install when signed release verification is not confirmed "
            "(fail-closed is the default)"
        ),
    )
    p.add_argument(
        "--offline",
        action="store_true",
        help="Use local cache / paths only (no RNS fetch or clone)",
    )
    p.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip expensive-clone confirmation prompts",
    )
    p.add_argument(
        "--require-release",
        action="store_true",
        help="Require a release wheel (no anonymous source tip)",
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


_COMMANDS = frozenset(
    {
        "install",
        "update",
        "list",
        "uninstall",
        "alias",
        "index",
        "release",
        "bundle",
        "doctor",
        "completion",
        "venv",
        "trust",
        "export",
        "discover",
    }
)


def _looks_like_remote(token: str) -> bool:
    if not token or token.startswith("-"):
        return False
    low = token.lower()
    if low.startswith("rns://"):
        return True
    # identity/group/repo or alias-ish path with a slash
    if "/" in token and "://" not in token:
        return True
    return False


def _inject_install_command(argv: list[str]) -> list[str]:
    """Allow `pip-rns rns://...` as shorthand for `pip-rns install rns://...`."""
    if len(argv) < 2:
        return argv
    # skip global flags before the first positional
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg in ("--version", "-h", "--help"):
            return argv
        if (
            arg.startswith("--")
            and "=" not in arg
            and arg
            in (
                "--no-color",
                "--no-interactive",
                "--config",
            )
        ):
            if arg == "--config" and i + 1 < len(argv):
                i += 2
                continue
            i += 1
            continue
        if arg.startswith("--config="):
            i += 1
            continue
        if arg.startswith("-"):
            i += 1
            continue
        break
    if i >= len(argv):
        return argv
    token = argv[i]
    if token in _COMMANDS:
        return argv
    if _looks_like_remote(token):
        return argv[:i] + ["install"] + argv[i:]
    return argv


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    else:
        argv = list(argv)
    argv = _inject_install_command(argv)

    parser = argparse.ArgumentParser(
        prog="pip-rns",
        description="Install Python packages from Reticulum (rns://) remotes",
        epilog=(
            "Examples:\n"
            "  pip-rns rns://id/group/repo\n"
            "  pip-rns install 06a54b505bb67b25ef3f8097e8001edc/public/LXMFy\n"
            "  pip-rns install --pipx repo@v1.0.0\n"
            "  pip-rns rns://id/group/repo@master\n"
            "  pip-rns export rns://id/group/repo -o ./mirror\n"
            "  pip-rns discover\n"
            "  pip-rns trust add rns://id/group/repo IDENTITY\n"
            "  pip-rns alias add myapp 06a54b50.../public/MyApp\n"
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

    p = sub.add_parser("trust", help="Trusted release publisher identities")
    tp = p.add_subparsers(dest="trust_command", required=True)
    a = tp.add_parser("add", help="Trust a signer for a remote (or set default)")
    a.add_argument(
        "remote_or_default",
        help="Remote rns:// URL, or 'default' for global default signer",
    )
    a.add_argument("identity", help="32-hex Reticulum identity hash")
    a = tp.add_parser("rm", help="Forget a trusted signer")
    a.add_argument(
        "remote_or_default",
        help="Remote rns:// URL, or 'default'",
    )
    tp.add_parser("ls", help="List trusted publishers")
    a = tp.add_parser("set-default", help="Set default signer identity")
    a.add_argument("identity")
    tp.add_parser("forget-default", help="Clear default signer")

    p = sub.add_parser(
        "export",
        help="Mirror release artifacts for sneakernet / offline sharing",
    )
    p.add_argument("remote", help="rns:// URL of the repository")
    p.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="DIR",
        help="Output directory for wheels and signatures",
    )
    p.add_argument("--ref", metavar="TAG", help="Release tag (default: latest)")
    p.add_argument(
        "--verify",
        metavar="IDENTITY",
        help="Pin required signer (else trust store)",
    )
    p.add_argument(
        "--insecure",
        action="store_true",
        help="Do not pin signer from trust store",
    )
    p.add_argument(
        "--all",
        action="store_true",
        dest="all_artifacts",
        help="Export all artifacts (not only the preferred .whl + .rsg)",
    )

    p = sub.add_parser(
        "discover",
        help="Listen for announced rngit repository nodes on Reticulum",
    )
    p.add_argument(
        "discover_command",
        nargs="?",
        default="listen",
        choices=("listen", "ls", "clear", "scan", "packages"),
        help="listen (default), ls, clear, scan, or packages",
    )
    p.add_argument(
        "--seconds",
        type=float,
        default=30.0,
        metavar="N",
        help="Listen duration in seconds (default: 30)",
    )
    p.add_argument(
        "--save",
        action="store_true",
        help="Remember heard nodes in the discover store",
    )
    p.add_argument(
        "--scan",
        action="store_true",
        help="After listen (or with scan), catalog Python packages on nodes",
    )
    p.add_argument(
        "--no-releases",
        action="store_true",
        help="Skip rngit release wheel checks during scan",
    )
    p.add_argument(
        "--reticulum-config",
        metavar="DIR",
        default=None,
        help="Reticulum config directory (default: ~/.reticulum)",
    )

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

    args = parser.parse_args(argv)
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

    if args.command == "trust":
        store = TrustStore(_config(args))
        if args.trust_command == "ls":
            rows = store.list_all()
            if not rows:
                print("No trusted publishers.")
            for name, identity in rows:
                print(f"{name}\t{identity}")
        elif args.trust_command == "add":
            if args.remote_or_default == "default":
                store.set_default(args.identity)
                print(f"{green('✔')} default signer -> {args.identity}")
            else:
                from .releases import _normalize_remote

                remote = _normalize_remote(args.remote_or_default)
                store.set_remote(remote, args.identity)
                print(f"{green('✔')} trusted {remote} -> {args.identity}")
        elif args.trust_command == "rm":
            if args.remote_or_default == "default":
                ok = store.forget_default()
            else:
                from .releases import _normalize_remote

                ok = store.forget_remote(_normalize_remote(args.remote_or_default))
            if ok:
                print(f"{green('✔')} forgot {args.remote_or_default}")
            else:
                print(f"No trust entry for {args.remote_or_default}")
        elif args.trust_command == "set-default":
            store.set_default(args.identity)
            print(f"{green('✔')} default signer -> {args.identity}")
        elif args.trust_command == "forget-default":
            if store.forget_default():
                print(f"{green('✔')} forgot default signer")
            else:
                print("No default signer set")
        return

    if args.command == "export":
        try:
            export_release(
                args.remote,
                args.output,
                ref=args.ref,
                verify_identity=args.verify,
                insecure=args.insecure,
                config_dir=_config(args),
                all_artifacts=args.all_artifacts,
            )
        except UserCancelled as exc:
            print(str(exc) or "Cancelled.", file=sys.stderr)
            raise SystemExit(130) from exc
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            raise SystemExit(130)
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        return

    if args.command == "discover":
        store = DiscoverStore(_config(args))
        cmd = args.discover_command or "listen"

        def _print_packages(pkgs: list) -> None:
            if not pkgs:
                print("No Python packages cataloged yet.")
                print(dim("Run: pip-rns discover scan"))
                return
            print(f"{header('⤵ Packages')} {len(pkgs)} from discovery")
            for raw in pkgs:
                from .discover_scan import DiscoveredPackage

                pkg = (
                    raw if hasattr(raw, "remote") else DiscoveredPackage.from_dict(raw)
                )
                if pkg is None:
                    continue
                print(f"  {format_package_line(pkg)}")
                print(f"    {dim(install_hint(pkg))}")

        if cmd == "ls":
            rows = store.list()
            if not rows:
                print("No discovered nodes saved.")
            for node in rows:
                print(format_node_line(node))
            pkgs = store.list_packages()
            if pkgs:
                print()
                _print_packages(pkgs)
            return
        if cmd == "packages":
            _print_packages(store.list_packages())
            return
        if cmd == "clear":
            n = store.clear()
            print(f"{green('✔')} cleared {n} discovered node(s)")
            return
        if cmd == "scan":
            nodes = store.list()
            if not nodes:
                print(
                    "No saved nodes. Run: pip-rns discover --save",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            print(f"{header('⤵ Scan')} {len(nodes)} node(s) for Python packages")
            try:
                pkgs = scan_nodes(
                    nodes,
                    reticulum_config=args.reticulum_config,
                    check_releases=not args.no_releases,
                    on_status=lambda m: print(f"  {dim(m)}"),
                )
            except Exception as exc:
                print(str(exc), file=sys.stderr)
                raise SystemExit(1) from exc
            store.merge_packages(pkgs)
            _print_packages(store.list_packages())
            if pkgs:
                print(
                    f"{green('✔')} {len(pkgs)} package(s) saved. "
                    f"Install with short name: pip-rns install <name>"
                )
            return

        print(
            f"{header('⤵ Discover')} listening for "
            f"{bold('git.repositories')} "
            f"{dim(f'({args.seconds:g}s)')}"
        )

        def _on_node(node):
            label = node.node_name or "-"
            print(f"  {green('heard')} {node.destination_hash}  {dim(label)}")

        try:
            nodes = discover_nodes(
                seconds=args.seconds,
                reticulum_config=args.reticulum_config,
                on_announce=_on_node,
            )
        except UserCancelled as exc:
            print(str(exc) or "Cancelled.", file=sys.stderr)
            raise SystemExit(130) from exc
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            raise SystemExit(130)
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc

        if args.save and nodes:
            store.merge(nodes)
            print(f"{green('✔')} saved {len(nodes)} node(s) to {store.path}")
        elif not nodes:
            print(f"  {dim('no announces heard in window')}")
        else:
            print(f"{dim('heard')} {len(nodes)} node(s) (pass --save to remember)")
            for node in nodes:
                print(f"  {format_node_line(node)}")

        if args.scan and nodes:
            if args.save:
                targets = store.list()
            else:
                targets = nodes
            print(f"{header('⤵ Scan')} {len(targets)} node(s) for Python packages")
            try:
                pkgs = scan_nodes(
                    targets,
                    reticulum_config=args.reticulum_config,
                    check_releases=not args.no_releases,
                    on_status=lambda m: print(f"  {dim(m)}"),
                )
            except Exception as exc:
                print(str(exc), file=sys.stderr)
                raise SystemExit(1) from exc
            store.merge_packages(pkgs)
            _print_packages(store.list_packages())
            if pkgs:
                print(f"{green('✔')} install with short name: pip-rns install <name>")
        return

    _boot(args)

    venv = getattr(args, "venv", None)
    ref = getattr(args, "ref", None)
    use_cache = getattr(args, "use_cache", False)
    from_release = getattr(args, "from_release", False)
    from_source = getattr(args, "from_source", False)
    verify_identity = getattr(args, "verify", None)
    insecure = getattr(args, "insecure", False)
    offline = getattr(args, "offline", False)
    assume_yes = getattr(args, "yes", False)
    require_release = getattr(args, "require_release", False)

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
        insecure=insecure,
        offline=offline,
        assume_yes=assume_yes,
        require_release=require_release,
        venv_explicit=venv is not None,
        remember_venv=getattr(args, "remember_venv", False),
        forget_venv=getattr(args, "forget_venv", False),
        no_interactive=no_interactive,
        config_dir=_config(args),
    )

    if args.command == "install":
        try:
            install(args.remote, **install_kwargs)
        except UserCancelled as exc:
            print(str(exc) or "Cancelled.", file=sys.stderr)
            raise SystemExit(130) from exc
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            raise SystemExit(130)
        except OfflineError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        except InstallerError as exc:
            print(format_installer_error(exc), file=sys.stderr)
            raise SystemExit(1) from exc
    elif args.command == "update":
        try:
            update_fn(args.remote, **install_kwargs)
        except UserCancelled as exc:
            print(str(exc) or "Cancelled.", file=sys.stderr)
            raise SystemExit(130) from exc
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            raise SystemExit(130)
        except OfflineError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        except InstallerError as exc:
            print(format_installer_error(exc), file=sys.stderr)
            raise SystemExit(1) from exc
    elif args.command == "list":
        list_packages(installer=inst)
    elif args.command == "uninstall":
        uninstall(args.package, installer=inst)


if __name__ == "__main__":
    main()
