# Copyright (c) 2026, Quad4 (quad4.io)
"""Environment-based configuration for opip."""

import os


def env_int(name, default):
    val = os.environ.get(name)
    if val is None or not val.strip():
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default


def env_str(name, default=None):
    val = os.environ.get(name)
    if val is None or not val.strip():
        return default
    return val.strip()


def apply_defaults(args):
    """Apply OPIP_* environment defaults to parsed args where not set on CLI."""
    if getattr(args, "data_dir", None) is None:
        args.data_dir = env_str("OPIP_DATA_DIR")

    if getattr(args, "command", None) == "create":
        if args.python_version is None:
            args.python_version = env_str("OPIP_PYTHON")
        if args.platform is None:
            args.platform = env_str("OPIP_PLATFORM")
        if args.jobs == 8:
            args.jobs = env_int("OPIP_JOBS", 8)
        if getattr(args, "publisher", None) is None:
            args.publisher = env_str("OPIP_PUBLISHER")
        if getattr(args, "identity", None) is None:
            args.identity = env_str("OPIP_IDENTITY")
        if getattr(args, "index_url", None) is None:
            args.index_url = env_str("OPIP_INDEX_URL")
        if getattr(args, "find_links", None) is None:
            args.find_links = env_str("OPIP_FIND_LINKS")
        if not getattr(args, "offline", False):
            args.offline = bool(env_str("OPIP_OFFLINE"))
        if getattr(args, "proxy", None) is None:
            args.proxy = env_str("OPIP_PROXY")

    if getattr(args, "command", None) == "update":
        if getattr(args, "index_url", None) is None:
            args.index_url = env_str("OPIP_INDEX_URL")
        if getattr(args, "find_links", None) is None:
            args.find_links = env_str("OPIP_FIND_LINKS")
        if not getattr(args, "offline", False):
            args.offline = bool(env_str("OPIP_OFFLINE"))

    if (
        getattr(args, "command", None) == "install"
        and getattr(args, "backend", None) is None
    ):
        args.backend = env_str("OPIP_BACKEND")

    if (
        getattr(args, "command", None) in ("verify", "install", "extract")
        or getattr(args, "bundle_command", None) in ("verify", "install")
    ) and getattr(args, "signer", None) is None:
        args.signer = env_str("OPIP_SIGNER")

    return args


ENV_HELP = [
    ("OPIP_DATA_DIR", "State directory (bundles registry, install records)"),
    ("OPIP_JOBS", "Default parallel downloads for create (integer)"),
    ("OPIP_PYTHON", "Default --python for create (e.g. 3.12)"),
    ("OPIP_PLATFORM", "Default --platform for create (e.g. win_amd64 or universal)"),
    ("OPIP_PUBLISHER", "Default --publisher for create"),
    ("OPIP_IDENTITY", "Default --identity path for create"),
    ("OPIP_SIGNER", "Optional pinned --signer for verify and install"),
    ("OPIP_COLOR", "Color mode: auto, always, or never"),
    ("OPIP_NO_COLOR", "Disable color when set (non-empty)"),
    ("OPIP_FORCE_COLOR", "Force color when set (non-empty)"),
    ("OPIP_NO_INTERACTIVE", "Disable prompts when set (non-empty)"),
    ("OPIP_INDEX_URL", "Warehouse JSON index base (default https://pypi.org/pypi)"),
    ("OPIP_FIND_LINKS", "Local wheel directory for create (air-gap)"),
    ("OPIP_OFFLINE", "Refuse network during create when set"),
    ("OPIP_BACKEND", "Install backend: pip, uv, or manual"),
    ("OPIP_PROXY", "HTTP/HTTPS/SOCKS5(h) proxy for create/kit downloads"),
    ("NO_COLOR", "Standard. Disables color when set"),
    ("FORCE_COLOR", "Standard. Enables color when set"),
    ("CI", "When set, disables prompts and color (unless FORCE_COLOR)"),
    ("PIP_RNS_CONFIG", "pip-rns config directory. aliases and trust store"),
]

COMMAND_SUMMARY = [
    ("create", "Build an offline .opip bundle from PyPI wheels"),
    ("install", "Install a bundle from file, rns://, URL, FTP, or git"),
    ("kit", "USB/airgap kit with zipapps and optional portable Python"),
    ("self-install", "Install opip/pip-rns without system pip"),
    ("export", "Copy a verified bundle for sneakernet sharing"),
    ("extract", "Unpack wheels for pip/uv hand-off"),
    ("verify", "Check integrity, authenticity, and provenance"),
    ("info", "Show bundle metadata"),
    ("update", "Rebuild a registered bundle from PyPI"),
    ("delta", "Build a thin .opipd patch between two bundles"),
    ("apply", "Apply a .opipd patch onto a base bundle"),
    ("uninstall", "Remove packages from a registered bundle name"),
    ("uninstall-file", "Uninstall using a .opip file path"),
    ("open", "Interactive install menu (Windows double-click)"),
    ("dest", "Remembered install destinations per bundle"),
    ("list", "List registered bundles or installs"),
    ("trust", "Trusted publishers (shared pip-rns trust.json)"),
    ("doctor", "Check opip environment health"),
    ("completion", "Install shell completions"),
    ("register-windows", "Explorer file association and context menus"),
    ("unregister-windows", "Remove Windows registration"),
    ("help", "Interactive help and per-command reference"),
    ("keygen", "Generate a Reticulum identity for bundle signing"),
]

EXAMPLES = [
    ("opip help airgap", "Offline / no-pip / kit recipes"),
    ("opip help create", "Detailed help for create"),
    ("opip create --help", "Same as above (argparse)"),
    ("opip create", "Auto-detect project and build bundle"),
    ("opip create -r req.txt --platform win_amd64 --python 3.12", "Windows bundle"),
    ("opip create --platform universal --python 3.12", "Multi-OS bundle"),
    ("opip kit create nomadnet -o /media/usb --with-runtime", "USB kit"),
    ("opip install ./my-bundle.opip --user", "User install offline"),
    ("opip install ./my-bundle.opip --venv .venv", "Install into a venv (PEP 668)"),
    ("opip export my-bundle -o /media/usb/pkg.opip", "Copy to USB"),
]
