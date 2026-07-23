"""Tests for remembered install destinations."""

from __future__ import annotations

import os
import tempfile
from unittest import mock

from opip.storage import Store


def test_preferred_target_set_get_forget():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(data_dir=tmp)
        assert store.get_preferred_target("pkg") is None
        store.set_preferred_target("pkg", os.path.join(tmp, "site"))
        got = store.get_preferred_target("pkg")
        assert got is not None
        assert got.endswith("site")
        assert store.forget_preferred_target("pkg") is True
        assert store.get_preferred_target("pkg") is None
        assert store.forget_preferred_target("pkg") is False


def test_list_preferred_targets_sorted():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(data_dir=tmp)
        store.set_preferred_target("b", "/tmp/b")
        store.set_preferred_target("a", "/tmp/a")
        names = [n for n, _p in store.list_preferred_targets()]
        assert names == ["a", "b"]


def test_install_uses_remembered_target():
    from tests.test_opip import _make_test_bundle
    from opip.install import install_bundle

    with tempfile.TemporaryDirectory() as tmp:
        store = Store(data_dir=os.path.join(tmp, "state"))
        target = os.path.join(tmp, "target")
        os.makedirs(target)
        store.set_preferred_target("test-bundle", target)

        work = os.path.join(tmp, "work")
        os.makedirs(work)
        bundle = os.path.join(tmp, "test.opip")
        _make_test_bundle(work, bundle)

        with mock.patch("opip.install._find_pip", return_value=False):
            with mock.patch("opip.install.install_wheel_manual") as manual:
                packages = install_bundle(
                    bundle,
                    store=store,
                    verify=True,
                    no_interactive=True,
                )
        assert packages
        assert manual.called
        dest_arg = manual.call_args[0][1]
        assert os.path.abspath(dest_arg) == os.path.abspath(target)


def test_remember_target_flag_saves_without_prompt():
    from tests.test_opip import _make_test_bundle
    from opip.install import install_bundle

    with tempfile.TemporaryDirectory() as tmp:
        store = Store(data_dir=os.path.join(tmp, "state"))
        target = os.path.join(tmp, "target")
        os.makedirs(target)
        work = os.path.join(tmp, "work")
        os.makedirs(work)
        bundle = os.path.join(tmp, "test.opip")
        _make_test_bundle(work, bundle)

        with mock.patch("opip.install._find_pip", return_value=False):
            with mock.patch("opip.install.install_wheel_manual"):
                install_bundle(
                    bundle,
                    target=target,
                    store=store,
                    verify=True,
                    target_explicit=True,
                    remember_target=True,
                    no_interactive=True,
                )
        assert os.path.abspath(
            store.get_preferred_target("test-bundle")
        ) == os.path.abspath(target)


def test_no_prompt_when_noninteractive():
    from tests.test_opip import _make_test_bundle
    from opip.install import install_bundle

    with tempfile.TemporaryDirectory() as tmp:
        store = Store(data_dir=os.path.join(tmp, "state"))
        target = os.path.join(tmp, "target")
        os.makedirs(target)
        work = os.path.join(tmp, "work")
        os.makedirs(work)
        bundle = os.path.join(tmp, "test.opip")
        _make_test_bundle(work, bundle)

        with mock.patch("opip.install._find_pip", return_value=False):
            with mock.patch("opip.install.install_wheel_manual"):
                with mock.patch(
                    "builtins.input", side_effect=AssertionError("prompted")
                ):
                    install_bundle(
                        bundle,
                        target=target,
                        store=store,
                        verify=True,
                        target_explicit=True,
                        no_interactive=True,
                    )
        assert store.get_preferred_target("test-bundle") is None
