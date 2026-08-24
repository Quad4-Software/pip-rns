"""Cost warning, export, and doctor trust/cache checks."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

from pip_rns.cost_warn import confirm_expensive_rns_clone
from pip_rns.doctor import run_doctor
from pip_rns.errors import UserCancelled
from pip_rns.export_cmd import export_release
from pip_rns.releases import ArtifactFetch


def test_cost_warn_skipped_noninteractive():
    with mock.patch("builtins.input", side_effect=AssertionError("prompted")):
        confirm_expensive_rns_clone(
            "rns://aa/g/repo",
            no_interactive=True,
        )


def test_cost_warn_assume_yes():
    with mock.patch("builtins.input", side_effect=AssertionError("prompted")):
        confirm_expensive_rns_clone("rns://aa/g/repo", assume_yes=True)


def test_cost_warn_abort():
    with mock.patch("pip_rns.cost_warn.is_noninteractive", return_value=False):
        with mock.patch("builtins.input", return_value="n"):
            try:
                confirm_expensive_rns_clone("rns://aa/g/repo")
                raise AssertionError("expected UserCancelled")
            except UserCancelled:
                pass


def test_export_writes_wheel_and_rsg():
    artifacts = [
        {"name": "pkg-1.0-py3-none-any.whl", "size": "1 KB"},
        {"name": "pkg-1.0-py3-none-any.whl.rsg", "size": "1 KB"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        whl = Path(tmp) / "src" / "pkg-1.0-py3-none-any.whl"
        rsg = Path(tmp) / "src" / "pkg-1.0-py3-none-any.whl.rsg"
        whl.parent.mkdir()
        whl.write_bytes(b"whl")
        rsg.write_bytes(b"rsg")
        out = Path(tmp) / "out"

        def fake_fetch(remote, tag, name, verify_identity=None):
            src = whl if name.endswith(".whl") and not name.endswith(".rsg") else rsg
            # export moves the file. copy to a temp path first
            import shutil

            dest = Path(tmp) / "fetch" / name
            dest.parent.mkdir(exist_ok=True)
            shutil.copy2(src, dest)
            return ArtifactFetch(path=str(dest), signer="aa" * 16, verified=True)

        with mock.patch(
            "pip_rns.export_cmd.release_info",
            return_value={"tag": "v1", "artifacts": artifacts},
        ), mock.patch(
            "pip_rns.export_cmd.fetch_release_artifact", side_effect=fake_fetch
        ):
            written = export_release(
                "rns://aabbccddeeff00112233445566778899/g/repo",
                str(out),
                ref="v1",
                insecure=True,
            )
        names = sorted(Path(p).name for p in written)
        assert names == [
            "pkg-1.0-py3-none-any.whl",
            "pkg-1.0-py3-none-any.whl.rsg",
        ]
        assert (out / "pkg-1.0-py3-none-any.whl").is_file()


def test_doctor_includes_trust_and_cache():
    with tempfile.TemporaryDirectory() as tmp:
        checks = run_doctor(online=False, config_dir=tmp)
    names = {c.name for c in checks}
    assert "trust" in names
    assert "source-cache" in names
