"""Update bundles by re-fetching wheels and rebuilding."""

import os
import shutil

from opip.bundle import create_bundle, verify_bundle
from opip.install import install_bundle
from opip.storage import Store
from opip.uninstall import uninstall_bundle


class UpdateError(Exception):
    pass


def update_bundle(
    bundle_name,
    output_path=None,
    store=None,
    reinstall=True,
    user=False,
    target=None,
):
    """
    Re-create a bundle from its stored requirements and optionally reinstall.

    Requires network access on the machine running update.
    """
    store = store or Store()
    entry = store.get_bundle(bundle_name)
    if entry is None:
        raise UpdateError("Bundle not registered: {0}".format(bundle_name))

    old_path = entry["path"]
    if not os.path.isfile(old_path):
        raise UpdateError("Bundle file missing: {0}".format(old_path))

    from opip.bundle import bundle_info

    manifest = bundle_info(old_path)
    requirements = manifest.get("requirements", [])
    if not requirements:
        raise UpdateError("Bundle has no requirements to update from")

    output_path = output_path or old_path
    backup = old_path + ".bak"
    if os.path.isfile(old_path) and output_path == old_path:
        shutil.copy2(old_path, backup)

    try:
        create_bundle(
            output_path,
            requirements,
            name=manifest.get("name"),
            py_version=manifest.get("python_version"),
            platform_tag=manifest.get("platform"),
        )
        errors, new_manifest = verify_bundle(output_path)
        if errors:
            raise UpdateError(
                "Updated bundle failed verification:\n" + "\n".join(errors)
            )

        store.register_bundle(bundle_name, output_path, new_manifest)

        if reinstall:
            try:
                uninstall_bundle(bundle_name, store=store, user=user, target=target)
            except Exception:
                pass
            install_bundle(output_path, target=target, user=user, store=store)

        if os.path.isfile(backup):
            os.remove(backup)

        return output_path

    except Exception:
        if os.path.isfile(backup):
            shutil.move(backup, old_path)
        raise
