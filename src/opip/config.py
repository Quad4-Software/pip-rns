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

    if getattr(args, "command", None) in ("verify", "install") or getattr(
        args, "bundle_command", None
    ) in ("verify", "install"):
        if getattr(args, "signer", None) is None:
            args.signer = env_str("OPIP_SIGNER")

    return args


ENV_HELP = [
    ("OPIP_DATA_DIR", "State directory (bundles registry, install records)"),
    ("OPIP_JOBS", "Default parallel downloads for create (integer)"),
    ("OPIP_PYTHON", "Default --python for create (e.g. 3.12)"),
    ("OPIP_PLATFORM", "Default --platform for create (e.g. win_amd64 or universal)"),
    ("OPIP_PUBLISHER", "Default --publisher for create"),
    ("OPIP_IDENTITY", "Default --identity path for create"),
    ("OPIP_SIGNER", "Default --signer for verify and install"),
    ("OPIP_COLOR", "Color mode: auto, always, or never"),
    ("OPIP_NO_COLOR", "Disable color when set (non-empty)"),
    ("OPIP_FORCE_COLOR", "Force color when set (non-empty)"),
    ("NO_COLOR", "Standard; disables color when set"),
    ("FORCE_COLOR", "Standard; enables color when set"),
    ("PIP_RNS_CONFIG", "pip-rns config directory; aliases resolve for rns:// installs"),
]

COMMAND_SUMMARY = [
    ("create", "Build an offline .opip bundle from PyPI wheels"),
    ("install", "Install a bundle from file, rns://, URL, FTP, or git"),
    ("export", "Copy a verified bundle for sneakernet sharing"),
    ("verify", "Check integrity, authenticity, and provenance"),
    ("info", "Show bundle metadata"),
    ("update", "Rebuild a registered bundle from PyPI"),
    ("uninstall", "Remove packages from a registered bundle name"),
    ("uninstall-file", "Uninstall using a .opip file path"),
    ("open", "Interactive install menu (Windows double-click)"),
    ("list", "List registered bundles or installs"),
    ("register-windows", "Explorer file association and context menus"),
    ("unregister-windows", "Remove Windows registration"),
    ("help", "Interactive help and per-command reference"),
    ("keygen", "Generate a Reticulum identity for bundle signing"),
]

EXAMPLES = [
    ("opip help create", "Detailed help for create"),
    ("opip create --help", "Same as above (argparse)"),
    ("opip create", "Auto-detect project and build bundle"),
    ("opip create -r req.txt --platform win_amd64 --python 3.12", "Windows bundle"),
    ("opip create --platform universal --python 3.12", "Multi-OS bundle"),
    ("opip install ./my-bundle.opip --user", "User install offline"),
    ("opip export my-bundle -o /media/usb/pkg.opip", "Copy to USB"),
]
