"""Command-line interface for opip."""

import argparse
import os
import sys

from opip import __version__
from opip.bundle import BundleError, bundle_info, create_bundle, read_requirements_file
from opip.config import apply_defaults
from opip.export import ExportError, export_bundle
from opip.help_pages import interactive_help, show_command_help, show_main_help
from opip.install import InstallError, install_from_source, uninstall_from_file
from opip.open_handler import OpenError, open_bundle
from opip.listing import (
    format_bundle_table,
    format_install_table,
    list_bundles,
    list_installed,
    show_bundle_info,
)
from opip.manifest import BUNDLE_EXTENSION
from opip.project import ProjectError, detect_project, merge_optional_requirements
from opip.storage import Store
from opip import terminal
from opip.uninstall import UninstallError, uninstall_bundle
from opip.update import UpdateError, update_bundle
from opip.keys import IdentityError, generate_identity, identity_hash
from opip.signing import SigningError
from opip.verify import verify_bundle_file


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opip",
        description=(
            "Create and install integrity-backed offline Python wheel bundles."
        ),
        add_help=True,
    )
    parser.add_argument(
        "--version",
        action="version",
        version="opip {0}".format(__version__),
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Override state directory (env: OPIP_DATA_DIR).",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output (env: OPIP_NO_COLOR, NO_COLOR).",
    )

    sub = parser.add_subparsers(dest="command", help="Available commands")

    p_help = sub.add_parser(
        "help",
        help="Interactive help and per-command reference.",
        add_help=False,
    )
    p_help.add_argument(
        "topic",
        nargs="?",
        default=None,
        help="Command name for detailed help (e.g. create, install).",
    )
    p_help.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Interactive command browser (default when TTY and no topic).",
    )

    p_create = sub.add_parser(
        "create",
        help="Fetch wheels and create an offline bundle (.opip).",
    )
    p_create.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output bundle path (default: PROJECT_NAME.opip).",
    )
    p_create.add_argument(
        "-C",
        "--project-dir",
        default=".",
        help="Project directory with pyproject.toml or requirements.txt.",
    )
    p_create.add_argument(
        "-r",
        "--requirements",
        default=None,
        help="Requirements file path (overrides auto-detection).",
    )
    p_create.add_argument(
        "packages",
        nargs="*",
        help="Package requirements (e.g. requests==2.28.0).",
    )
    p_create.add_argument(
        "--name",
        default=None,
        help="Bundle name (default: from pyproject.toml or prompt).",
    )
    p_create.add_argument(
        "--python",
        default=None,
        dest="python_version",
        help="Target Python version (env: OPIP_PYTHON).",
    )
    p_create.add_argument(
        "--platform",
        default=None,
        help="Platform tag or universal (env: OPIP_PLATFORM).",
    )
    p_create.add_argument(
        "--no-deps",
        action="store_true",
        help="Do not include transitive dependencies.",
    )
    p_create.add_argument(
        "--with-dev",
        action="store_true",
        help="Include dev/test requirements files when auto-detecting.",
    )
    p_create.add_argument(
        "--include-project",
        action="store_true",
        help="Build and include a wheel for the local project (setup.py/pyproject).",
    )
    p_create.add_argument(
        "--no-include-project",
        action="store_true",
        help="Do not build a local project wheel when auto-detecting.",
    )
    p_create.add_argument(
        "--jobs",
        type=int,
        default=8,
        help="Parallel downloads (default: 8, env: OPIP_JOBS).",
    )
    p_create.add_argument(
        "--no-cache",
        action="store_true",
        help="Do not reuse the local wheel cache.",
    )
    p_create.add_argument(
        "--no-interactive",
        action="store_true",
        help="Do not prompt for bundle name; fail if name is unknown.",
    )
    p_create.add_argument(
        "--require-pypi-hash",
        action="store_true",
        help="Require PyPI sha256 digests for every downloaded wheel.",
    )
    p_create.add_argument(
        "--publisher",
        default=None,
        help="Publisher name recorded in publisher.json (env: OPIP_PUBLISHER).",
    )
    p_create.add_argument(
        "--publisher-contact",
        default=None,
        help="Publisher contact (email, URL) for publisher.json.",
    )
    p_create.add_argument(
        "--identity",
        default=None,
        help="Reticulum identity file for RSG signing (env: OPIP_IDENTITY).",
    )

    p_install = sub.add_parser(
        "install",
        help="Install from a local bundle or remote source.",
    )
    p_install.add_argument(
        "source",
        help="Bundle path, rns:// remote, URL (http/https/ftp), or git source.",
    )
    p_install.add_argument(
        "--target",
        default=None,
        help="Install into directory instead of site-packages.",
    )
    p_install.add_argument(
        "--user",
        action="store_true",
        help="Install to user site-packages and user Scripts/bin.",
    )
    p_install.add_argument(
        "--system",
        action="store_true",
        help="Install to system site-packages (default when --user is not set).",
    )
    p_install.add_argument(
        "--replace",
        action="store_true",
        help="Force reinstall/upgrade packages from the bundle.",
    )
    p_install.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip integrity verification before install.",
    )
    p_install.add_argument(
        "--signer",
        metavar="IDENTITY",
        default=None,
        help="Require bundle signed by IDENTITY (env: OPIP_SIGNER).",
    )
    p_install.add_argument(
        "--require-signature",
        action="store_true",
        help="Fail if bundle is not signed.",
    )

    p_uninstall = sub.add_parser(
        "uninstall",
        help="Uninstall packages installed from a registered bundle.",
    )
    p_uninstall.add_argument("bundle", help="Registered bundle name.")
    p_uninstall.add_argument("--user", action="store_true")
    p_uninstall.add_argument("--target", default=None)

    p_uninstall_file = sub.add_parser(
        "uninstall-file",
        help="Uninstall using the bundle name inside a .opip file.",
    )
    p_uninstall_file.add_argument("bundle", help="Path to .opip bundle file.")
    p_uninstall_file.add_argument("--user", action="store_true")
    p_uninstall_file.add_argument("--target", default=None)

    p_open = sub.add_parser(
        "open",
        help="Open a bundle (install/update menu, used by Windows file association).",
    )
    p_open.add_argument("bundle", help="Path to .opip bundle file.")
    p_open.add_argument("--user", action="store_true")
    p_open.add_argument("--target", default=None)

    p_export = sub.add_parser(
        "export",
        help="Export a registered or installed bundle for offline sharing.",
    )
    p_export.add_argument(
        "source",
        help="Registered bundle name or path to .opip file.",
    )
    p_export.add_argument(
        "-o",
        "--output",
        required=True,
        help="Destination .opip path (USB, network share, etc.).",
    )

    sub.add_parser(
        "register-windows",
        help="Register .opip file association and Explorer context menus (Windows).",
    )
    sub.add_parser(
        "unregister-windows",
        help="Remove .opip file association and context menus (Windows).",
    )

    p_update = sub.add_parser(
        "update",
        help="Re-fetch wheels and rebuild a registered bundle.",
    )
    p_update.add_argument("bundle", help="Registered bundle name.")
    p_update.add_argument("-o", "--output", default=None)
    p_update.add_argument("--no-reinstall", action="store_true")
    p_update.add_argument("--user", action="store_true")
    p_update.add_argument("--target", default=None)

    p_verify = sub.add_parser(
        "verify",
        help="Verify bundle integrity, authenticity, and provenance.",
    )
    p_verify.add_argument("bundle", help="Path to .opip bundle file.")
    p_verify.add_argument(
        "--signer",
        metavar="IDENTITY",
        default=None,
        help="Required signer identity hash or file (env: OPIP_SIGNER).",
    )
    p_verify.add_argument(
        "--require-signature",
        action="store_true",
        help="Fail if bundle is not signed.",
    )
    p_verify.add_argument(
        "--require-pypi-hash",
        action="store_true",
        help="Fail if any wheel lacks a recorded PyPI sha256 digest.",
    )

    p_keygen = sub.add_parser(
        "keygen",
        help="Generate a Reticulum identity for bundle signing.",
    )
    p_keygen.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output path for identity file (.rns).",
    )

    p_info = sub.add_parser(
        "info",
        help="Show bundle metadata without installing.",
    )
    p_info.add_argument("bundle", help="Path to .opip bundle file.")

    p_list = sub.add_parser(
        "list",
        help="List registered bundles or installed bundle packages.",
    )
    p_list.add_argument(
        "what",
        nargs="?",
        default="bundles",
        choices=["bundles", "installed"],
        help="What to list (default: bundles).",
    )

    return parser


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()

    if not argv:
        terminal.configure()
        show_main_help()
        if sys.stdin.isatty():
            return interactive_help(parser)
        return 0

    no_color = "--no-color" in argv
    terminal.configure(no_color=no_color)
    args = parser.parse_args(argv)
    args = apply_defaults(args)

    if args.command == "help":
        if args.topic:
            return show_command_help(parser, args.topic)
        if args.interactive or sys.stdin.isatty():
            return interactive_help(parser)
        show_main_help()
        return 0

    if not args.command:
        show_main_help()
        return 0

    store = Store(data_dir=args.data_dir)

    try:
        return _dispatch(args, store)
    except (BundleError, InstallError, UninstallError, UpdateError, ProjectError, ExportError, OpenError, IdentityError, SigningError) as exc:
        terminal.error(str(exc))
        return 1
    except KeyboardInterrupt:
        terminal.warn("Interrupted.")
        return 130


