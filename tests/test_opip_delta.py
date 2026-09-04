"""Tests for opip delta, extract, offline create, reuse, and CLI."""

from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from opip.bundle import create_bundle, verify_bundle, write_bundle_zip
from opip.delta import DeltaError, apply_delta, create_delta
from opip.extract_cmd import ExtractError, extract_to_wheelhouse
from opip.integrity import (
    build_integrity,
    collect_files,
    dump_integrity,
    file_hash,
)
from opip.lockfile import dump_json, make_lock, make_sbom
from opip.manifest import dump_manifest, make_manifest
from opip.provenance import build_wheel_record
from opip.resolver import detect_python_version
from tests.test_opip import _make_minimal_wheel


def _pack_bundle(work_dir, bundle_path, name, wheel_paths, requirements=None):
    """Build a verifiable .opip from real minimal wheels on disk."""
    wheels_dir = os.path.join(work_dir, "wheels")
    os.makedirs(wheels_dir, exist_ok=True)
    entries = []
    for src in wheel_paths:
        filename = os.path.basename(src)
        dest = os.path.join(wheels_dir, filename)
        if os.path.abspath(src) != os.path.abspath(dest):
            with open(src, "rb") as rf, open(dest, "wb") as wf:
                wf.write(rf.read())
        entries.append(build_wheel_record(dest, source="local"))
    requirements = requirements or [
        "{}=={}".format(e["package"], e["version"]) for e in entries
    ]
    manifest = make_manifest(
        name=name,
        requirements=requirements,
        wheels=entries,
        python_version=detect_python_version(),
        platform_tag="any",
        extras={
            "pinned_requirements": [
                "{}=={}".format(e["package"], e["version"]) for e in entries
            ],
            "platforms": ["any"],
        },
    )
    with open(os.path.join(work_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        fh.write(dump_manifest(manifest))
    with open(os.path.join(work_dir, "requirements.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(requirements) + "\n")
    with open(os.path.join(work_dir, "lock.json"), "w", encoding="utf-8") as fh:
        fh.write(dump_json(make_lock(manifest, entries)))
    with open(os.path.join(work_dir, "sbom.json"), "w", encoding="utf-8") as fh:
        fh.write(dump_json(make_sbom(manifest, entries)))
    integrity = build_integrity(collect_files(work_dir), base_dir=work_dir)
    with open(os.path.join(work_dir, "integrity.json"), "w", encoding="utf-8") as fh:
        fh.write(dump_integrity(integrity))
    write_bundle_zip(bundle_path, work_dir)
    return manifest


def test_delta_only_packs_changed_wheels():
    """Delta must stay scarce: unchanged wheels stay out of the pack."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        whl_a = tmp_path / "a-1.0.0-py3-none-any.whl"
        whl_b = tmp_path / "b-2.0.0-py3-none-any.whl"
        _make_minimal_wheel(str(whl_a), name="aaa", version="1.0.0")
        _make_minimal_wheel(str(whl_b), name="bbb", version="2.0.0")

        old_work = tmp_path / "old-work"
        old_work.mkdir()
        old_bundle = tmp_path / "old.opip"
        _pack_bundle(str(old_work), str(old_bundle), "pkg", [str(whl_a)])

        new_work = tmp_path / "new-work"
        new_work.mkdir()
        stage = tmp_path / "stage"
        stage.mkdir()
        for src in (whl_a, whl_b):
            dest = stage / src.name
            dest.write_bytes(src.read_bytes())
        new_bundle = tmp_path / "new.opip"
        _pack_bundle(
            str(new_work),
            str(new_bundle),
            "pkg",
            [str(stage / whl_a.name), str(stage / whl_b.name)],
        )

        delta_path = tmp_path / "patch.opipd"
        path, meta = create_delta(str(old_bundle), str(new_bundle), str(delta_path))
        assert path.endswith(".opipd")
        assert meta["added"] == ["b-2.0.0-py3-none-any.whl"]
        assert meta["changed"] == []
        assert meta["removed"] == []
        assert "a-1.0.0-py3-none-any.whl" in meta["unchanged"]
        assert meta["base_sha256"] == file_hash(str(old_bundle))

        with zipfile.ZipFile(delta_path) as zf:
            names = zf.namelist()
            assert "delta.json" in names
            assert "integrity.json" in names
            assert "wheels/b-2.0.0-py3-none-any.whl" in names
            assert "wheels/a-1.0.0-py3-none-any.whl" not in names


def test_delta_apply_roundtrip_verifies():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        whl_a = tmp_path / "a-1.0.0-py3-none-any.whl"
        whl_b = tmp_path / "b-2.0.0-py3-none-any.whl"
        whl_c = tmp_path / "c-3.0.0-py3-none-any.whl"
        _make_minimal_wheel(str(whl_a), name="aaa", version="1.0.0")
        _make_minimal_wheel(str(whl_b), name="bbb", version="2.0.0")
        _make_minimal_wheel(str(whl_c), name="ccc", version="3.0.0")

        old_work = tmp_path / "old-work"
        old_work.mkdir()
        stage_old = tmp_path / "stage-old"
        stage_old.mkdir()
        for src in (whl_a, whl_b):
            (stage_old / src.name).write_bytes(src.read_bytes())
        old_bundle = tmp_path / "old.opip"
        _pack_bundle(
            str(old_work),
            str(old_bundle),
            "pkg",
            [str(stage_old / whl_a.name), str(stage_old / whl_b.name)],
        )

        whl_a2 = tmp_path / "a-1.0.0-py3-none-any-v2.whl"
        _make_minimal_wheel(str(whl_a2), name="aaa", version="1.0.0")
        stage_new = tmp_path / "stage-new"
        stage_new.mkdir()
        a_new = stage_new / "a-1.0.0-py3-none-any.whl"
        data = whl_a2.read_bytes()
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data), "r") as src_zf:
            with zipfile.ZipFile(buf, "w") as dst_zf:
                for item in src_zf.infolist():
                    dst_zf.writestr(item, src_zf.read(item.filename))
                dst_zf.writestr("aaa/extra.txt", "changed")
        a_new.write_bytes(buf.getvalue())
        (stage_new / whl_c.name).write_bytes(whl_c.read_bytes())

        new_work = tmp_path / "new-work"
        new_work.mkdir()
        new_bundle = tmp_path / "new.opip"
        _pack_bundle(
            str(new_work),
            str(new_bundle),
            "pkg",
            [str(a_new), str(stage_new / whl_c.name)],
        )

        delta_path = tmp_path / "patch.opipd"
        _path, meta = create_delta(str(old_bundle), str(new_bundle), str(delta_path))
        assert "a-1.0.0-py3-none-any.whl" in meta["changed"]
        assert "c-3.0.0-py3-none-any.whl" in meta["added"]
        assert "b-2.0.0-py3-none-any.whl" in meta["removed"]

        applied = tmp_path / "applied.opip"
        apply_delta(str(old_bundle), str(delta_path), str(applied))
        errors, manifest = verify_bundle(str(applied))
        assert errors == []
        names = {w["filename"] for w in manifest["wheels"]}
        assert names == {"a-1.0.0-py3-none-any.whl", "c-3.0.0-py3-none-any.whl"}
        assert "b-2.0.0-py3-none-any.whl" not in names

        new_a = next(w for w in manifest["wheels"] if w["filename"].startswith("a-"))
        assert new_a["sha256"] == file_hash(str(a_new))


def test_apply_rejects_wrong_base():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        whl = tmp_path / "x-1.0.0-py3-none-any.whl"
        _make_minimal_wheel(str(whl), name="xxx", version="1.0.0")
        old_work = tmp_path / "ow"
        old_work.mkdir()
        old_b = tmp_path / "old.opip"
        _pack_bundle(str(old_work), str(old_b), "pkg", [str(whl)])

        whl2 = tmp_path / "y-1.0.0-py3-none-any.whl"
        _make_minimal_wheel(str(whl2), name="yyy", version="1.0.0")
        new_work = tmp_path / "nw"
        new_work.mkdir()
        stage = tmp_path / "st"
        stage.mkdir()
        (stage / whl.name).write_bytes(whl.read_bytes())
        (stage / whl2.name).write_bytes(whl2.read_bytes())
        new_b = tmp_path / "new.opip"
        _pack_bundle(
            str(new_work),
            str(new_b),
            "pkg",
            [str(stage / whl.name), str(stage / whl2.name)],
        )

        delta = tmp_path / "d.opipd"
        create_delta(str(old_b), str(new_b), str(delta))
        try:
            apply_delta(str(new_b), str(delta), str(tmp_path / "out.opip"))
            raise AssertionError("expected DeltaError")
        except DeltaError as exc:
            assert "hash mismatch" in str(exc).lower()


def test_extract_verifies_and_writes_simple_index():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        whl = tmp_path / "demo-1.0.0-py3-none-any.whl"
        _make_minimal_wheel(str(whl), name="demo", version="1.0.0")
        work = tmp_path / "work"
        work.mkdir()
        bundle = tmp_path / "demo.opip"
        _pack_bundle(str(work), str(bundle), "demo", [str(whl)])

        out = tmp_path / "wheelhouse"
        path, count = extract_to_wheelhouse(
            str(bundle),
            str(out),
            simple_index=True,
            verify=True,
        )
        assert count == 1
        assert (out / "demo-1.0.0-py3-none-any.whl").is_file()
        assert (out / "index.html").is_file()
        assert (out / "demo" / "index.html").is_file()
        html = (out / "demo" / "index.html").read_text(encoding="utf-8")
        assert "demo-1.0.0-py3-none-any.whl" in html


def test_extract_fails_on_tampered_bundle():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        whl = tmp_path / "demo-1.0.0-py3-none-any.whl"
        _make_minimal_wheel(str(whl), name="demo", version="1.0.0")
        work = tmp_path / "work"
        work.mkdir()
        bundle = tmp_path / "demo.opip"
        _pack_bundle(str(work), str(bundle), "demo", [str(whl)])

        bad = tmp_path / "bad.opip"
        with zipfile.ZipFile(bundle, "r") as src, zipfile.ZipFile(bad, "w") as dst:
            for info in src.infolist():
                data = src.read(info.filename)
                if info.filename == "requirements.txt":
                    data = b"tampered\n"
                dst.writestr(info, data)

        try:
            extract_to_wheelhouse(str(bad), str(tmp_path / "out"), verify=True)
            raise AssertionError("expected ExtractError")
        except ExtractError as exc:
            assert "verification failed" in str(exc).lower()


def test_create_offline_find_links():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        wheels = tmp_path / "wheels"
        wheels.mkdir()
        whl = wheels / "solo-1.0.0-py3-none-any.whl"
        _make_minimal_wheel(str(whl), name="solo", version="1.0.0")
        out = tmp_path / "solo.opip"
        create_bundle(
            str(out),
            ["solo==1.0.0"],
            name="solo",
            include_deps=False,
            find_links=str(wheels),
            offline=True,
            use_cache=False,
        )
        errors, manifest = verify_bundle(str(out))
        assert errors == []
        assert manifest["name"] == "solo"
        with zipfile.ZipFile(out) as zf:
            sbom = json.loads(zf.read("sbom.json").decode("utf-8"))
        assert sbom["bomFormat"] == "CycloneDX"
        assert sbom["specVersion"] == "1.5"


def test_create_offline_missing_wheel_fails():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        wheels = tmp_path / "wheels"
        wheels.mkdir()
        out = tmp_path / "missing.opip"
        try:
            create_bundle(
                str(out),
                ["nosuchpkg==9.9.9"],
                name="missing",
                include_deps=False,
                find_links=str(wheels),
                offline=True,
                use_cache=False,
            )
            raise AssertionError("expected create failure")
        except Exception:
            pass


def test_create_reuses_wheels_from_prior_dir():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        wheels = tmp_path / "wheels"
        wheels.mkdir()
        whl = wheels / "reuse-1.0.0-py3-none-any.whl"
        _make_minimal_wheel(str(whl), name="reuse", version="1.0.0")

        first = tmp_path / "first.opip"
        create_bundle(
            str(first),
            ["reuse==1.0.0"],
            name="reuse",
            include_deps=False,
            find_links=str(wheels),
            offline=True,
            use_cache=False,
        )

        reuse_dir = tmp_path / "reuse-src"
        reuse_dir.mkdir()
        (reuse_dir / whl.name).write_bytes(whl.read_bytes())
        second = tmp_path / "second.opip"

        with mock.patch("opip.bundle.download_wheels_parallel") as dl:
            create_bundle(
                str(second),
                ["reuse==1.0.0"],
                name="reuse",
                include_deps=False,
                find_links=str(wheels),
                offline=True,
                use_cache=False,
                reuse_wheels_dir=str(reuse_dir),
            )
            dl.assert_not_called()

        errors, _manifest = verify_bundle(str(second))
        assert errors == []


def test_cli_delta_apply_json_and_quiet():
    from opip.cli import main

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        whl_a = tmp_path / "a-1.0.0-py3-none-any.whl"
        whl_b = tmp_path / "b-2.0.0-py3-none-any.whl"
        _make_minimal_wheel(str(whl_a), name="aaa", version="1.0.0")
        _make_minimal_wheel(str(whl_b), name="bbb", version="2.0.0")

        old_work = tmp_path / "ow"
        old_work.mkdir()
        old_b = tmp_path / "old.opip"
        _pack_bundle(str(old_work), str(old_b), "pkg", [str(whl_a)])

        stage = tmp_path / "st"
        stage.mkdir()
        (stage / whl_a.name).write_bytes(whl_a.read_bytes())
        (stage / whl_b.name).write_bytes(whl_b.read_bytes())
        new_work = tmp_path / "nw"
        new_work.mkdir()
        new_b = tmp_path / "new.opip"
        _pack_bundle(
            str(new_work),
            str(new_b),
            "pkg",
            [str(stage / whl_a.name), str(stage / whl_b.name)],
        )

        delta = tmp_path / "p.opipd"
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["--json", "delta", str(old_b), str(new_b), "-o", str(delta)])
        assert code == 0
        assert delta.is_file()
        payload = json.loads(buf.getvalue())
        assert payload["added"] == ["b-2.0.0-py3-none-any.whl"]
        assert payload["unchanged_count"] == 1

        applied = tmp_path / "applied.opip"
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["-q", "apply", str(old_b), str(delta), "-o", str(applied)])
        assert code == 0
        assert buf.getvalue().strip() == ""
        errors, _m = verify_bundle(str(applied))
        assert errors == []

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["--json", "verify", str(applied)])
        assert code == 0
        verify_payload = json.loads(buf.getvalue())
        assert verify_payload["ok"] is True
        assert verify_payload["manifest_summary"]["wheel_count"] == 2

        assert delta.stat().st_size < new_b.stat().st_size


def test_cli_info_list_json():
    from opip.cli import main
    from opip.storage import Store

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        whl = tmp_path / "z-1.0.0-py3-none-any.whl"
        _make_minimal_wheel(str(whl), name="zzz", version="1.0.0")
        work = tmp_path / "w"
        work.mkdir()
        bundle = tmp_path / "z.opip"
        _pack_bundle(str(work), str(bundle), "zzz", [str(whl)])

        store = Store(data_dir=str(tmp_path / "state"))
        store.register_bundle(
            "zzz",
            str(bundle),
            {"name": "zzz", "wheels": [], "python_version": "3"},
        )

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["--data-dir", str(tmp_path / "state"), "--json", "list"])
        assert code == 0
        rows = json.loads(buf.getvalue())
        assert isinstance(rows, list)
        assert any(r.get("name") == "zzz" for r in rows)

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["--json", "info", str(bundle)])
        assert code == 0
        info = json.loads(buf.getvalue())
        assert info["name"] == "zzz"
        assert info["wheel_count"] == 1


def test_trust_cli_and_verify_uses_default():
    from opip.cli import main
    from pip_rns.trust import TrustStore

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        identity = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(
                [
                    "--config",
                    str(tmp_path),
                    "trust",
                    "add",
                    "default",
                    identity,
                ],
            )
        assert code == 0
        store = TrustStore(str(tmp_path))
        assert store.get_default() == identity

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["--config", str(tmp_path), "--json", "trust", "ls"])
        assert code == 0
        rows = json.loads(buf.getvalue())
        assert rows[0]["identity"] == identity
