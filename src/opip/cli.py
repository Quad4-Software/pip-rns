# Copyright (c) 2026, Quad4 (quad4.io)
"""Command-line interface for opip."""

import argparse
import json
import os
import sys

from opip import __version__, terminal
from opip.bundle import BundleError, bundle_info, create_bundle, read_requirements_file
from opip.config import apply_defaults
from opip.export import ExportError, export_bundle
from opip.fetch import FetchError
from opip.help_pages import interactive_help, show_command_help, show_main_help
from opip.install import InstallError, install_from_source, uninstall_from_file
from opip.interactive import is_noninteractive
from opip.keys import IdentityError, generate_identity, identity_hash
from opip.kit import KitError
from opip.listing import (
    bundle_info_dict,
    bundles_as_json,
    format_bundle_table,
    format_install_table,
    installs_as_json,
    list_bundles,
    list_installed,
    show_bundle_info,
    verify_result_dict,
)
from opip.manifest import BUNDLE_EXTENSION
from opip.open_handler import OpenError, open_bundle
from opip.project import ProjectError, detect_project, merge_optional_requirements
from opip.proxy import ProxyError
from opip.signing import SigningError
from opip.storage import Store
from opip.trust_cmd import dispatch_trust, resolve_signer
from opip.uninstall import UninstallError, uninstall_bundle
from opip.update import UpdateError, update_bundle
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
        version=f"opip {__version__}",
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
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Never prompt (also: -y/--yes, CI, OPIP_NO_INTERACTIVE, non-TTY).",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Assume yes / non-interactive (alias for --no-interactive).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Machine-readable JSON on stdout for verify, info, list, trust ls.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress success stdout (errors still on stderr).",
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="DIR",
        help="pip-rns config directory for trust store (env: PIP_RNS_CONFIG).",
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
        "--require-pypi-hash",
        action="store_true",
        help="Require index sha256 digests for every downloaded wheel.",
    )
    p_create.add_argument(
        "--index-url",
        default=None,
        help="Warehouse JSON index base (env: OPIP_INDEX_URL).",
    )
    p_create.add_argument(
        "--find-links",
        default=None,
        metavar="DIR",
        help="Local wheel directory for create (env: OPIP_FIND_LINKS).",
    )
    p_create.add_argument(
        "--offline",
        action="store_true",
        help="Refuse network during create (env: OPIP_OFFLINE).",
    )
    p_create.add_argument(
        "--lockfile",
        default=None,
        metavar="PATH",
        help="Use uv.lock, poetry.lock, or pip-tools hashed requirements.",
    )
    p_create.add_argument(
        "--no-lock",
        action="store_true",
        help="Ignore auto-detected lockfiles; resolve from requirements.",
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
    p_create.add_argument(
        "--proxy",
        default=None,
        help="HTTP/HTTPS/SOCKS5(h) proxy for downloads (env: OPIP_PROXY). "
        "Tor example: socks5h://127.0.0.1:9050",
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
        "--venv",
        default=None,
        metavar="PATH",
        help="Create/use a virtualenv at PATH and install into it.",
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
        help=(
            "Pin required signer identity (env: OPIP_SIGNER). "
            "Without this, a present .rsg is still verified via embedded pubkey."
        ),
    )
    p_install.add_argument(
        "--require-signature",
        action="store_true",
        help="Fail if bundle is not signed.",
    )
    p_install.add_argument(
        "--remember-target",
        action="store_true",
        help="Remember --target for this bundle name without prompting.",
    )
    p_install.add_argument(
        "--forget-target",
        action="store_true",
        help="Forget any remembered install destination for this bundle.",
    )
    p_install.add_argument(
        "--backend",
        choices=("pip", "uv", "manual"),
        default=None,
        help="Install backend (env: OPIP_BACKEND, default pip). "
        "manual extracts wheels without pip.",
    )
    p_install.add_argument(
        "--break-system-packages",
        action="store_true",
        help="Pass --break-system-packages to pip/uv (PEP 668).",
    )

    p_self = sub.add_parser(
        "self-install",
        help="Install opip and pip-rns onto PATH without system pip.",
    )
    p_self.add_argument(
        "--user",
        action="store_true",
        help="Install to user site (default when no target/venv).",
    )
    p_self.add_argument(
        "--target",
        default=None,
        metavar="DIR",
        help="Extract packages into DIR.",
    )
    p_self.add_argument(
        "--venv",
        default=None,
        metavar="PATH",
        help="Create/use a venv and install into it.",
    )

    p_kit = sub.add_parser(
        "kit",
        help="Build or verify USB/airgap kits (zipapps + bundle + optional runtime).",
    )
    kit_sub = p_kit.add_subparsers(dest="kit_command", help="kit actions")
    p_kit_create = kit_sub.add_parser(
        "create",
        help="Create a sneakernet kit directory.",
    )
    p_kit_create.add_argument(
        "packages",
        nargs="+",
        help="Package requirements (e.g. nomadnet).",
    )
    p_kit_create.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output kit directory (must be empty or new).",
    )
    p_kit_create.add_argument("--name", default=None, help="Bundle/kit name.")
    p_kit_create.add_argument(
        "--python",
        default=None,
        dest="python_version",
        help="Target Python version.",
    )
    p_kit_create.add_argument(
        "--platform",
        default=None,
        help="Platform tag for wheels.",
    )
    p_kit_create.add_argument(
        "--with-runtime",
        action="store_true",
        help="Embed portable CPython (python-build-standalone).",
    )
    p_kit_create.add_argument(
        "--as-app",
        action="store_true",
        help="Pre-extract wheels and write an AppImage-style ./Run launcher.",
    )
    p_kit_create.add_argument(
        "--entry",
        default=None,
        metavar="NAME",
        help="Console script / launcher name for --as-app (default: package name).",
    )
    p_kit_create.add_argument(
        "--no-tools",
        action="store_true",
        help="Do not copy opip.pyz / pip-rns.pyz into the kit.",
    )
    p_kit_create.add_argument(
        "--runtime-arch",
        choices=("x86_64", "aarch64"),
        default=None,
        help="Architecture for --with-runtime (default: this machine).",
    )
    p_kit_create.add_argument(
        "--runtime-dir",
        default=None,
        help="Use an existing portable Python directory instead of downloading.",
    )
    p_kit_create.add_argument(
        "--runtime-tarball",
        default=None,
        help="Use a local install_only tarball instead of downloading.",
    )
    p_kit_create.add_argument(
        "--proxy",
        default=None,
        help="Proxy for PyPI / runtime downloads (env: OPIP_PROXY).",
    )
    p_kit_create.add_argument(
        "--find-links",
        default=None,
        help="Local wheel directory (offline create).",
    )
    p_kit_create.add_argument(
        "--offline",
        action="store_true",
        help="Refuse network during bundle create.",
    )
    p_kit_create.add_argument(
        "--require-pypi-hash",
        action="store_true",
        help="Require index sha256 digests for every wheel.",
    )
    p_kit_create.add_argument(
        "--dist-dir",
        default=None,
        help="Directory containing prebuilt opip.pyz / pip-rns.pyz.",
    )
    p_kit_verify = kit_sub.add_parser(
        "verify",
        help="Verify kit SHA256SUMS and optional signatures.",
    )
    p_kit_verify.add_argument("directory", help="Kit directory.")
    p_kit_verify.add_argument(
        "--require-signature",
        action="store_true",
        help="Require .rsg on bundled .opip files.",
    )

    p_dest = sub.add_parser(
        "dest",
        help="Manage remembered install destinations per bundle name.",
    )
    dest_sub = p_dest.add_subparsers(dest="dest_command", help="dest actions")
    dest_sub.add_parser("list", help="List remembered destinations.")
    p_dest_set = dest_sub.add_parser("set", help="Set remembered destination.")
    p_dest_set.add_argument("name", help="Bundle name.")
    p_dest_set.add_argument("path", help="Install target directory.")
    p_dest_forget = dest_sub.add_parser("forget", help="Forget remembered destination.")
    p_dest_forget.add_argument("name", help="Bundle name.")

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

    p_extract = sub.add_parser(
        "extract",
        help="Unpack wheels from a bundle for pip/uv hand-off.",
    )
    p_extract.add_argument("bundle", help="Path to .opip bundle file.")
    p_extract.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output wheelhouse directory.",
    )
    p_extract.add_argument(
        "--simple-index",
        action="store_true",
        help="Write a minimal PEP 503 simple index layout.",
    )
    p_extract.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip integrity verification before extract.",
    )
    p_extract.add_argument(
        "--signer",
        metavar="IDENTITY",
        default=None,
        help="Pin required signer identity (env: OPIP_SIGNER).",
    )
    p_extract.add_argument(
        "--require-signature",
        action="store_true",
        help="Fail if bundle is not signed.",
    )

    p_delta = sub.add_parser(
        "delta",
        help="Build a thin .opipd patch between two bundles.",
    )
    p_delta.add_argument("old", help="Base .opip bundle.")
    p_delta.add_argument("new", help="Target .opip bundle.")
    p_delta.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output .opipd path.",
    )

    p_apply = sub.add_parser(
        "apply",
        help="Apply a .opipd patch onto a base bundle.",
    )
    p_apply.add_argument("base", help="Base .opip bundle.")
    p_apply.add_argument("delta", help="Path to .opipd patch.")
    p_apply.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output .opip path.",
    )
    p_apply.add_argument(
        "--identity",
        default=None,
        help="Reticulum identity to sign the result.",
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
    p_update.add_argument(
        "--no-reinstall",
        action="store_true",
        help="Only rebuild the .opip file; do not reinstall packages.",
    )
    p_update.add_argument("--user", action="store_true")
    p_update.add_argument("--target", default=None)
    p_update.add_argument(
        "--venv",
        default=None,
        metavar="PATH",
        help="Reinstall into this virtualenv (overrides remembered dest).",
    )
    p_update.add_argument(
        "--identity",
        default=None,
        help="Reticulum identity to re-sign the updated bundle.",
    )
    p_update.add_argument(
        "--index-url",
        default=None,
        help="Warehouse JSON index base (env: OPIP_INDEX_URL).",
    )
    p_update.add_argument(
        "--find-links",
        default=None,
        metavar="DIR",
        help="Local wheel directory (env: OPIP_FIND_LINKS).",
    )
    p_update.add_argument(
        "--offline",
        action="store_true",
        help="Refuse network during update.",
    )
    p_update.add_argument(
        "--emit-delta",
        default=None,
        metavar="PATH",
        help="Also write a .opipd patch from the previous bundle.",
    )

    p_verify = sub.add_parser(
        "verify",
        help="Verify bundle integrity, authenticity, and provenance.",
    )
    p_verify.add_argument("bundle", help="Path to .opip bundle file.")
    p_verify.add_argument(
        "--signer",
        metavar="IDENTITY",
        default=None,
        help=(
            "Pin required signer identity (env: OPIP_SIGNER). "
            "Without this, a present .rsg is still verified via embedded pubkey."
        ),
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

    p_trust = sub.add_parser(
        "trust",
        help="Trusted publisher identities (shared pip-rns trust store).",
    )
    tp = p_trust.add_subparsers(dest="trust_command", help="trust actions")
    t_add = tp.add_parser("add", help="Trust a signer for a remote (or set default).")
    t_add.add_argument(
        "remote_or_default",
        help="Remote rns:// URL, identity hex, or 'default'.",
    )
    t_add.add_argument("identity", help="32-hex Reticulum identity hash.")
    t_rm = tp.add_parser("rm", help="Forget a trusted signer.")
    t_rm.add_argument("remote_or_default", help="Remote rns:// URL or 'default'.")
    tp.add_parser("ls", help="List trusted publishers.")
    t_sd = tp.add_parser("set-default", help="Set default signer identity.")
    t_sd.add_argument("identity")
    tp.add_parser("forget-default", help="Clear default signer.")

    sub.add_parser(
        "doctor",
        help="Check opip environment health.",
    )

    p_comp = sub.add_parser(
        "completion",
        help="Install shell completions.",
    )
    cp = p_comp.add_subparsers(dest="completion_command", help="completion actions")
    p_comp_install = cp.add_parser(
        "install",
        help="Install completions for this shell.",
    )
    p_comp_install.add_argument(
        "--shell",
        choices=("bash", "zsh", "fish"),
        default=None,
        help="Shell (default: detect from $SHELL).",
    )
    p_comp_install.add_argument(
        "--dry-run",
        action="store_true",
        help="Show copy actions without writing files.",
    )

    return parser


def main(argv=None):
    terminal.configure_stdio()
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()

    no_color = "--no-color" in argv
    terminal.configure(no_color=no_color)

    if not argv:
        show_main_help()
        if is_noninteractive():
            return 2
        return interactive_help(parser)

    args = parser.parse_args(argv)
    args = apply_defaults(args)
    args.no_interactive = bool(
        getattr(args, "no_interactive", False) or getattr(args, "yes", False),
    )

    if args.command == "help":
        if args.topic == "airgap":
            return _show_airgap_help()
        if args.topic:
            return show_command_help(parser, args.topic)
        if args.interactive and not is_noninteractive(args.no_interactive):
            return interactive_help(parser)
        if is_noninteractive(args.no_interactive):
            show_main_help()
            return 0
        if sys.stdin.isatty():
            return interactive_help(parser)
        show_main_help()
        return 0

    if not args.command:
        show_main_help()
        return 0

    store = Store(data_dir=args.data_dir)

    try:
        return _dispatch(args, store)
    except (
        BundleError,
        InstallError,
        UninstallError,
        UpdateError,
        ProjectError,
        ExportError,
        OpenError,
        IdentityError,
        SigningError,
        KitError,
        ProxyError,
        FetchError,
    ) as exc:
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
    lock_pins = None

    if not getattr(args, "no_lock", False):
        lock_path = getattr(args, "lockfile", None)
        if not lock_path:
            from opip.lock_import import detect_lockfile

            lock_path = detect_lockfile(project_dir)
        if lock_path and (
            getattr(args, "lockfile", None)
            or (not args.requirements and not args.packages)
        ):
            from opip.lock_import import LockImportError, load_lockfile

            try:
                lock_pins = load_lockfile(lock_path)
                terminal.info(f"Using lockfile {lock_path}")
            except LockImportError as exc:
                if getattr(args, "lockfile", None):
                    raise BundleError(str(exc))
                lock_pins = None

    if lock_pins is None:
        if args.requirements:
            reqs.extend(read_requirements_file(args.requirements))
        elif not reqs:
            project_info = detect_project(project_dir)
            reqs = merge_optional_requirements(
                project_info,
                project_dir,
                include_dev=args.with_dev,
            )
            if project_info.source:
                terminal.info(f"Using {project_info.source} from {project_dir}")

        if not reqs:
            raise BundleError(
                "No requirements found. Add packages, pass -r requirements.txt, "
                "--lockfile, or run inside a project with pyproject.toml.",
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

    return output, reqs, name, project_dir, include_project, lock_pins


def _resolve_include_project(args, project_info, project_dir):
    if args.no_include_project:
        return False
    if args.include_project:
        return True
    return bool(project_info and project_info.source in ("setup.py", "pyproject.toml"))


def _prompt_bundle_name(no_interactive):
    if is_noninteractive(no_interactive):
        raise BundleError(
            "Could not determine bundle name. Pass --name or use a pyproject.toml.",
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


def _show_airgap_help():
    terminal.heading("opip airgap")
    terminal.write_out("")
    terminal.write_out("1) Bootstrap with NO pip (browser-downloaded pip_rns wheel):")
    terminal.bullet(
        "python3 get-opip.py --from-wheel pip_rns-*.whl -o .",
        "stdlib only",
    )
    terminal.bullet(
        "python3 get-opip.py --proxy socks5h://127.0.0.1:9050 -o .",
        "or Tor download",
    )
    terminal.write_out("")
    terminal.write_out("2) Build a USB kit (hand wheels + Tor + AppImage-like run):")
    terminal.bullet(
        "python3 opip.pyz kit create nomadnet -o /media/usb",
        "--find-links ./wheels --offline --with-runtime --as-app",
    )
    terminal.bullet(
        "python3 opip.pyz kit create nomadnet -o /media/usb --with-runtime --as-app",
        "--proxy socks5h://127.0.0.1:9050",
    )
    terminal.write_out("")
    terminal.write_out("3) Offline machine (like MeshChat AppImage):")
    terminal.bullet("/media/usb/NomadNet", "or ./Run  (no install.sh needed)")
    terminal.bullet("/media/usb/install.sh", "optional: also install into a venv")
    terminal.write_out("")
    terminal.info("Also: opip help kit   pip-rns help bootstrap")
    return 0


def _dispatch(args, store):
    if args.command == "create":
        proxy = getattr(args, "proxy", None)
        if proxy:
            from opip.proxy import set_proxy

            set_proxy(proxy)
        output, reqs, name, project_dir, include_project, lock_pins = (
            _resolve_create_plan(args)
        )
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
            index_url=getattr(args, "index_url", None),
            find_links=getattr(args, "find_links", None),
            offline=bool(getattr(args, "offline", False)),
            lock_pins=lock_pins,
        )
        manifest = bundle_info(path)
        store.register_bundle(
            manifest.get("name") or name,
            path,
            manifest,
        )
        if not getattr(args, "quiet", False):
            terminal.success(f"Created bundle: {path}")
            terminal.write_out(
                "  {} wheels for Python {} on {}".format(
                    len(manifest.get("wheels", [])),
                    manifest.get("python_version"),
                    manifest.get("platform"),
                ),
            )
        return 0

    if args.command == "self-install":
        from opip.self_install import self_install

        self_install(
            user=bool(args.user) or not (args.target or args.venv),
            target=args.target,
            venv=args.venv,
            no_interactive=args.no_interactive,
        )
        return 0

    if args.command == "kit":
        return _dispatch_kit(args)

    if args.command == "install":
        if args.system and args.user:
            terminal.error("use either --user or --system, not both.")
            return 1
        if args.venv and (args.target or args.user):
            terminal.error("use --venv alone, not with --target or --user.")
            return 1
        signer = resolve_signer(
            args.source,
            explicit=args.signer,
            insecure=False,
            config_dir=getattr(args, "config", None),
        )
        packages = install_from_source(
            args.source,
            target=args.target,
            user=args.user,
            replace=args.replace,
            store=store,
            verify=not args.no_verify,
            signer=signer,
            require_signature=args.require_signature,
            target_explicit=args.target is not None,
            remember_target=args.remember_target,
            forget_target=args.forget_target,
            no_interactive=args.no_interactive,
            venv=args.venv,
            backend=getattr(args, "backend", None),
            break_system_packages=bool(getattr(args, "break_system_packages", False)),
        )
        if not getattr(args, "quiet", False):
            terminal.success(f"Installed {len(packages)} packages from bundle.")
            for pkg in packages:
                terminal.write_out(f"  {pkg}")
            dest = getattr(packages, "dest", None) or (
                args.target
                or (f"venv {args.venv}" if args.venv else None)
                or ("user site" if args.user else "system/active")
            )
            if args.no_verify:
                signer_label = "skipped (--no-verify)"
            elif signer:
                signer_label = f"verified {signer}"
            else:
                signer_label = "auto (.rsg when present)"
            terminal.write_out(terminal.dim(f"Resolved: {args.source}"))
            terminal.write_out(terminal.dim("Mode: opip bundle"))
            terminal.write_out(terminal.dim(f"Dest: {dest}"))
            terminal.write_out(terminal.dim(f"Signer: {signer_label}"))
        return 0

    if args.command == "dest":
        return _dispatch_dest(args, store)

    if args.command == "uninstall":
        packages = uninstall_bundle(
            args.bundle,
            store=store,
            user=args.user,
            target=args.target,
        )
        terminal.success(f"Uninstalled {len(packages)} packages from {args.bundle}.")
        return 0

    if args.command == "uninstall-file":
        packages = uninstall_from_file(
            args.bundle,
            store=store,
            user=args.user,
            target=args.target,
        )
        terminal.success(f"Uninstalled {len(packages)} packages.")
        return 0

    if args.command == "open":
        packages = open_bundle(
            args.bundle,
            store=store,
            user=args.user,
            target=args.target,
            no_interactive=args.no_interactive,
            target_explicit=args.target is not None,
        )
        if packages:
            terminal.success(f"Done. {len(packages)} packages affected.")
        return 0

    if args.command == "export":
        out, manifest = export_bundle(args.source, args.output, store=store)
        if not getattr(args, "quiet", False):
            terminal.success(f"Exported bundle: {out}")
            terminal.write_out(
                "  {} wheels, Python {}, {}".format(
                    len(manifest.get("wheels", [])),
                    manifest.get("python_version"),
                    manifest.get("platform"),
                ),
            )
        return 0

    if args.command == "extract":
        from opip.extract_cmd import ExtractError, extract_to_wheelhouse

        signer = resolve_signer(
            args.bundle,
            explicit=args.signer,
            insecure=False,
            config_dir=getattr(args, "config", None),
        )
        try:
            out, count = extract_to_wheelhouse(
                args.bundle,
                args.output,
                simple_index=args.simple_index,
                verify=not args.no_verify,
                signer=signer,
                require_signature=args.require_signature,
            )
        except ExtractError as exc:
            terminal.error(str(exc))
            return 1
        if not getattr(args, "quiet", False):
            terminal.success(f"Extracted {count} wheels to {out}")
        return 0

    if args.command == "delta":
        from opip.delta import DeltaError, create_delta

        try:
            path, meta = create_delta(args.old, args.new, args.output)
        except DeltaError as exc:
            terminal.error(str(exc))
            return 1
        if getattr(args, "json", False):
            terminal.write_out(
                json.dumps(
                    {
                        "path": path,
                        "added": meta.get("added"),
                        "changed": meta.get("changed"),
                        "removed": meta.get("removed"),
                        "unchanged_count": len(meta.get("unchanged") or []),
                    },
                    indent=2,
                    sort_keys=True,
                ),
            )
        elif not getattr(args, "quiet", False):
            terminal.success(f"Wrote delta: {path}")
            terminal.write_out(
                "  +{} ~{} -{} ({} unchanged)".format(
                    len(meta.get("added") or []),
                    len(meta.get("changed") or []),
                    len(meta.get("removed") or []),
                    len(meta.get("unchanged") or []),
                ),
            )
        return 0

    if args.command == "apply":
        from opip.delta import DeltaError, apply_delta

        try:
            path = apply_delta(
                args.base,
                args.delta,
                args.output,
                identity_path=args.identity,
            )
        except DeltaError as exc:
            terminal.error(str(exc))
            return 1
        if not getattr(args, "quiet", False):
            terminal.success(f"Applied delta: {path}")
        return 0

    if args.command == "register-windows":
        from opip.windows import WindowsIntegrationError, register_windows

        try:
            register_windows()
        except WindowsIntegrationError as exc:
            terminal.error(str(exc))
            return 1
        terminal.success("Registered .opip file association and context menus.")
        return 0

    if args.command == "unregister-windows":
        from opip.windows import WindowsIntegrationError, unregister_windows

        try:
            unregister_windows()
        except WindowsIntegrationError as exc:
            terminal.error(str(exc))
            return 1
        terminal.success("Removed .opip file association and context menus.")
        return 0

    if args.command == "update":
        if args.venv and (args.target or args.user):
            terminal.error("use --venv alone, not with --target or --user.")
            return 1
        path = update_bundle(
            args.bundle,
            output_path=args.output,
            store=store,
            reinstall=not args.no_reinstall,
            user=args.user,
            target=args.target,
            venv=args.venv,
            no_interactive=args.no_interactive,
            identity_path=args.identity,
            index_url=getattr(args, "index_url", None),
            find_links=getattr(args, "find_links", None),
            offline=bool(getattr(args, "offline", False)),
            emit_delta=getattr(args, "emit_delta", None),
        )
        if not getattr(args, "quiet", False):
            terminal.success(f"Updated bundle: {path}")
        return 0

    if args.command == "verify":
        signer = resolve_signer(
            args.bundle,
            explicit=args.signer,
            insecure=False,
            config_dir=getattr(args, "config", None),
        )
        ok, errors, manifest = verify_bundle_file(
            args.bundle,
            signer=signer,
            require_signature=args.require_signature,
            require_pypi_hash=args.require_pypi_hash,
        )
        if getattr(args, "json", False):
            payload = verify_result_dict(ok, args.bundle, errors, manifest)
            terminal.write_out(json.dumps(payload, indent=2, sort_keys=True))
            return 0 if ok else 1
        if ok:
            if not getattr(args, "quiet", False):
                terminal.success(f"Bundle OK: {args.bundle}")
                terminal.write_out(
                    "  {} wheels, Python {}, {}".format(
                        len(manifest.get("wheels", [])),
                        manifest.get("python_version"),
                        manifest.get("platform"),
                    ),
                )
                if manifest.get("version") == "2":
                    terminal.write_out("  manifest v2 (integrity + provenance)")
            return 0
        terminal.error("Bundle verification failed:")
        for err in errors:
            terminal.write_err(f"  {err}")
        return 1

    if args.command == "keygen":
        generate_identity(args.output)
        signer = identity_hash(args.output)
        if not getattr(args, "quiet", False):
            terminal.success(f"Wrote identity: {args.output}")
            terminal.write_out(f"  Identity hash: {signer}")
            terminal.write_out(
                f"  Sign bundles with --identity. verify with --signer {signer}",
            )
        return 0

    if args.command == "info":
        if getattr(args, "json", False):
            terminal.write_out(
                json.dumps(bundle_info_dict(args.bundle), indent=2, sort_keys=True),
            )
            return 0
        if not getattr(args, "quiet", False):
            terminal.write_out(show_bundle_info(args.bundle))
        return 0

    if args.command == "list":
        if args.what == "installed":
            rows = list_installed(store)
            if getattr(args, "json", False):
                terminal.write_out(installs_as_json(rows))
            elif not getattr(args, "quiet", False):
                terminal.write_out(format_install_table(rows))
        else:
            rows = list_bundles(store)
            if getattr(args, "json", False):
                terminal.write_out(bundles_as_json(rows))
            elif not getattr(args, "quiet", False):
                terminal.write_out(format_bundle_table(rows))
        return 0

    if args.command == "trust":
        return dispatch_trust(
            args,
            write_out=terminal.write_out,
            success=terminal.success,
            warn=terminal.warn,
            error=terminal.error,
        )

    if args.command == "doctor":
        from opip.doctor import print_doctor, run_doctor

        terminal.heading("opip doctor")
        return print_doctor(run_doctor(data_dir=args.data_dir))

    if args.command == "completion":
        from opip.completion_cmd import install_completions

        cmd = getattr(args, "completion_command", None)
        if cmd != "install":
            terminal.error("Usage: opip completion install [--shell bash|zsh|fish]")
            return 1
        try:
            lines = install_completions(
                shell=getattr(args, "shell", None),
                dry_run=getattr(args, "dry_run", False),
            )
        except (ValueError, FileNotFoundError) as exc:
            terminal.error(str(exc))
            return 1
        for line in lines:
            terminal.write_out(line)
        return 0

    return 1


def _dispatch_kit(args):
    from opip.kit import create_kit, verify_kit

    if args.kit_command == "create":
        create_kit(
            list(args.packages),
            args.output,
            python_version=args.python_version,
            platform_tag=args.platform,
            with_runtime=bool(args.with_runtime),
            with_tools=not bool(args.no_tools),
            runtime_arch=args.runtime_arch,
            runtime_dir=args.runtime_dir,
            runtime_tarball=args.runtime_tarball,
            proxy=args.proxy,
            find_links=args.find_links,
            offline=bool(args.offline),
            name=args.name,
            require_pypi_hash=bool(args.require_pypi_hash),
            dist_dir=args.dist_dir,
            as_app=bool(getattr(args, "as_app", False)),
            entry=getattr(args, "entry", None),
        )
        return 0
    if args.kit_command == "verify":
        errors = verify_kit(
            args.directory,
            require_signature=bool(args.require_signature),
        )
        if errors:
            for err in errors:
                terminal.error(err)
            return 1
        terminal.success(f"Kit OK: {args.directory}")
        return 0
    terminal.error("Usage: opip kit create|verify ...")
    return 2


def _dispatch_dest(args, store):
    cmd = getattr(args, "dest_command", None)
    if cmd == "list" or cmd is None:
        rows = store.list_preferred_targets()
        if not rows:
            terminal.info("No remembered destinations.")
            return 0
        for name, path in rows:
            terminal.write_out(f"{name}\t{path}")
        return 0
    if cmd == "set":
        store.set_preferred_target(args.name, args.path)
        terminal.success(f"Remembered {args.name} -> {os.path.abspath(args.path)}")
        return 0
    if cmd == "forget":
        if store.forget_preferred_target(args.name):
            terminal.success(f"Forgot destination for {args.name}.")
        else:
            terminal.warn(f"No remembered destination for {args.name}.")
        return 0
    terminal.error("Usage: opip dest list|set|forget")
    return 1


if __name__ == "__main__":
    sys.exit(main())
