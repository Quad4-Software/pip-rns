"""Tests for installer.py - registry and factory functions."""

from __future__ import annotations

from pip_rns.installer import (
    PipInstaller,
    PipxInstaller,
    PoetryInstaller,
    UvInstaller,
    get_installer,
    register_installer,
)


def test_get_pip_installer():
    inst = get_installer("pip")
    assert isinstance(inst, PipInstaller)


def test_get_pipx_installer():
    inst = get_installer("pipx")
    assert isinstance(inst, PipxInstaller)


def test_get_uv_installer():
    inst = get_installer("uv")
    assert isinstance(inst, UvInstaller)


def test_get_poetry_installer():
    inst = get_installer("poetry")
    assert isinstance(inst, PoetryInstaller)


def test_get_unknown_installer_raises():
    try:
        get_installer("nonexistent")
        assert False, "should have raised"
    except ValueError as e:
        assert "nonexistent" in str(e)


def test_custom_registration():
    class FakeInstaller(PipInstaller):
        name = "fake"

    register_installer("fake", FakeInstaller)
    inst = get_installer("fake")
    assert isinstance(inst, FakeInstaller)


def test_installer_name_matches():
    assert get_installer("pip").name == "pip"
    assert get_installer("pipx").name == "pipx"
    assert get_installer("uv").name == "uv"
    assert get_installer("poetry").name == "poetry"


def test_installer_inject_not_implemented():
    from pathlib import Path

    inst = get_installer("pip")
    try:
        inst.inject("venv", Path("/tmp/pkg"))
        assert False, "should have raised"
    except NotImplementedError:
        pass
