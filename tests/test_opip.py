"""Tests for opip bundle integrity, sidecars, and remote resolution."""

from __future__ import annotations

import os
import tempfile
import zipfile

from opip import fetch as opip_fetch
from opip import resolver as opip_resolver
from opip.bundle import verify_bundle, write_bundle_zip
from opip.integrity import (
    build_integrity,
    collect_files,
    dump_integrity,
    file_hash,
    verify_integrity,
)
from opip.lockfile import dump_json, make_lock, make_sbom
from opip.manifest import dump_manifest, make_manifest
from opip.provenance import build_wheel_record
from opip.remote_resolve import resolve_remote_source
from opip.resolver import detect_python_version
from opip.sidecar import copy_sidecar_from_dir, fetch_sidecar_if_available
from opip.signing import signature_path
from opip.sources import is_rns_source, parse_git_source
from pip_rns.aliases import AliasManager


def _make_minimal_wheel(path: str, name: str = "pkg", version: str = "1.0.0") -> None:
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{name}/__init__.py", "")
        zf.writestr(
            f"{name}-{version}.dist-info/METADATA",
            metadata,
        )
        zf.writestr(
            f"{name}-{version}.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )


def _make_test_bundle(tmpdir: str, bundle_path: str) -> None:
    wheels_dir = os.path.join(tmpdir, "wheels")
    os.makedirs(wheels_dir)
    whl_name = "pkg-1.0.0-py3-none-any.whl"
    whl_path = os.path.join(wheels_dir, whl_name)
    _make_minimal_wheel(whl_path)

    wheel_entries = [build_wheel_record(whl_path, source="local")]
    requirements = ["pkg==1.0.0"]
    manifest = make_manifest(
        name="test-bundle",
        requirements=requirements,
        wheels=wheel_entries,
        python_version=detect_python_version(),
        platform_tag="any",
    )
    with open(os.path.join(tmpdir, "manifest.json"), "w", encoding="utf-8") as fh:
        fh.write(dump_manifest(manifest))
    with open(os.path.join(tmpdir, "requirements.txt"), "w", encoding="utf-8") as fh:
        fh.write("pkg==1.0.0\n")
    with open(os.path.join(tmpdir, "lock.json"), "w", encoding="utf-8") as fh:
        fh.write(dump_json(make_lock(manifest, wheel_entries)))
    with open(os.path.join(tmpdir, "sbom.json"), "w", encoding="utf-8") as fh:
        fh.write(dump_json(make_sbom(manifest, wheel_entries)))

    all_files = collect_files(tmpdir)
    integrity = build_integrity(all_files, base_dir=tmpdir)
    with open(os.path.join(tmpdir, "integrity.json"), "w", encoding="utf-8") as fh:
        fh.write(dump_integrity(integrity))

    write_bundle_zip(bundle_path, tmpdir)


def test_file_hash_stable():
    with tempfile.NamedTemporaryFile(delete=False) as fh:
        fh.write(b"hello")
        path = fh.name
    try:
        assert file_hash(path) == file_hash(path)
    finally:
        os.unlink(path)


def test_verify_integrity_detects_tamper():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "data.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("original")
        integrity = build_integrity([path], base_dir=tmpdir)
        assert verify_integrity(tmpdir, integrity) == []
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("tampered")
        errors = verify_integrity(tmpdir, integrity)
        assert len(errors) == 1
        assert "Hash mismatch" in errors[0]


def test_verify_bundle_ok():
    with tempfile.TemporaryDirectory() as tmpdir:
        bundle_path = os.path.join(tmpdir, "test.opip")
        work = os.path.join(tmpdir, "work")
        os.makedirs(work)
        _make_test_bundle(work, bundle_path)
        errors, manifest = verify_bundle(bundle_path)
        assert errors == []
        assert manifest["name"] == "test-bundle"


def test_signature_path_sidecar():
    assert signature_path("/tmp/bundle.opip") == "/tmp/bundle.opip.rsg"


def test_copy_sidecar_from_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        bundle_path = os.path.join(tmpdir, "bundle.opip")
        with open(bundle_path, "wb") as fh:
            fh.write(b"bundle")
        sidecar = signature_path(bundle_path)
        with open(sidecar, "w", encoding="utf-8") as fh:
            fh.write("sig")
        copy_dir = os.path.join(tmpdir, "copy")
        os.makedirs(copy_dir)
        other_bundle = os.path.join(copy_dir, "bundle.opip")
        with open(other_bundle, "wb") as fh:
            fh.write(b"bundle")
        copy_sidecar_from_dir(other_bundle, tmpdir)
        assert os.path.isfile(signature_path(other_bundle))


def test_fetch_sidecar_if_available_missing_url():
    with tempfile.TemporaryDirectory() as tmpdir:
        bundle_path = os.path.join(tmpdir, "bundle.opip")
        with open(bundle_path, "wb") as fh:
            fh.write(b"bundle")
        fetch_sidecar_if_available(bundle_path, source_url=None)
        assert not os.path.isfile(signature_path(bundle_path))


def test_is_rns_source():
    assert is_rns_source("rns://id/group/repo")
    assert is_rns_source("06a54b505bb67b25ef3f8097e8001edc/public/LXMFy")
    assert not is_rns_source("https://example.com/bundle.opip")


def test_parse_git_source_fragment():
    url, ref, subpath = parse_git_source(
        "git+https://github.com/example/repo.git#v1.0.0:dist/bundle.opip",
    )
    assert url == "https://github.com/example/repo.git"
    assert ref == "v1.0.0"
    assert subpath == "dist/bundle.opip"


def test_resolve_remote_source_alias():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = AliasManager(tmpdir)
        mgr.set("lxmfy", "06a54b505bb67b25ef3f8097e8001edc/public/LXMFy")
        os.environ["PIP_RNS_CONFIG"] = tmpdir
        try:
            resolved = resolve_remote_source("lxmfy@v1.0.0")
            assert resolved == "06a54b505bb67b25ef3f8097e8001edc/public/LXMFy@v1.0.0"
        finally:
            os.environ.pop("PIP_RNS_CONFIG", None)


def test_user_agent_version():
    import opip
    from pip_rns.version import __version__

    assert __version__ in opip_fetch.USER_AGENT
    assert "Quad4-Software/pip-rns" in opip_fetch.USER_AGENT
    assert opip_fetch.USER_AGENT == opip_resolver.USER_AGENT
    assert opip.__version__ == __version__


def test_rns_fetch_parse_ref():
    from opip.rns_fetch import _parse_ref

    remote, ref, artifact = _parse_ref("rns://id/group/repo@v1.0.0:bundle.opip")
    assert remote == "rns://id/group/repo"
    assert ref == "v1.0.0"
    assert artifact == "bundle.opip"