def _resolve_create_plan(args):
    """Resolve requirements, bundle name, and output path for create."""
    project_dir = os.path.abspath(args.project_dir)
    project_info = None
    reqs = list(args.packages)

    if args.requirements:
        reqs.extend(read_requirements_file(args.requirements))
    elif not reqs:
        project_info = detect_project(project_dir)
        reqs = merge_optional_requirements(
            project_info, project_dir, include_dev=args.with_dev
        )
        if project_info.source:
            terminal.info(
                "Using {0} from {1}".format(project_info.source, project_dir)
            )

    if not reqs:
        raise BundleError(
            "No requirements found. Add packages, pass -r requirements.txt, "
            "or run inside a project with pyproject.toml."
        )

    name = args.name
    if not name and project_info and project_info.name:
        name = project_info.name
    if not name:
        name = _prompt_bundle_name(args.no_interactive)

    output = args.output
    if not output:
        output = os.path.join(project_dir, name + BUNDLE_EXTENSION)

    include_project = _resolve_include_project(args, project_info, project_dir)

    return output, reqs, name, project_dir, include_project


def _resolve_include_project(args, project_info, project_dir):
    if args.no_include_project:
        return False
    if args.include_project:
        return True
    if project_info and project_info.source in ("setup.py", "pyproject.toml"):
        return True
    return False


