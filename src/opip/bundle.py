"""Create, read, write, and verify offline wheel bundles (.opip)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

from opip.fetch import download_wheels_parallel
from opip.integrity import (
    build_integrity,
    collect_files,
    dump_integrity,
    load_integrity,
    verify_integrity,
)
from opip.keys import export_public_record, identity_hash
from opip.lockfile import dump_json, make_lock, make_sbom
from opip.manifest import BUNDLE_EXTENSION, dump_manifest, load_manifest, make_manifest
from opip.provenance import ProvenanceError, build_wheel_record, verify_wheel_provenance
from opip.publisher_meta import PUBLISHER_FILE, dump_publisher, make_publisher
from opip.resolver import (
    UNIVERSAL_PLATFORMS,
    detect_platform,
    detect_python_version,
    is_universal_platform,
    resolve_requirements,
)
from opip.safe_zip import UnsafeZipError, extract_zip_safe, safe_artifact_name
from opip.signing import has_signature, sign_bundle, verify_bundle_signature
from opip.wheel import read_wheel_metadata


class BundleError(Exception):
    pass


def read_requirements_file(path):
    """Read requirements from a text file, one per line."""
    reqs = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                reqs.append(line)
    return reqs


def build_project_wheel(project_dir, wheels_dir):
    """Build a wheel for the local project using pip wheel."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--wheel-dir",
            wheels_dir,
            "--no-deps",
        ],
        cwd=project_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    if result.returncode != 0:
        raise BundleError(
            "Failed to build project wheel:\n{0}".format(result.stderr or result.stdout)
        )
    for name in os.listdir(wheels_dir):
        if name.endswith(".whl"):
            return os.path.join(wheels_dir, name)
    raise BundleError("No wheel produced from project directory")


