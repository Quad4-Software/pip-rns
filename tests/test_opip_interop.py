"""Tests for opip interop: trust, json, lock import, extract, delta, backends."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

from opip.lock_import import load_lockfile
from opip.lockfile import diff_locks, make_sbom
from opip.trust_cmd import resolve_signer


def test_cyclonedx_sbom_shape():
    manifest = {
        "name": "demo",
        "created": "2026-01-01T00:00:00+00:00",
        "python_version": "3.12",
        "platform": "py3-none-any",
    }
    wheels = [
        {
            "package": "demo",
            "version": "1.0",
            "filename": "demo-1.0-py3-none-any.whl",
            "sha256": "a" * 64,
            "source": "pypi",
        },
    ]
    sbom = make_sbom(
        manifest,
        wheels,
        publisher={"name": "Team", "identity": "ab" * 16},
    )
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.5"
    assert sbom["components"][0]["purl"] == "pkg:pypi/demo@1.0"
    assert sbom["components"][0]["hashes"][0]["alg"] == "SHA-256"


def test_diff_locks():
    old = [
        {"filename": "a-1.whl", "sha256": "aa"},
        {"filename": "b-1.whl", "sha256": "bb"},
    ]
    new = [
        {"filename": "b-1.whl", "sha256": "bb2"},
        {"filename": "c-1.whl", "sha256": "cc"},
    ]
    d = diff_locks(old, new)
    assert d["added"] == ["c-1.whl"]
    assert d["removed"] == ["a-1.whl"]
    assert d["changed"] == ["b-1.whl"]


def test_lock_import_pip_tools():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "requirements.lock"
        path.write_text(
            "requests==2.31.0 \\\n    --hash=sha256:"
            + ("ab" * 32)
            + "\nurllib3==2.0.0\n",
            encoding="utf-8",
        )
        pins = load_lockfile(str(path))
        assert pins[0]["name"] == "requests"
        assert pins[0]["version"] == "2.31.0"
        assert pins[0]["sha256"] == "ab" * 32
        assert pins[1]["name"] == "urllib3"


def test_lock_import_poetry():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "poetry.lock"
        path.write_text(
            "[[package]]\n"
            'name = "demo"\n'
            'version = "1.2.3"\n'
            'category = "main"\n'
            'files = [{file = "demo-1.2.3-py3-none-any.whl", hash = "sha256:'
            + ("cd" * 32)
            + '"}]\n',
            encoding="utf-8",
        )
        pins = load_lockfile(str(path))
        assert pins[0]["name"] == "demo"
        assert pins[0]["version"] == "1.2.3"
        assert pins[0]["sha256"] == "cd" * 32


def test_lock_import_uv():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "uv.lock"
        path.write_text(
            "version = 1\n"
            "[[package]]\n"
            'name = "demo"\n'
            'version = "9.9.9"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
            'wheels = [{ url = "https://example/demo.whl", hash = "sha256:'
            + ("ef" * 32)
            + '" }]\n',
            encoding="utf-8",
        )
        pins = load_lockfile(str(path))
        assert pins[0]["name"] == "demo"
        assert pins[0]["sha256"] == "ef" * 32


def test_resolve_signer_uses_trust_default():
    from pip_rns.trust import TrustStore

    with tempfile.TemporaryDirectory() as tmp:
        store = TrustStore(tmp)
        store.set_default("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        signer = resolve_signer("some-bundle.opip", config_dir=tmp)
        assert signer == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_resolve_signer_explicit_wins():
    from pip_rns.trust import TrustStore

    with tempfile.TemporaryDirectory() as tmp:
        store = TrustStore(tmp)
        store.set_default("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        signer = resolve_signer(
            "x.opip",
            explicit="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            config_dir=tmp,
        )
        assert signer == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def test_cli_verify_json():
    from opip.cli import main

    with tempfile.TemporaryDirectory() as tmp:
        code = main(["--json", "verify", os.path.join(tmp, "missing.opip")])
        assert code == 1


def test_install_via_uv_cmd():
    from opip import install as install_mod

    calls = []

    def fake_run(cmd, capture_output=True, text=True):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return R()

    with tempfile.TemporaryDirectory() as tmp:
        req = os.path.join(tmp, "req.txt")
        with open(req, "w", encoding="utf-8") as fh:
            fh.write("x\n")
        with mock.patch("opip.install._uv_available", return_value=True):
            with mock.patch("opip.install.subprocess.run", side_effect=fake_run):
                with mock.patch(
                    "opip.install.shutil.which",
                    side_effect=lambda name: "/usr/bin/uv" if name == "uv" else None,
                ):
                    import shutil as shutil_mod

                    with mock.patch.object(
                        shutil_mod,
                        "which",
                        side_effect=lambda name: (
                            "/usr/bin/uv" if name == "uv" else None
                        ),
                    ):
                        install_mod.install_via_uv(tmp, req, wheels=[])
    assert calls
    assert calls[0][0] == "uv"
    assert "--find-links" in calls[0]


def test_extract_and_simple_index():
    from opip.extract_cmd import extract_to_wheelhouse
    from opip.integrity import build_integrity, collect_files, dump_integrity, file_hash
    from opip.manifest import dump_manifest, make_manifest

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        work = tmp_path / "work"
        wheels = work / "wheels"
        wheels.mkdir(parents=True)
        whl = wheels / "demo-1.0-py3-none-any.whl"
        with zipfile.ZipFile(whl, "w") as zf:
            zf.writestr(
                "demo-1.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n",
            )
            zf.writestr(
                "demo-1.0.dist-info/WHEEL",
                "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            )
            zf.writestr("demo/__init__.py", "")
        manifest = make_manifest(
            "demo",
            ["demo==1.0"],
            [
                {
                    "filename": "demo-1.0-py3-none-any.whl",
                    "package": "demo",
                    "version": "1.0",
                    "sha256": "0" * 64,
                    "source": "local",
                },
            ],
            "3.12",
            "py3-none-any",
        )
        digest = file_hash(str(whl))
        manifest["wheels"][0]["sha256"] = digest
        (work / "manifest.json").write_text(dump_manifest(manifest), encoding="utf-8")
        (work / "requirements.txt").write_text("demo==1.0\n", encoding="utf-8")
        integrity = build_integrity(collect_files(str(work)), base_dir=str(work))
        (work / "integrity.json").write_text(
            dump_integrity(integrity), encoding="utf-8"
        )
        bundle = tmp_path / "demo.opip"
        with zipfile.ZipFile(bundle, "w") as zf:
            for root, _dirs, files in os.walk(work):
                for name in files:
                    full = os.path.join(root, name)
                    zf.write(full, os.path.relpath(full, work))

        out = tmp_path / "wheelhouse"
        _path, count = extract_to_wheelhouse(
            str(bundle),
            str(out),
            simple_index=True,
            verify=True,
        )
        assert count == 1
        assert (out / "demo-1.0-py3-none-any.whl").is_file()
        assert (out / "index.html").is_file()
        assert (out / "demo" / "index.html").is_file()
