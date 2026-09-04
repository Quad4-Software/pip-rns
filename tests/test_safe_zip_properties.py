"""Property and fuzz tests for safe zip extraction and path containment."""

from __future__ import annotations

import contextlib
import os
import tempfile
import zipfile

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from opip.bundle import extract_bundle, verify_bundle, write_bundle_zip
from opip.integrity import (
    build_integrity,
    collect_files,
    dump_integrity,
    verify_integrity,
)
from opip.lockfile import dump_json, make_lock, make_sbom
from opip.manifest import dump_manifest, make_manifest
from opip.provenance import build_wheel_record
from opip.safe_zip import (
    UnsafeZipError,
    contain_path,
    extract_zip_safe,
    safe_artifact_name,
    safe_member_path,
)

# Path segment that cannot introduce traversal or absolute forms.
_SAFE_SEGMENT = st.from_regex(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,24}", fullmatch=True,
).filter(lambda s: s not in (".", "..") and ".." not in s)

_SAFE_REL_PATH = st.lists(_SAFE_SEGMENT, min_size=1, max_size=5).map(
    lambda parts: "/".join(parts),
)

_SAFE_ARTIFACT = st.from_regex(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,40}\.(whl|opip|rsg|json)",
    fullmatch=True,
).filter(lambda s: ".." not in s and "/" not in s and "\\" not in s)

_TRAVERSAL_NAME = st.one_of(
    st.just("../etc/passwd"),
    st.just("../../secret"),
    st.just("foo/../../bar"),
    st.just("/etc/passwd"),
    st.just("C:/Windows/system32"),
    st.just("\\Windows\\system32"),
    st.just("a/../../../b"),
    st.sampled_from(["..", "../", "./../x", "x/../y/../../z"]),
)


