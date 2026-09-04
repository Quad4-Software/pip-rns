"""Thin .opipd delta packs for scarce USB/RNS updates."""

from __future__ import annotations

import json
import os
import shutil
import tempfile

from opip.bundle import (
    extract_bundle,
    write_bundle_zip,
)
from opip.integrity import (
    build_integrity,
    collect_files,
    dump_integrity,
    file_hash,
)
from opip.lockfile import diff_locks, dump_json, make_lock, make_sbom
from opip.manifest import BUNDLE_EXTENSION, dump_manifest, make_manifest, utc_now_iso
from opip.publisher_meta import PUBLISHER_FILE, load_publisher
from opip.safe_zip import extract_zip_safe, safe_artifact_name
from opip.signing import sign_bundle

DELTA_EXTENSION = ".opipd"
DELTA_FORMAT = "opip-delta/1"


class DeltaError(Exception):
    pass


def create_delta(old_bundle, new_bundle, output_path):
    """Build a thin delta from old_bundle to new_bundle.

    Packs only added/changed wheels plus delta.json describing removals.
    """
    old_bundle = os.path.abspath(old_bundle)
    new_bundle = os.path.abspath(new_bundle)
    if not output_path.endswith(DELTA_EXTENSION):
        output_path = output_path + DELTA_EXTENSION

    old_ctx = extract_bundle(old_bundle)
    new_ctx = extract_bundle(new_bundle)
    try:
        old_manifest = old_ctx["manifest"]
        new_manifest = new_ctx["manifest"]
        diff = diff_locks(
            old_manifest.get("wheels", []), new_manifest.get("wheels", []),
        )

        base_sha = file_hash(old_bundle)
        delta_meta = {
            "format": DELTA_FORMAT,
            "created": utc_now_iso(),
            "base_sha256": base_sha,
            "base_name": old_manifest.get("name"),
            "target_name": new_manifest.get("name"),
            "added": diff["added"],
            "changed": diff["changed"],
            "removed": diff["removed"],
            "unchanged": diff["unchanged"],
            "target_manifest": new_manifest,
        }

        tmpdir = tempfile.mkdtemp(prefix="opip-delta-")
        try:
            wheels_dir = os.path.join(tmpdir, "wheels")
            os.makedirs(wheels_dir)
            new_wheels = os.path.join(new_ctx["dest_dir"], "wheels")
            for filename in diff["added"] + diff["changed"]:
                src = os.path.join(new_wheels, safe_artifact_name(filename))
                if not os.path.isfile(src):
                    raise DeltaError(f"Missing wheel in new bundle: {filename}")
                shutil.copy2(
                    src, os.path.join(wheels_dir, safe_artifact_name(filename)),
                )

            # Carry lock/sbom/publisher from target for apply
            for name in ("lock.json", "sbom.json", PUBLISHER_FILE, "requirements.txt"):
                src = os.path.join(new_ctx["dest_dir"], name)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(tmpdir, name))

            with open(os.path.join(tmpdir, "delta.json"), "w", encoding="utf-8") as fh:
                fh.write(dump_json(delta_meta))

            all_files = collect_files(tmpdir)
            integrity = build_integrity(all_files, base_dir=tmpdir)
            with open(
                os.path.join(tmpdir, "integrity.json"), "w", encoding="utf-8",
            ) as fh:
                fh.write(dump_integrity(integrity))

            write_bundle_zip(output_path, tmpdir)
            return output_path, delta_meta
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    finally:
        shutil.rmtree(old_ctx["dest_dir"], ignore_errors=True)
        shutil.rmtree(new_ctx["dest_dir"], ignore_errors=True)


