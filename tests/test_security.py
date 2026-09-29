"""Adversarial tests for zip extraction, integrity, and path sanitization."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path

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


def test_safe_member_path_rejects_nul():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            safe_member_path(tmp, "a\x00b.txt")
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
                    {"algorithm": "sha256", "files": {}},
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


def _write_tar_gz(path, members):
    """Write a .tar.gz. members maps name -> (kind, payload_or_linkname)."""
    import io
    import tarfile

    with tarfile.open(path, "w:gz") as tf:
        for name, (kind, payload) in members.items():
            info = tarfile.TarInfo(name)
            if kind == "dir":
                info.type = tarfile.DIRTYPE
                tf.addfile(info)
            elif kind == "sym":
                info.type = tarfile.SYMTYPE
                info.linkname = payload
                tf.addfile(info)
            elif kind == "chr":
                info.type = tarfile.CHRTYPE
                tf.addfile(info)
            else:
                data = payload if isinstance(payload, bytes) else payload.encode()
                info.size = len(data)
                info.mode = 0o755 if name.endswith(".run") else 0o644
                tf.addfile(info, io.BytesIO(data))


def test_extract_runtime_tarball_rejects_traversal():
    from opip.kit import KitError, _extract_runtime_tarball

    with tempfile.TemporaryDirectory() as tmp:
        tar = os.path.join(tmp, "rt.tar.gz")
        _write_tar_gz(tar, {"../evil.txt": ("file", b"x")})
        dest = os.path.join(tmp, "dest")
        try:
            _extract_runtime_tarball(Path(tar), Path(dest))
            raise AssertionError("expected KitError")
        except KitError:
            pass
        assert not os.path.isfile(os.path.join(tmp, "evil.txt"))


def test_extract_runtime_tarball_rejects_python_prefix_escape():
    from pathlib import Path

    from opip.kit import KitError, _extract_runtime_tarball

    with tempfile.TemporaryDirectory() as tmp:
        tar = os.path.join(tmp, "rt.tar.gz")
        _write_tar_gz(tar, {"python/../../evil.txt": ("file", b"x")})
        try:
            _extract_runtime_tarball(Path(tar), Path(os.path.join(tmp, "dest")))
            raise AssertionError("expected KitError")
        except KitError:
            pass
        assert not os.path.isfile(os.path.join(tmp, "evil.txt"))


def test_extract_runtime_tarball_rejects_absolute():
    from pathlib import Path

    from opip.kit import KitError, _extract_runtime_tarball

    with tempfile.TemporaryDirectory() as tmp:
        tar = os.path.join(tmp, "rt.tar.gz")
        _write_tar_gz(tar, {"/abs.txt": ("file", b"x")})
        try:
            _extract_runtime_tarball(Path(tar), Path(os.path.join(tmp, "dest")))
            raise AssertionError("expected KitError")
        except KitError:
            pass


def test_extract_runtime_tarball_rejects_symlink_escape():
    from pathlib import Path

    from opip.kit import KitError, _extract_runtime_tarball

    with tempfile.TemporaryDirectory() as tmp:
        tar = os.path.join(tmp, "rt.tar.gz")
        _write_tar_gz(
            tar,
            {"python/bin/evil": ("sym", "../../../../etc/passwd")},
        )
        try:
            _extract_runtime_tarball(Path(tar), Path(os.path.join(tmp, "dest")))
            raise AssertionError("expected KitError")
        except KitError:
            pass


def test_extract_runtime_tarball_rejects_device():
    from pathlib import Path

    from opip.kit import KitError, _extract_runtime_tarball

    with tempfile.TemporaryDirectory() as tmp:
        tar = os.path.join(tmp, "rt.tar.gz")
        _write_tar_gz(tar, {"python/dev/null0": ("chr", b"")})
        try:
            _extract_runtime_tarball(Path(tar), Path(os.path.join(tmp, "dest")))
            raise AssertionError("expected KitError")
        except KitError:
            pass


def test_extract_runtime_tarball_roundtrip():
    from pathlib import Path

    from opip.kit import _extract_runtime_tarball

    with tempfile.TemporaryDirectory() as tmp:
        tar = os.path.join(tmp, "rt.tar.gz")
        _write_tar_gz(
            tar,
            {
                "python/bin/": ("dir", b""),
                "python/bin/tool.run": ("file", b"#!/bin/sh\n"),
                "python/bin/tool": ("sym", "tool.run"),
            },
        )
        dest = Path(tmp) / "dest"
        _extract_runtime_tarball(Path(tar), dest)
        tool = dest / "bin" / "tool.run"
        assert tool.is_file()
        if os.name != "nt":
            # Windows chmod does not track POSIX exec bits.
            assert tool.stat().st_mode & 0o111
        link = dest / "bin" / "tool"
        if link.is_symlink():
            assert os.readlink(link) == "tool.run"
        elif os.name == "nt":
            # Windows falls back to copying the payload (no symlink privilege).
            assert link.is_file()
            assert link.read_bytes() == b"#!/bin/sh\n"
        else:
            raise AssertionError("expected symlink or Windows copy fallback")


def test_copy_packages_from_zip_rejects_traversal():
    from opip.self_install import _copy_packages_from_zip

    with tempfile.TemporaryDirectory() as tmp:
        pyz = os.path.join(tmp, "app.pyz")
        _write_zip(
            pyz,
            {
                "opip/ok.py": b"x = 1\n",
                "opip/../../evil.py": b"x = 1\n",
            },
        )
        site_dir = os.path.join(tmp, "site")
        try:
            _copy_packages_from_zip(Path(pyz), Path(site_dir))
            raise AssertionError("expected traversal rejection")
        except Exception:
            pass
        assert not os.path.isfile(os.path.join(tmp, "evil.py"))


def test_reject_option_value():
    from opip.safe_zip import reject_option_value

    for bad in ("-x", "--upload-pack=evil", "-rf", "--", "a\x00b", ""):
        try:
            reject_option_value(bad, "arg")
            raise AssertionError(f"expected ValueError for {bad!r}")
        except ValueError:
            pass
    assert reject_option_value("rns://abc/repo") == "rns://abc/repo"
    assert reject_option_value("v1.2.3") == "v1.2.3"


def test_git_resolver_clone_rejects_option_url():
    from unittest import mock

    from pip_rns.resolver import GitResolver

    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch("pip_rns.resolver.subprocess.run") as run:
            try:
                GitResolver().clone("--upload-pack=touch /tmp/pwn", Path(tmp) / "d")
                raise AssertionError("expected ValueError")
            except ValueError:
                pass
            assert not run.called


def test_git_resolver_update_rejects_option_ref():
    from unittest import mock

    from pip_rns.resolver import GitResolver

    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch("pip_rns.resolver.subprocess.run") as run:
            try:
                GitResolver().update(
                    "rns://x", Path(tmp), ref="--upload-pack=touch /tmp/pwn"
                )
                raise AssertionError("expected ValueError")
            except ValueError:
                pass
            assert not run.called


def test_index_clone_rejects_option_url():
    from unittest import mock

    from pip_rns.indexes import IndexManager

    mgr = object.__new__(IndexManager)
    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch("pip_rns.indexes.subprocess.run") as run:
            try:
                mgr._clone("--upload-pack=touch /tmp/pwn", Path(tmp))
                raise AssertionError("expected ValueError")
            except ValueError:
                pass
            assert not run.called


def test_rns_fetch_clone_rejects_option_remote():
    from unittest import mock

    from opip.fetch import FetchError
    from opip.rns_fetch import _clone_repo

    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch("opip.rns_fetch._check_rns_available"):
            try:
                _clone_repo("--upload-pack=touch /tmp/pwn", tmp)
                raise AssertionError("expected FetchError")
            except FetchError:
                pass


def test_release_info_rejects_option_tag():
    from unittest import mock

    from pip_rns.releases import release_info

    with mock.patch("pip_rns.releases.subprocess.run") as run:
        try:
            release_info("rns://abc/repo", "--all")
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
        assert not run.called
