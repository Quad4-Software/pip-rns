"""Tests for opip update_bundle error handling and dest resolution."""

from __future__ import annotations

import os
import tempfile
from unittest import mock

from opip.install import InstallError, _venv_python
from opip.storage import Store
from opip.update import (
    UpdateError,
    _path_is_venv,
    _resolve_reinstall_dest,
    update_bundle,
)
from tests.test_opip import _make_test_bundle


def test_path_is_venv_detects_layout():
    with tempfile.TemporaryDirectory() as tmp:
        assert _path_is_venv(tmp) is False
        py = _venv_python(tmp)
        os.makedirs(os.path.dirname(py))
        open(py, "w").close()
        assert _path_is_venv(tmp) is True


def test_resolve_reinstall_prefers_cli_venv():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(data_dir=os.path.join(tmp, "state"))
        store.record_install("pkg", ["pkg"], target=os.path.join(tmp, "old"))
        target, user, venv = _resolve_reinstall_dest(
            store,
            "pkg",
            venv=os.path.join(tmp, "env"),
        )
        assert target is None
        assert user is False
        assert venv.endswith("env")


def test_resolve_reinstall_uses_recorded_venv():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(data_dir=os.path.join(tmp, "state"))
        venv = os.path.join(tmp, "venv")
        py = _venv_python(venv)
        os.makedirs(os.path.dirname(py))
        open(py, "w").close()
        store.record_install("pkg", ["pkg"], target=venv)
        target, user, got = _resolve_reinstall_dest(store, "pkg")
        assert target is None
        assert user is False
        assert got == venv


def test_resolve_reinstall_uses_recorded_target_dir():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(data_dir=os.path.join(tmp, "state"))
        dest = os.path.join(tmp, "vendor")
        os.makedirs(dest)
        store.record_install("pkg", ["pkg"], target=dest)
        target, user, venv = _resolve_reinstall_dest(store, "pkg")
        assert target == dest
        assert user is False
        assert venv is None


def test_update_missing_bundle_errors():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(data_dir=os.path.join(tmp, "state"))
        try:
            update_bundle("missing", store=store, reinstall=False)
            raise AssertionError("expected UpdateError")
        except UpdateError as exc:
            assert "not registered" in str(exc)


def test_update_missing_file_errors():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(data_dir=os.path.join(tmp, "state"))
        store.register_bundle(
            "pkg",
            os.path.join(tmp, "gone.opip"),
            {"name": "pkg", "wheels": [], "python_version": "3.12", "platform": "any"},
        )
        try:
            update_bundle("pkg", store=store, reinstall=False)
            raise AssertionError("expected UpdateError")
        except UpdateError as exc:
            assert "missing" in str(exc)


def test_update_no_requirements_errors():
    with tempfile.TemporaryDirectory() as tmp:
        work = os.path.join(tmp, "work")
        os.makedirs(work)
        bundle = os.path.join(tmp, "pkg.opip")
        _make_test_bundle(work, bundle)
        store = Store(data_dir=os.path.join(tmp, "state"))
        store.register_bundle(
            "test-bundle",
            bundle,
            {
                "name": "test-bundle",
                "wheels": [],
                "python_version": "3.12",
                "platform": "any",
            },
        )
        with mock.patch("opip.update.bundle_info", return_value={"requirements": []}):
            try:
                update_bundle("test-bundle", store=store, reinstall=False)
                raise AssertionError("expected UpdateError")
            except UpdateError as exc:
                assert "no requirements" in str(exc).lower()


