"""Adversarial tests for zip extraction, integrity, and path sanitization."""

from __future__ import annotations

import os
import tempfile
import zipfile

from opip.bundle import BundleError, extract_bundle, verify_bundle
from opip.integrity import (
    build_integrity,
    collect_files,
    dump_integrity,
    load_integrity,
    verify_integrity,
)
from opip.safe_zip import (
    UnsafeZipError,
    contain_path,
    extract_zip_safe,
    safe_artifact_name,
    safe_member_path,
)
from opip.signing import signature_path
from opip.wheel_cache import cache_path


def _write_zip(path: str, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def test_safe_member_path_rejects_traversal():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            safe_member_path(tmp, "../outside.txt")
            raise AssertionError("expected UnsafeZipError")
        except UnsafeZipError:
            pass
        try:
            safe_member_path(tmp, "foo/../../outside.txt")
            raise AssertionError("expected UnsafeZipError")
        except UnsafeZipError:
            pass


def test_safe_member_path_rejects_absolute():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            safe_member_path(tmp, "/etc/passwd")
            raise AssertionError("expected UnsafeZipError")
        except UnsafeZipError:
            pass


def test_safe_member_path_allows_nested():
    with tempfile.TemporaryDirectory() as tmp:
        dest = safe_member_path(tmp, "wheels/pkg.whl")
        assert dest.startswith(os.path.abspath(tmp))
        assert dest.endswith(os.path.join("wheels", "pkg.whl"))


def test_extract_zip_safe_rejects_zip_slip():
    with tempfile.TemporaryDirectory() as tmp:
        evil = os.path.join(tmp, "evil.zip")
        outside = os.path.join(tmp, "outside.txt")
        _write_zip(evil, {"../outside.txt": b"pwned"})
        dest = os.path.join(tmp, "out")
        os.makedirs(dest)
        try:
            extract_zip_safe(evil, dest)
            raise AssertionError("expected UnsafeZipError")
        except UnsafeZipError:
            pass
        assert not os.path.isfile(outside)


def test_extract_zip_safe_allows_normal():
    with tempfile.TemporaryDirectory() as tmp:
        zpath = os.path.join(tmp, "ok.zip")
        _write_zip(zpath, {"a/b.txt": b"hello"})
        dest = os.path.join(tmp, "out")
        extract_zip_safe(zpath, dest)
        path = os.path.join(dest, "a", "b.txt")
        assert os.path.isfile(path)
        with open(path, "rb") as fh:
            assert fh.read() == b"hello"


def test_extract_zip_safe_rejects_oversized_member():
    with tempfile.TemporaryDirectory() as tmp:
        zpath = os.path.join(tmp, "bomb.zip")
        with zipfile.ZipFile(zpath, "w") as zf:
            info = zipfile.ZipInfo("big.bin")
            data = b"x" * 1000
            zf.writestr(info, data)
        dest = os.path.join(tmp, "out")
        try:
            extract_zip_safe(zpath, dest, max_member_bytes=100, max_total_bytes=10**9)
            raise AssertionError("expected UnsafeZipError")
        except UnsafeZipError as exc:
            assert "too large" in str(exc).lower() or "size" in str(exc).lower()


def test_safe_artifact_name_rejects_separators():
    try:
        safe_artifact_name("../evil.whl")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    try:
        safe_artifact_name("foo/bar.whl")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    assert (
        safe_artifact_name("pkg-1.0.0-py3-none-any.whl") == "pkg-1.0.0-py3-none-any.whl"
    )


def test_cache_path_rejects_traversal():
    try:
        cache_path("../evil.whl")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_contain_path_rejects_escape():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            contain_path(tmp, "../../etc")
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
        ok = contain_path(tmp, "dist/bundle.opip")
        assert ok.startswith(os.path.abspath(tmp))


def test_verify_integrity_rejects_path_escape():
    with tempfile.TemporaryDirectory() as tmp:
        integrity = {
            "algorithm": "sha256",
            "files": {"../escape.txt": "abc"},
        }
        errors = verify_integrity(tmp, integrity)
        assert any("traversal" in e.lower() or "escape" in e.lower() for e in errors)


def test_verify_integrity_detects_unlisted_file():
    with tempfile.TemporaryDirectory() as tmp:
        listed = os.path.join(tmp, "ok.txt")
        with open(listed, "w", encoding="utf-8") as fh:
            fh.write("ok")
        extra = os.path.join(tmp, "payload.bin")
        with open(extra, "w", encoding="utf-8") as fh:
            fh.write("evil")
        integrity = build_integrity([listed], base_dir=tmp)
        all_files = collect_files(tmp)
        errors = verify_integrity(tmp, integrity, all_files=all_files)
        assert any("Unlisted file" in e for e in errors)


def test_load_integrity_rejects_bad_algorithm():
    try:
        load_integrity({"algorithm": "md5", "files": {}})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_extract_bundle_rejects_zip_slip():
    with tempfile.TemporaryDirectory() as tmp:
        bundle = os.path.join(tmp, "bad.opip")
        _write_zip(
            bundle,
            {
                "../escape.txt": b"x",
                "manifest.json": b'{"name":"x","wheels":[]}',
                "integrity.json": dump_integrity(
                    {"algorithm": "sha256", "files": {}}
                ).encode("utf-8"),
            },
        )
        try:
            extract_bundle(bundle, dest_dir=os.path.join(tmp, "out"))
            raise AssertionError("expected BundleError")
        except BundleError:
            pass


def test_signed_without_signer_auto_verifies():
    """A present .rsg is verified automatically without --signer."""
    from unittest import mock

    from tests.test_opip import _make_test_bundle

    with tempfile.TemporaryDirectory() as tmpdir:
        bundle_path = os.path.join(tmpdir, "test.opip")
        work = os.path.join(tmpdir, "work")
        os.makedirs(work)
        _make_test_bundle(work, bundle_path)
        sidecar = signature_path(bundle_path)
        with open(sidecar, "w", encoding="utf-8") as fh:
            fh.write("fake-sig")
        fake = mock.Mock(
            returncode=0,
            stdout="Signature is valid, the file was signed by <aabbccddeeff00112233445566778899>\n",
            stderr="",
        )
        with mock.patch("opip.signing.shutil.which", return_value="/usr/bin/rnid"):
            with mock.patch("opip.signing.subprocess.run", return_value=fake) as run:
                errors, _manifest = verify_bundle(bundle_path)
        assert errors == []
        cmd = run.call_args[0][0]
        assert cmd[:2] == ["rnid", "-V"]
        assert "-i" not in cmd


def test_signed_invalid_without_signer_fails():
    from unittest import mock

    from tests.test_opip import _make_test_bundle

    with tempfile.TemporaryDirectory() as tmpdir:
        bundle_path = os.path.join(tmpdir, "test.opip")
        work = os.path.join(tmpdir, "work")
        os.makedirs(work)
        _make_test_bundle(work, bundle_path)
        sidecar = signature_path(bundle_path)
        with open(sidecar, "w", encoding="utf-8") as fh:
            fh.write("fake-sig")
        fake = mock.Mock(returncode=1, stdout="", stderr="Invalid signature")
        with mock.patch("opip.signing.shutil.which", return_value="/usr/bin/rnid"):
            with mock.patch("opip.signing.subprocess.run", return_value=fake):
                errors, _manifest = verify_bundle(bundle_path)
        assert any("Signature check failed" in e for e in errors)


def test_require_signature_on_unsigned():
    from tests.test_opip import _make_test_bundle

    with tempfile.TemporaryDirectory() as tmpdir:
        bundle_path = os.path.join(tmpdir, "test.opip")
        work = os.path.join(tmpdir, "work")
        os.makedirs(work)
        _make_test_bundle(work, bundle_path)
        errors, _manifest = verify_bundle(bundle_path, require_signature=True)
        assert any(
            "no .rsg" in e or "not signed" in e.lower() or "require-signature" in e
            for e in errors
        )


def test_verify_bundle_signature_mocked_valid():
    from unittest import mock

    from opip.signing import verify_bundle_signature

    with tempfile.TemporaryDirectory() as tmp:
        bundle = os.path.join(tmp, "b.opip")
        with open(bundle, "wb") as fh:
            fh.write(b"data")
        with open(signature_path(bundle), "w", encoding="utf-8") as fh:
            fh.write("sig")
        fake = mock.Mock(
            returncode=0,
            stdout="Signature is valid\n",
            stderr="",
        )
        with mock.patch("opip.signing.shutil.which", return_value="/usr/bin/rnid"):
            with mock.patch("opip.signing.subprocess.run", return_value=fake):
                errors = verify_bundle_signature(bundle, signer="/id")
        assert errors == []


def test_verify_bundle_signature_auto_without_signer():
    from unittest import mock

    from opip.signing import verify_bundle_signature_info

    with tempfile.TemporaryDirectory() as tmp:
        bundle = os.path.join(tmp, "b.opip")
        with open(bundle, "wb") as fh:
            fh.write(b"data")
        with open(signature_path(bundle), "w", encoding="utf-8") as fh:
            fh.write("sig")
        fake = mock.Mock(
            returncode=0,
            stdout=(
                "Signature is valid, the file b.opip was signed by "
                "<e46112d44649266d71fe2193e00a4710>\n"
            ),
            stderr="",
        )
        with mock.patch("opip.signing.shutil.which", return_value="/usr/bin/rnid"):
            with mock.patch("opip.signing.subprocess.run", return_value=fake) as run:
                errors, identity = verify_bundle_signature_info(bundle)
        assert errors == []
        assert identity == "e46112d44649266d71fe2193e00a4710"
        assert "-i" not in run.call_args[0][0]


def test_verify_bundle_signature_mocked_invalid():
    from unittest import mock

    from opip.signing import verify_bundle_signature

    with tempfile.TemporaryDirectory() as tmp:
        bundle = os.path.join(tmp, "b.opip")
        with open(bundle, "wb") as fh:
            fh.write(b"data")
        with open(signature_path(bundle), "w", encoding="utf-8") as fh:
            fh.write("sig")
        fake = mock.Mock(returncode=1, stdout="", stderr="bad")
        with mock.patch("opip.signing.shutil.which", return_value="/usr/bin/rnid"):
            with mock.patch("opip.signing.subprocess.run", return_value=fake):
                errors = verify_bundle_signature(bundle, signer="/id")
        assert errors
        assert "failed" in errors[0].lower()


def test_install_wheel_manual_rejects_zip_slip():
    from opip.install import InstallError, install_wheel_manual

    with tempfile.TemporaryDirectory() as tmp:
        whl = os.path.join(tmp, "evil.whl")
        _write_zip(whl, {"../escape.txt": b"pwned"})
        dest = os.path.join(tmp, "site")
        os.makedirs(dest)
        try:
            install_wheel_manual(whl, dest)
            raise AssertionError("expected InstallError")
        except InstallError:
            pass
        assert not os.path.isfile(os.path.join(tmp, "escape.txt"))