def _make_minimal_wheel(path: str, name: str = "pkg", version: str = "1.0.0") -> None:
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{name}/__init__.py", b"# ok\n")
        zf.writestr(
            f"{name}-{version}.dist-info/METADATA",
            metadata.encode("utf-8"),
        )
        zf.writestr(
            f"{name}-{version}.dist-info/WHEEL",
            b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        zf.writestr(
            f"{name}-{version}.dist-info/RECORD",
            f"{name}/__init__.py,,\n".encode(),
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
        python_version="3.12",
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


def test_normal_wheel_extract_roundtrip():
    """Realistic wheel member layout survives safe extract."""
    with tempfile.TemporaryDirectory() as tmpdir:
        whl = os.path.join(tmpdir, "pkg-1.0.0-py3-none-any.whl")
        dest = os.path.join(tmpdir, "out")
        _make_minimal_wheel(whl)
        extract_zip_safe(whl, dest)
        assert os.path.isfile(os.path.join(dest, "pkg", "__init__.py"))
        assert os.path.isfile(os.path.join(dest, "pkg-1.0.0.dist-info", "METADATA"))
        assert os.path.abspath(dest) == os.path.commonpath(
            [os.path.abspath(dest), os.path.abspath(os.path.join(dest, "pkg"))],
        )


def test_normal_bundle_create_verify_extract():
    """Create -> verify -> extract stays intact under safe zip."""
    with tempfile.TemporaryDirectory() as tmpdir:
        work = os.path.join(tmpdir, "work")
        os.makedirs(work)
        bundle = os.path.join(tmpdir, "test.opip")
        out = os.path.join(tmpdir, "extracted")
        _make_test_bundle(work, bundle)
        errors, manifest = verify_bundle(bundle)
        assert errors == []
        assert manifest["name"] == "test-bundle"
        extract_bundle(bundle, out)
        assert os.path.isfile(os.path.join(out, "manifest.json"))
        assert os.path.isfile(os.path.join(out, "integrity.json"))
        assert os.path.isdir(os.path.join(out, "wheels"))
        whls = [
            n for n in os.listdir(os.path.join(out, "wheels")) if n.endswith(".whl")
        ]
        assert len(whls) == 1
        wheel_out = os.path.join(tmpdir, "wheel_out")
        extract_zip_safe(os.path.join(out, "wheels", whls[0]), wheel_out)
        assert os.path.isfile(os.path.join(wheel_out, "pkg", "__init__.py"))


@given(path=_SAFE_REL_PATH)
@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_safe_member_path_accepts_nested_relative(path):
    with tempfile.TemporaryDirectory() as dest:
        resolved = safe_member_path(dest, path)
        assert resolved is not None
        assert os.path.commonpath([os.path.abspath(dest), resolved]) == os.path.abspath(
            dest,
        )
        assert resolved == os.path.abspath(os.path.join(dest, *path.split("/")))


@given(name=_TRAVERSAL_NAME)
@settings(max_examples=40, deadline=None)
def test_safe_member_path_rejects_traversal(name):
    with tempfile.TemporaryDirectory() as dest:
        try:
            result = safe_member_path(dest, name)
        except UnsafeZipError:
            return
        # Directory-only markers may return None
        assert result is None


@given(path=_SAFE_REL_PATH, payload=st.binary(min_size=0, max_size=4096))
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_extract_roundtrip_keeps_bytes_inside_dest(path, payload):
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "a.zip")
        dest = os.path.join(tmpdir, "out")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(path, payload)
            zf.writestr("ok/dir/", b"")
        extract_zip_safe(zip_path, dest)
        expected = os.path.join(dest, *path.split("/"))
        assert os.path.isfile(expected)
        with open(expected, "rb") as fh:
            assert fh.read() == payload
        for root, _dirs, files in os.walk(dest):
            for name in files:
                full = os.path.join(root, name)
                assert os.path.commonpath(
                    [os.path.abspath(dest), os.path.abspath(full)],
                ) == os.path.abspath(dest)


@given(bad=_TRAVERSAL_NAME, payload=st.binary(min_size=1, max_size=64))
@settings(max_examples=40, deadline=None)
def test_extract_rejects_malicious_member_names(bad, payload):
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "bad.zip")
        dest = os.path.join(tmpdir, "out")
        marker = os.path.join(tmpdir, "outside.txt")
        with open(marker, "wb") as fh:
            fh.write(b"safe")
        with zipfile.ZipFile(zip_path, "w") as zf:
            # Always include one safe file so zip is nonempty
            zf.writestr("legit.txt", b"ok")
            try:
                zf.writestr(bad, payload)
            except ValueError:
                # zipfile may reject some absolute names itself
                return
        try:
            extract_zip_safe(zip_path, dest)
        except UnsafeZipError:
            with open(marker, "rb") as fh:
                assert fh.read() == b"safe"
            return
        # If extraction succeeded, malicious path must not have escaped
        with open(marker, "rb") as fh:
            assert fh.read() == b"safe"
        for root, _dirs, files in os.walk(dest):
            for name in files:
                full = os.path.join(root, name)
                assert os.path.commonpath(
                    [os.path.abspath(dest), os.path.abspath(full)],
                ) == os.path.abspath(dest)


@given(name=_SAFE_ARTIFACT)
@settings(max_examples=50, deadline=None)
def test_safe_artifact_name_accepts_basename(name):
    assert safe_artifact_name(name) == name


@given(
    name=st.one_of(
        st.just(""),
        st.just("."),
        st.just(".."),
        st.just("../x.whl"),
        st.just("a/b.whl"),
        st.just("a\\b.whl"),
        st.just("/abs.whl"),
    ),
)
@settings(max_examples=20, deadline=None)
def test_safe_artifact_name_rejects_unsafe(name):
    try:
        safe_artifact_name(name)
        raise AssertionError(f"expected ValueError for {name!r}")
    except ValueError:
        pass


@given(path=_SAFE_REL_PATH)
@settings(max_examples=50, deadline=None)
def test_contain_path_accepts_relative(path):
    with tempfile.TemporaryDirectory() as root:
        target = contain_path(root, path)
        assert os.path.commonpath([os.path.abspath(root), target]) == os.path.abspath(
            root,
        )


@given(path=_TRAVERSAL_NAME)
@settings(max_examples=30, deadline=None)
def test_contain_path_rejects_escape(path):
    with tempfile.TemporaryDirectory() as root:
        try:
            contain_path(root, path)
            raise AssertionError(f"expected ValueError for {path!r}")
        except ValueError:
            pass


def _paths_are_file_compatible(paths):
    """True when no path is a prefix of another (avoids file/dir clashes)."""
    ordered = sorted(paths)
    for i, left in enumerate(ordered):
        prefix = left + "/"
        for right in ordered[i + 1 :]:
            if right.startswith(prefix) or right == left:
                return False
    return True


