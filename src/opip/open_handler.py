"""Interactive handler for opening .opip bundles (Windows double-click)."""

import os
import sys

from opip.bundle import bundle_info
from opip.install import install_bundle
from opip.storage import Store
from opip.uninstall import uninstall_bundle
from opip.update import update_bundle


class OpenError(Exception):
    pass


def open_bundle(bundle_path, store=None, user=False, target=None):
    """
    Prompt to install, update, replace, or uninstall a bundle.

    Used for Windows file association double-click.
    """
    bundle_path = os.path.abspath(bundle_path)
    if not os.path.isfile(bundle_path):
        raise OpenError("Bundle not found: {0}".format(bundle_path))

    store = store or Store()
    manifest = bundle_info(bundle_path)
    name = manifest.get("name") or os.path.splitext(os.path.basename(bundle_path))[0]
    installed = store.get_install(name) is not None

    if not sys.stdin.isatty():
        return install_bundle(
            bundle_path, target=target, user=user, store=store
        )

    sys.stdout.write("Bundle: {0}\n".format(name))
    sys.stdout.write(
        "Python {0} on {1}, {2} wheels\n".format(
            manifest.get("python_version"),
            manifest.get("platform"),
            len(manifest.get("wheels", [])),
        )
    )

    if not installed:
        sys.stdout.write("\n1) Install\n0) Cancel\nChoice: ")
        sys.stdout.flush()
        choice = _read_choice()
        if choice == "1":
            return install_bundle(
                bundle_path, target=target, user=user, store=store
            )
        return []

    sys.stdout.write(
        "\n1) Update (reinstall from this bundle file)\n"
        "2) Replace (uninstall then install)\n"
        "3) Uninstall\n"
        "0) Cancel\n"
        "Choice: "
    )
    sys.stdout.flush()
    choice = _read_choice()

    if choice == "1":
        return install_bundle(
            bundle_path, target=target, user=user, store=store
        )
    if choice == "2":
        uninstall_bundle(name, store=store, user=user, target=target)
        return install_bundle(
            bundle_path, target=target, user=user, store=store
        )
    if choice == "3":
        return uninstall_bundle(name, store=store, user=user, target=target)
    return []


def _read_choice():
    try:
        return input().strip()
    except EOFError:
        return "0"
