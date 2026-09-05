# Copyright (c) 2026, Quad4 (quad4.io)
"""Extract .opip bundles to a wheelhouse for pip/uv hand-off."""

from __future__ import annotations

import html
import os
import shutil

from opip.bundle import extract_bundle, verify_bundle
from opip.resolver import normalize_name
from opip.safe_zip import safe_artifact_name


class ExtractError(Exception):
    pass


def extract_to_wheelhouse(
    bundle_path,
    output_dir,
    *,
    simple_index=False,
    verify=True,
    signer=None,
    require_signature=False,
):
    """Verify (optional) and unpack wheels into output_dir.

    With simple_index=True, also write a minimal PEP 503 layout under output_dir.
    Returns (output_dir, wheel_count).
    """
    bundle_path = os.path.abspath(bundle_path)
    output_dir = os.path.abspath(output_dir)
    if not os.path.isfile(bundle_path):
        raise ExtractError(f"Bundle not found: {bundle_path}")

    if verify:
        errors, _manifest = verify_bundle(
            bundle_path,
            signer=signer,
            require_signature=require_signature,
        )
        if errors:
            raise ExtractError("Bundle verification failed:\n" + "\n".join(errors))

    ctx = extract_bundle(bundle_path)
    try:
        wheels_src = os.path.join(ctx["dest_dir"], "wheels")
        if not os.path.isdir(wheels_src):
            raise ExtractError("Bundle missing wheels/ directory")

        os.makedirs(output_dir, exist_ok=True)
        wheel_names = []
        for name in sorted(os.listdir(wheels_src)):
            if not name.endswith(".whl"):
                continue
            safe = safe_artifact_name(name)
            shutil.copy2(
                os.path.join(wheels_src, name),
                os.path.join(output_dir, safe),
            )
            wheel_names.append(safe)

        if simple_index:
            _write_simple_index(output_dir, wheel_names)

        return output_dir, len(wheel_names)
    finally:
        shutil.rmtree(ctx["dest_dir"], ignore_errors=True)


def _write_simple_index(root, wheel_names):
    """Write PEP 503 simple index: index.html + per-package dirs."""
    by_pkg = {}
    for filename in wheel_names:
        # name-ver-py-abi-plat.whl
        parts = filename.split("-")
        if len(parts) < 5:
            continue
        pkg = normalize_name(parts[0])
        by_pkg.setdefault(pkg, []).append(filename)

    index_links = []
    for pkg in sorted(by_pkg):
        pkg_dir = os.path.join(root, pkg)
        os.makedirs(pkg_dir, exist_ok=True)
        links = []
        for filename in sorted(by_pkg[pkg]):
            # Relative link from package dir to wheel in root
            href = html.escape(f"../{filename}")
            links.append(f'<a href="{href}">{html.escape(filename)}</a><br/>\n')
            # Also leave wheel in package dir as hard link or copy for find-links
            dest = os.path.join(pkg_dir, filename)
            src = os.path.join(root, filename)
            if not os.path.exists(dest):
                try:
                    os.link(src, dest)
                except OSError:
                    shutil.copy2(src, dest)
            links[-1] = (
                f'<a href="{html.escape(filename)}">{html.escape(filename)}</a><br/>\n'
            )
        with open(os.path.join(pkg_dir, "index.html"), "w", encoding="utf-8") as fh:
            fh.write("<!DOCTYPE html><html><body>\n")
            fh.writelines(links)
            fh.write("</body></html>\n")
        index_links.append(
            f'<a href="{html.escape(pkg)}/">{html.escape(pkg)}</a><br/>\n',
        )

    with open(os.path.join(root, "index.html"), "w", encoding="utf-8") as fh:
        fh.write("<!DOCTYPE html><html><body>\n")
        fh.writelines(index_links)
        fh.write("</body></html>\n")