def apply_delta(base_bundle, delta_path, output_path, identity_path=None):
    """Apply .opipd onto base .opip. Fail closed if base_sha256 mismatches.
    """
    base_bundle = os.path.abspath(base_bundle)
    delta_path = os.path.abspath(delta_path)
    if not output_path.endswith(BUNDLE_EXTENSION):
        output_path = output_path + BUNDLE_EXTENSION

    actual = file_hash(base_bundle)
    delta_dir = tempfile.mkdtemp(prefix="opip-delta-apply-")
    try:
        extract_zip_safe(delta_path, delta_dir)
        delta_json = os.path.join(delta_dir, "delta.json")
        if not os.path.isfile(delta_json):
            raise DeltaError("Invalid delta: missing delta.json")
        with open(delta_json, encoding="utf-8") as fh:
            meta = json.load(fh)
        expected = meta.get("base_sha256")
        if not expected or expected != actual:
            raise DeltaError(
                "Base bundle hash mismatch. expected {}, got {}".format(
                    (expected or "")[:16], actual[:16],
                ),
            )

        base_ctx = extract_bundle(base_bundle)
        try:
            out_dir = tempfile.mkdtemp(prefix="opip-apply-")
            try:
                # Start from base contents
                for name in os.listdir(base_ctx["dest_dir"]):
                    src = os.path.join(base_ctx["dest_dir"], name)
                    dst = os.path.join(out_dir, name)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)

                wheels_out = os.path.join(out_dir, "wheels")
                os.makedirs(wheels_out, exist_ok=True)

                for filename in meta.get("removed") or []:
                    path = os.path.join(wheels_out, safe_artifact_name(filename))
                    if os.path.isfile(path):
                        os.remove(path)

                delta_wheels = os.path.join(delta_dir, "wheels")
                if os.path.isdir(delta_wheels):
                    for filename in os.listdir(delta_wheels):
                        if filename.endswith(".whl"):
                            shutil.copy2(
                                os.path.join(delta_wheels, filename),
                                os.path.join(wheels_out, safe_artifact_name(filename)),
                            )

                target_manifest = meta.get("target_manifest")
                if not target_manifest:
                    raise DeltaError("Delta missing target_manifest")

                # Refresh wheel list from disk + target metadata when possible
                wheel_entries = list(target_manifest.get("wheels") or [])
                on_disk = {f for f in os.listdir(wheels_out) if f.endswith(".whl")}
                wheel_entries = [
                    w for w in wheel_entries if w.get("filename") in on_disk
                ]

                manifest = make_manifest(
                    name=target_manifest.get("name") or meta.get("target_name"),
                    requirements=target_manifest.get("requirements") or [],
                    wheels=wheel_entries,
                    python_version=target_manifest.get("python_version"),
                    platform_tag=target_manifest.get("platform"),
                    extras={
                        "pinned_requirements": target_manifest.get(
                            "pinned_requirements",
                        )
                        or [],
                        "platforms": target_manifest.get("platforms") or [],
                    },
                )
                with open(
                    os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8",
                ) as fh:
                    fh.write(dump_manifest(manifest))

                for name in (
                    "lock.json",
                    "sbom.json",
                    "requirements.txt",
                    PUBLISHER_FILE,
                ):
                    src = os.path.join(delta_dir, name)
                    if os.path.isfile(src):
                        shutil.copy2(src, os.path.join(out_dir, name))
                    elif name in ("lock.json", "sbom.json"):
                        # Rebuild if missing
                        if name == "lock.json":
                            data = make_lock(manifest, wheel_entries)
                        else:
                            publisher = None
                            pub_path = os.path.join(out_dir, PUBLISHER_FILE)
                            if os.path.isfile(pub_path):
                                with open(pub_path, encoding="utf-8") as fh:
                                    publisher = load_publisher(fh.read())
                            data = make_sbom(
                                manifest, wheel_entries, publisher=publisher,
                            )
                        with open(
                            os.path.join(out_dir, name), "w", encoding="utf-8",
                        ) as fh:
                            fh.write(dump_json(data))

                # Drop old integrity and rebuild
                integ = os.path.join(out_dir, "integrity.json")
                if os.path.isfile(integ):
                    os.remove(integ)
                all_files = collect_files(out_dir)
                integrity = build_integrity(all_files, base_dir=out_dir)
                with open(integ, "w", encoding="utf-8") as fh:
                    fh.write(dump_integrity(integrity))

                write_bundle_zip(output_path, out_dir)
                if identity_path:
                    sign_bundle(output_path, identity_path)
                return output_path
            finally:
                shutil.rmtree(out_dir, ignore_errors=True)
        finally:
            shutil.rmtree(base_ctx["dest_dir"], ignore_errors=True)
    finally:
        shutil.rmtree(delta_dir, ignore_errors=True)
