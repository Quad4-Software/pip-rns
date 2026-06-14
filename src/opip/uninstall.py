"""Uninstall packages that were installed from a bundle."""

import os
import shutil
import subprocess
import sys

from opip.storage import Store


class UninstallError(Exception):
    pass


def _pip_uninstall(packages, user=False):
    cmd = [sys.executable, "-m", "pip", "uninstall", "-y"] + packages
    if user:
        cmd.append("--user")
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True
    )
    if result.returncode != 0:
        raise UninstallError(
            "pip uninstall failed:\n{0}".format(result.stderr or result.stdout)
        )


def _manual_uninstall(packages, target_dir):
    """Remove package directories matching installed names from target."""
    if not os.path.isdir(target_dir):
        return
    pkg_norms = {p.replace("_", "-").lower() for p in packages}
    for name in list(os.listdir(target_dir)):
        lower = name.replace("_", "-").lower()
        matched = False
        for pkg_norm in pkg_norms:
            if lower == pkg_norm or lower.startswith(pkg_norm + "-"):
                matched = True
                break
        if matched:
            path = os.path.join(target_dir, name)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.isfile(path):
                os.remove(path)


def uninstall_bundle(bundle_name, store=None, user=False, target=None):
    """
    Uninstall packages recorded for a bundle.

    Returns list of uninstalled package names.
    """
    store = store or Store()
    record = store.get_install(bundle_name)
    if record is None:
        raise UninstallError(
            "No install record for bundle: {0}".format(bundle_name)
        )

    packages = record.get("packages", [])
    install_target = target or record.get("target")

    pip_ok = False
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _pip_uninstall(packages, user=user)
        pip_ok = True
    except (subprocess.CalledProcessError, FileNotFoundError, UninstallError):
        pip_ok = False

    if not pip_ok:
        if install_target:
            _manual_uninstall(packages, install_target)
        else:
            raise UninstallError(
                "Could not uninstall via pip and no install target recorded"
            )

    store.remove_install(bundle_name)
    return packages
