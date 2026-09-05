# Copyright (c) 2026, Quad4 (quad4.io)
"""Update bundles by re-fetching wheels and rebuilding."""

import os
import shutil

from opip.bundle import bundle_info, create_bundle, extract_bundle, verify_bundle
from opip.install import InstallError, _venv_python, install_bundle
from opip.lockfile import diff_locks
from opip.signing import has_signature
from opip.storage import Store


class UpdateError(Exception):
    pass


def _path_is_venv(path):
    """True when path looks like a Python virtualenv root."""
    if not path or not os.path.isdir(path):
        return False
    return os.path.isfile(_venv_python(path))


def _resolve_reinstall_dest(store, bundle_name, target=None, user=False, venv=None):
    """Pick reinstall destination from CLI flags, then install record, then prefs.

    Returns (target, user, venv).
    """
    if venv:
        return None, False, os.path.abspath(os.path.expanduser(venv))
    if target:
        return os.path.abspath(os.path.expanduser(target)), user, None
    if user:
        return None, True, None

    record = store.get_install(bundle_name)
    if record:
        recorded = record.get("target")
        if recorded and _path_is_venv(recorded):
            return None, False, recorded
        if recorded:
            return recorded, False, None

    preferred = store.get_preferred_target(bundle_name)
    if preferred and _path_is_venv(preferred):
        return None, False, preferred
    if preferred:
        return preferred, False, None

    return None, False, None


def update_bundle(
    bundle_name,
    output_path=None,
    store=None,
    reinstall=True,
    user=False,
    target=None,
    venv=None,
    no_interactive=False,
    identity_path=None,
    index_url=None,
    find_links=None,
    offline=False,
    emit_delta=None,
):
    """Re-create a bundle from its stored requirements and optionally reinstall.

    Reuses unchanged wheels from the previous bundle when hashes match.
    Reinstall uses --upgrade/--force-reinstall instead of uninstall-first
    so a failed refresh does not leave packages removed.
    """
    store = store or Store()
    entry = store.get_bundle(bundle_name)
    if entry is None:
        raise UpdateError(f"Bundle not registered: {bundle_name}")

    old_path = entry["path"]
    if not os.path.isfile(old_path):
        raise UpdateError(f"Bundle file missing: {old_path}")

    manifest = bundle_info(old_path)
    requirements = manifest.get("requirements", [])
    if not requirements:
        raise UpdateError("Bundle has no requirements to update from")

    output_path = output_path or old_path
    backup = old_path + ".bak"
    restored = False
    if os.path.isfile(old_path) and os.path.abspath(output_path) == os.path.abspath(
        old_path,
    ):
        shutil.copy2(old_path, backup)

    old_ctx = None
    try:
        if has_signature(old_path) and not identity_path:
            from opip import terminal

            terminal.warn(
                "Previous bundle was signed. Pass --identity to re-sign the update, "
                "or the new file will be unsigned.",
            )

        old_ctx = extract_bundle(old_path)
        reuse_dir = os.path.join(old_ctx["dest_dir"], "wheels")

        create_bundle(
            output_path,
            requirements,
            name=manifest.get("name"),
            py_version=manifest.get("python_version"),
            platform_tag=manifest.get("platform"),
            identity_path=identity_path,
            index_url=index_url,
            find_links=find_links,
            offline=offline,
            reuse_wheels_dir=reuse_dir if os.path.isdir(reuse_dir) else None,
        )
        errors, new_manifest = verify_bundle(output_path)
        if errors:
            raise UpdateError(
                "Updated bundle failed verification:\n" + "\n".join(errors),
            )

        diff = diff_locks(manifest.get("wheels", []), new_manifest.get("wheels", []))
        from opip import terminal

        terminal.info(
            "Update wheels: +{} ~{} -{} ={}".format(
                len(diff["added"]),
                len(diff["changed"]),
                len(diff["removed"]),
                len(diff["unchanged"]),
            ),
        )

        if emit_delta:
            from opip.delta import create_delta

            base_for_delta = backup if os.path.isfile(backup) else old_path
            create_delta(base_for_delta, output_path, emit_delta)

        store.register_bundle(bundle_name, output_path, new_manifest)

        if reinstall:
            dest_target, dest_user, dest_venv = _resolve_reinstall_dest(
                store,
                bundle_name,
                target=target,
                user=user,
                venv=venv,
            )
            try:
                install_bundle(
                    output_path,
                    target=dest_target,
                    user=dest_user,
                    replace=True,
                    store=store,
                    venv=dest_venv,
                    no_interactive=no_interactive,
                    target_explicit=dest_target is not None,
                )
            except InstallError as exc:
                raise UpdateError(
                    "Bundle file was rebuilt, but reinstall failed:\n" + str(exc),
                ) from exc

        if os.path.isfile(backup):
            os.remove(backup)

        return output_path

    except Exception:
        if os.path.isfile(backup) and not restored:
            shutil.move(backup, old_path)
            restored = True
        raise
    finally:
        if old_ctx is not None:
            shutil.rmtree(old_ctx["dest_dir"], ignore_errors=True)