def test_update_restores_backup_when_create_fails():
    with tempfile.TemporaryDirectory() as tmp:
        work = os.path.join(tmp, "work")
        os.makedirs(work)
        bundle = os.path.join(tmp, "pkg.opip")
        _make_test_bundle(work, bundle)
        store = Store(data_dir=os.path.join(tmp, "state"))
        store.register_bundle(
            "test-bundle",
            bundle,
            {
                "name": "test-bundle",
                "wheels": [{"filename": "pkg-1.0.0-py3-none-any.whl"}],
                "python_version": "3.12",
                "platform": "any",
                "requirements": ["pkg==1.0.0"],
            },
        )
        with open(bundle, "rb") as fh:
            before = fh.read()
        with mock.patch(
            "opip.update.create_bundle",
            side_effect=RuntimeError("network down"),
        ):
            try:
                update_bundle("test-bundle", store=store, reinstall=False)
                raise AssertionError("expected failure")
            except RuntimeError:
                pass
        with open(bundle, "rb") as fh:
            assert fh.read() == before
        assert not os.path.isfile(bundle + ".bak")


def test_update_reinstall_uses_replace_not_uninstall():
    with tempfile.TemporaryDirectory() as tmp:
        work = os.path.join(tmp, "work")
        os.makedirs(work)
        bundle = os.path.join(tmp, "pkg.opip")
        _make_test_bundle(work, bundle)
        store = Store(data_dir=os.path.join(tmp, "state"))
        store.register_bundle(
            "test-bundle",
            bundle,
            {
                "name": "test-bundle",
                "wheels": [{"filename": "pkg-1.0.0-py3-none-any.whl"}],
                "python_version": "3.12",
                "platform": "any",
                "requirements": ["pkg==1.0.0"],
            },
        )
        calls = {}

        def fake_create(output_path, requirements, **kwargs):
            with open(output_path, "wb") as fh:
                fh.write(b"new")

        def fake_verify(_path):
            return [], {"name": "test-bundle", "wheels": []}

        def fake_install(*_a, **kwargs):
            calls["install"] = kwargs

        with mock.patch("opip.update.create_bundle", side_effect=fake_create):
            with mock.patch("opip.update.verify_bundle", side_effect=fake_verify):
                with mock.patch("opip.update.has_signature", return_value=False):
                    with mock.patch(
                        "opip.update.install_bundle",
                        side_effect=fake_install,
                    ) as inst:
                        with mock.patch("opip.update.bundle_info") as info:
                            info.return_value = {
                                "name": "test-bundle",
                                "requirements": ["pkg==1.0.0"],
                                "python_version": "3.12",
                                "platform": "any",
                            }
                            update_bundle(
                                "test-bundle",
                                store=store,
                                reinstall=True,
                                no_interactive=True,
                            )
        assert inst.called
        assert calls["install"].get("replace") is True


def test_update_wraps_reinstall_failure():
    with tempfile.TemporaryDirectory() as tmp:
        work = os.path.join(tmp, "work")
        os.makedirs(work)
        bundle = os.path.join(tmp, "pkg.opip")
        _make_test_bundle(work, bundle)
        store = Store(data_dir=os.path.join(tmp, "state"))
        store.register_bundle(
            "test-bundle",
            bundle,
            {
                "name": "test-bundle",
                "wheels": [],
                "python_version": "3.12",
                "platform": "any",
                "requirements": ["pkg==1.0.0"],
            },
        )

        def fake_create(output_path, requirements, **kwargs):
            with open(output_path, "wb") as fh:
                fh.write(b"new")

        with mock.patch("opip.update.create_bundle", side_effect=fake_create):
            with mock.patch(
                "opip.update.verify_bundle",
                return_value=([], {"name": "test-bundle", "wheels": []}),
            ):
                with mock.patch("opip.update.has_signature", return_value=False):
                    with mock.patch(
                        "opip.update.install_bundle",
                        side_effect=InstallError("pep 668"),
                    ):
                        with mock.patch("opip.update.bundle_info") as info:
                            info.return_value = {
                                "name": "test-bundle",
                                "requirements": ["pkg==1.0.0"],
                                "python_version": "3.12",
                                "platform": "any",
                            }
                            try:
                                update_bundle(
                                    "test-bundle",
                                    store=store,
                                    reinstall=True,
                                    no_interactive=True,
                                )
                                raise AssertionError("expected UpdateError")
                            except UpdateError as exc:
                                assert "reinstall failed" in str(exc).lower()