@given(
    files=st.dictionaries(
        keys=_SAFE_REL_PATH.filter(lambda p: not p.endswith("/")),
        values=st.binary(min_size=0, max_size=256),
        min_size=1,
        max_size=8,
    ).filter(lambda d: _paths_are_file_compatible(d.keys())),
)
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_integrity_roundtrip_on_safe_trees(files):
    with tempfile.TemporaryDirectory() as tmpdir:
        for rel, data in files.items():
            full = contain_path(tmpdir, rel)
            parent = os.path.dirname(full)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(full, "wb") as fh:
                fh.write(data)
        collected = collect_files(tmpdir)
        integrity = build_integrity(collected, base_dir=tmpdir)
        assert verify_integrity(tmpdir, integrity) == []


@given(
    escape=st.sampled_from(
        [
            "../outside.txt",
            "../../etc/passwd",
            "/tmp/abs.txt",
            "ok/../../evil.txt",
        ],
    ),
)
@settings(max_examples=20, deadline=None)
def test_integrity_rejects_escape_paths_in_map(escape):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "ok.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("x")
        integrity = build_integrity([path], base_dir=tmpdir)
        integrity["files"][escape] = "deadbeef"
        errors = verify_integrity(tmpdir, integrity)
        assert errors
        assert any(
            "escapes" in e.lower() or "absolute" in e.lower() or "path" in e.lower()
            for e in errors
        )


def test_fuzz_random_member_names_never_escape_dest():
    """Brute-force odd member names, assert no write outside dest."""
    import random

    rng = random.Random(20260723)
    samples = [
        "",
        ".",
        "./",
        "a/",
        "a/./b",
        "a//b",
        "./a/b",
        "a\\b",
        "a\\..\\b",
        "..\\..\\x",
        "....//....",
        "foo/./bar/../baz",
        "\x00evil",
        "\n../x",
        " " * 8,
        "a" * 200,
        "pkg-1.0.0.dist-info/METADATA",
        "nested/deep/path/file.txt",
    ]
    for _ in range(40):
        parts = []
        for _j in range(rng.randint(1, 4)):
            choice = rng.choice(
                [
                    "ok",
                    "pkg",
                    "..",
                    ".",
                    "",
                    "dist-info",
                    "x.y",
                    "../x",
                    "C:",
                    "abs",
                ],
            )
            parts.append(choice)
        samples.append("/".join(parts))

    with tempfile.TemporaryDirectory() as tmpdir:
        outside = os.path.join(tmpdir, "sentinel")
        with open(outside, "wb") as fh:
            fh.write(b"untouched")
        for i, name in enumerate(samples):
            dest = os.path.join(tmpdir, f"out-{i}")
            zip_path = os.path.join(tmpdir, f"fuzz-{i}.zip")
            try:
                with zipfile.ZipFile(zip_path, "w") as zf:
                    zf.writestr("keep.txt", b"keep")
                    if name and not name.endswith("/"):
                        zf.writestr(name, b"payload")
            except (ValueError, OSError, IndexError):
                # IndexError: Python 3.10 zipfile collapses NUL names to "" then crashes
                continue
            with contextlib.suppress(UnsafeZipError):
                extract_zip_safe(zip_path, dest)
            with open(outside, "rb") as fh:
                assert fh.read() == b"untouched"
            if os.path.isdir(dest):
                for root, _dirs, files in os.walk(dest):
                    for fname in files:
                        full = os.path.join(root, fname)
                        assert os.path.commonpath(
                            [os.path.abspath(dest), os.path.abspath(full)],
                        ) == os.path.abspath(dest)


def test_extract_rejects_file_dir_conflict():
    """Member that collides with an earlier directory becomes UnsafeZipError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "conflict.zip")
        dest = os.path.join(tmpdir, "out")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("pkg/__init__.py", b"#\n")
            zf.writestr("pkg", b"not-a-dir")
        try:
            extract_zip_safe(zip_path, dest)
            raise AssertionError("expected UnsafeZipError")
        except UnsafeZipError as exc:
            assert "directory" in str(exc).lower() or "destination" in str(exc).lower()