def _prompt_bundle_name(no_interactive):
    if no_interactive:
        raise BundleError(
            "Could not determine bundle name. Pass --name or use a pyproject.toml."
        )
    if not sys.stdin.isatty():
        raise BundleError(
            "Could not determine bundle name. Pass --name NAME."
        )
    sys.stdout.write(terminal.bold("Bundle name: "))
    sys.stdout.flush()
    try:
        answer = input().strip()
    except EOFError:
        answer = ""
    if not answer:
        raise BundleError("Bundle name is required.")
    return answer


def _dispatch(args, store):
    if args.command == "create":
        output, reqs, name, project_dir, include_project = _resolve_create_plan(args)
        path = create_bundle(
            output,
            reqs,
            name=name,
            py_version=args.python_version,
            platform_tag=args.platform,
            include_deps=not args.no_deps,
            project_dir=project_dir,
            include_project=include_project,
            jobs=max(1, args.jobs),
            use_cache=not args.no_cache,
            require_pypi_hash=args.require_pypi_hash,
            publisher_name=args.publisher,
            publisher_contact=args.publisher_contact,
            identity_path=args.identity,
        )
        manifest = bundle_info(path)
        store.register_bundle(
            manifest.get("name") or name,
            path,
            manifest,
        )
        terminal.success("Created bundle: {0}".format(path))
        terminal.write_out(
            "  {0} wheels for Python {1} on {2}".format(
                len(manifest.get("wheels", [])),
                manifest.get("python_version"),
                manifest.get("platform"),
            )
        )
        return 0

    if args.command == "install":
        if args.system and args.user:
            terminal.error("use either --user or --system, not both.")
            return 1
        packages = install_from_source(
            args.source,
            target=args.target,
            user=args.user,
            replace=args.replace,
            store=store,
            verify=not args.no_verify,
            signer=args.signer,
            require_signature=args.require_signature,
        )
        terminal.success(
            "Installed {0} packages from bundle.".format(len(packages))
        )
        for pkg in packages:
            terminal.write_out("  {0}".format(pkg))
        return 0

    if args.command == "uninstall":
        packages = uninstall_bundle(
            args.bundle,
            store=store,
            user=args.user,
            target=args.target,
        )
        terminal.success(
            "Uninstalled {0} packages from {1}.".format(
                len(packages), args.bundle
            )
        )
        return 0

    if args.command == "uninstall-file":
        packages = uninstall_from_file(
            args.bundle,
            store=store,
            user=args.user,
            target=args.target,
        )
        terminal.success("Uninstalled {0} packages.".format(len(packages)))
        return 0

    if args.command == "open":
        packages = open_bundle(
            args.bundle,
            store=store,
            user=args.user,
            target=args.target,
        )
        if packages:
            terminal.success(
                "Done. {0} packages affected.".format(len(packages))
            )
        return 0

    if args.command == "export":
        out, manifest = export_bundle(args.source, args.output, store=store)
        terminal.success("Exported bundle: {0}".format(out))
        terminal.write_out(
            "  {0} wheels, Python {1}, {2}".format(
                len(manifest.get("wheels", [])),
                manifest.get("python_version"),
                manifest.get("platform"),
            )
        )
        return 0

    if args.command == "register-windows":
        from opip.windows import register_windows, WindowsIntegrationError

        try:
            register_windows()
        except WindowsIntegrationError as exc:
            terminal.error(str(exc))
            return 1
        terminal.success("Registered .opip file association and context menus.")
        return 0

    if args.command == "unregister-windows":
        from opip.windows import unregister_windows, WindowsIntegrationError

        try:
            unregister_windows()
        except WindowsIntegrationError as exc:
            terminal.error(str(exc))
            return 1
        terminal.success("Removed .opip file association and context menus.")
        return 0

    if args.command == "update":
        path = update_bundle(
            args.bundle,
            output_path=args.output,
            store=store,
            reinstall=not args.no_reinstall,
            user=args.user,
            target=args.target,
        )
        terminal.success("Updated bundle: {0}".format(path))
        return 0

    if args.command == "verify":
        ok, errors, manifest = verify_bundle_file(
            args.bundle,
            signer=args.signer,
            require_signature=args.require_signature,
            require_pypi_hash=args.require_pypi_hash,
        )
        if ok:
            terminal.success("Bundle OK: {0}".format(args.bundle))
            terminal.write_out(
                "  {0} wheels, Python {1}, {2}".format(
                    len(manifest.get("wheels", [])),
                    manifest.get("python_version"),
                    manifest.get("platform"),
                )
            )
            if manifest.get("version") == "2":
                terminal.write_out("  manifest v2 (integrity + provenance)")
            return 0
        terminal.error("Bundle verification failed:")
        for err in errors:
            terminal.write_err("  {0}".format(err))
        return 1

    if args.command == "keygen":
        generate_identity(args.output)
        signer = identity_hash(args.output)
        terminal.success("Wrote identity: {0}".format(args.output))
        terminal.write_out("  Identity hash: {0}".format(signer))
        terminal.write_out(
            "  Sign bundles with --identity; verify with --signer {0}".format(signer)
        )
        return 0

    if args.command == "info":
        terminal.write_out(show_bundle_info(args.bundle))
        return 0

    if args.command == "list":
        if args.what == "installed":
            terminal.write_out(format_install_table(list_installed(store)))
        else:
            terminal.write_out(format_bundle_table(list_bundles(store)))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