def create_bundle(
    output_path,
    requirements,
    name=None,
    py_version=None,
    platform_tag=None,
    include_deps=True,
    requirements_file=None,
    project_dir=None,
    include_project=False,
    jobs=8,
    use_cache=True,
    require_pypi_hash=False,
    publisher_name=None,
    publisher_contact=None,
    identity_path=None,
):
    """Fetch wheels and pack them into an integrity-backed .opip bundle."""
    if requirements_file:
        requirements = read_requirements_file(requirements_file)
    if not requirements:
        raise BundleError("No requirements specified")

    py_version = py_version or detect_python_version()
    platform_tag = platform_tag or detect_platform()
    name = name or os.path.splitext(os.path.basename(output_path))[0]

    if not output_path.endswith(BUNDLE_EXTENSION):
        output_path = output_path + BUNDLE_EXTENSION

    wheels_specs = resolve_requirements(
        requirements,
        py_version,
        platform_tag,
        include_deps=include_deps,
        jobs=jobs,
        progress=True,
    )

    if require_pypi_hash:
        for spec in wheels_specs:
            if "sha256" not in (spec.get("digests") or {}):
                raise BundleError(
                    "PyPI provides no sha256 for {0}. cannot satisfy --require-pypi-hash".format(
                        spec.get("filename")
                    )
                )

    tmpdir = tempfile.mkdtemp(prefix="opip-create-")
    wheels_dir = os.path.join(tmpdir, "wheels")
    os.makedirs(wheels_dir)

    wheel_entries = []
    install_reqs = list(requirements)
    signer_identity = None
    if identity_path:
        signer_identity = identity_hash(identity_path)

    try:
        download_wheels_parallel(
            wheels_specs,
            wheels_dir,
            jobs=jobs,
            use_cache=use_cache,
            require_pypi_hash=require_pypi_hash,
        )
        for spec in wheels_specs:
            filename = safe_artifact_name(spec["filename"])
            path = os.path.join(wheels_dir, filename)
            source = "cache" if use_cache else "pypi"
            wheel_entries.append(build_wheel_record(path, spec=spec, source=source))

        if include_project and project_dir:
            project_wheel = build_project_wheel(project_dir, wheels_dir)
            project_name = os.path.basename(os.path.normpath(project_dir))
            wheel_entries.append(
                build_wheel_record(
                    project_wheel,
                    spec={"project_name": project_name},
                    source="local",
                    built_from=os.path.abspath(project_dir),
                )
            )
            meta = read_wheel_metadata(project_wheel)
            pkg_req = "{0}=={1}".format(meta["name"], meta["version"])
            if pkg_req not in install_reqs:
                install_reqs.append(pkg_req)

        pinned_reqs = [
            "{0}=={1}".format(w["package"], w["version"]) for w in wheel_entries
        ]

        req_path = os.path.join(tmpdir, "requirements.txt")
        with open(req_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(pinned_reqs) + "\n")

        manifest = make_manifest(
            name=name,
            requirements=install_reqs,
            wheels=wheel_entries,
            python_version=py_version,
            platform_tag=platform_tag,
            extras={
                "pinned_requirements": pinned_reqs,
                "platforms": list(UNIVERSAL_PLATFORMS)
                if is_universal_platform(platform_tag)
                else [platform_tag],
            },
        )
        with open(os.path.join(tmpdir, "manifest.json"), "w", encoding="utf-8") as fh:
            fh.write(dump_manifest(manifest))

        lock_data = make_lock(manifest, wheel_entries)
        with open(os.path.join(tmpdir, "lock.json"), "w", encoding="utf-8") as fh:
            fh.write(dump_json(lock_data))

        publisher_record = None
        if publisher_name or signer_identity:
            pub_name = publisher_name or name
            trust = None
            if identity_path:
                trust = export_public_record(
                    identity_path, pub_name, contact=publisher_contact
                )
            publisher_record = make_publisher(
                pub_name,
                identity=signer_identity,
                contact=publisher_contact,
                public_record=trust,
            )
            with open(
                os.path.join(tmpdir, PUBLISHER_FILE), "w", encoding="utf-8"
            ) as fh:
                fh.write(dump_publisher(publisher_record))

        sbom_data = make_sbom(manifest, wheel_entries, publisher=publisher_record)
        with open(os.path.join(tmpdir, "sbom.json"), "w", encoding="utf-8") as fh:
            fh.write(dump_json(sbom_data))

        all_files = collect_files(tmpdir)
        integrity = build_integrity(all_files, base_dir=tmpdir)
        integrity_path = os.path.join(tmpdir, "integrity.json")
        integrity_bytes = dump_integrity(integrity)
        with open(integrity_path, "w", encoding="utf-8") as fh:
            fh.write(integrity_bytes)

        write_bundle_zip(output_path, tmpdir)

        if identity_path:
            sign_bundle(output_path, identity_path)

        return output_path

    except ProvenanceError as exc:
        raise BundleError(str(exc))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def write_bundle_zip(output_path, source_dir):
    """Pack source_dir contents into a .opip zip archive."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(source_dir):
            for name in files:
                full = os.path.join(root, name)
                arc = os.path.relpath(full, source_dir).replace("\\", "/")
                zf.write(full, arc)


def extract_bundle(bundle_path, dest_dir=None):
    """Extract bundle to dest_dir. Returns bundle context dict."""
    if not os.path.isfile(bundle_path):
        raise BundleError("Bundle not found: {0}".format(bundle_path))

    dest_dir = dest_dir or tempfile.mkdtemp(prefix="opip-extract-")
    try:
        extract_zip_safe(bundle_path, dest_dir)
    except UnsafeZipError as exc:
        raise BundleError(str(exc))

    manifest_path = os.path.join(dest_dir, "manifest.json")
    integrity_path = os.path.join(dest_dir, "integrity.json")

    if not os.path.isfile(manifest_path):
        raise BundleError("Invalid bundle: missing manifest.json")
    if not os.path.isfile(integrity_path):
        raise BundleError("Invalid bundle: missing integrity.json")

    with open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = load_manifest(fh.read())
    with open(integrity_path, "r", encoding="utf-8") as fh:
        try:
            integrity = load_integrity(fh.read())
        except ValueError as exc:
            raise BundleError(str(exc))

    publisher = None
    pub_path = os.path.join(dest_dir, PUBLISHER_FILE)
    if os.path.isfile(pub_path):
        with open(pub_path, "r", encoding="utf-8") as fh:
            publisher = json.load(fh)

    return {
        "dest_dir": dest_dir,
        "manifest": manifest,
        "integrity": integrity,
        "publisher": publisher,
    }


def verify_bundle_contents(
    bundle_ctx,
    bundle_path=None,
    signer=None,
    require_signature=False,
    require_pypi_hash=False,
):
    """Full integrity, authenticity, and provenance verification."""
    dest_dir = bundle_ctx["dest_dir"]
    manifest = bundle_ctx["manifest"]
    integrity = bundle_ctx["integrity"]
    errors = []

    all_files = collect_files(dest_dir, exclude=["integrity.json"])
    errors.extend(verify_integrity(dest_dir, integrity, all_files=all_files))

    if bundle_path:
        if has_signature(bundle_path):
            errors.extend(verify_bundle_signature(bundle_path, signer))
        elif require_signature:
            errors.append("Bundle has no .rsg sidecar but --require-signature was set.")

    wheels_dir = os.path.join(dest_dir, "wheels")
    for record in manifest.get("wheels", []):
        raw_name = record.get("filename", "")
        try:
            filename = safe_artifact_name(raw_name)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        whl = os.path.join(wheels_dir, filename)
        if not record.get("sha256"):
            errors.append("Missing sha256 for wheel: {0}".format(filename))
        if os.path.isfile(whl):
            errors.extend(
                verify_wheel_provenance(
                    whl, record, require_pypi_hash=require_pypi_hash
                )
            )
        else:
            errors.append("Missing wheel file: {0}".format(filename))

    return errors


def verify_bundle(
    bundle_path, signer=None, require_signature=False, require_pypi_hash=False
):
    """Verify bundle. Returns (errors, manifest)."""
    ctx = extract_bundle(bundle_path)
    try:
        errors = verify_bundle_contents(
            ctx,
            bundle_path=os.path.abspath(bundle_path),
            signer=signer,
            require_signature=require_signature,
            require_pypi_hash=require_pypi_hash,
        )
        return errors, ctx["manifest"]
    finally:
        shutil.rmtree(ctx["dest_dir"], ignore_errors=True)


def bundle_info(bundle_path):
    """Return manifest dict without full extraction verification."""
    with zipfile.ZipFile(bundle_path, "r") as zf:
        if "manifest.json" not in zf.namelist():
            raise BundleError("Invalid bundle: missing manifest.json")
        manifest = load_manifest(zf.read("manifest.json").decode("utf-8"))
    return manifest
