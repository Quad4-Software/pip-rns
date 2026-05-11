"""Pluggable package installer backends (pip, pipx, uv, poetry)."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

_REGISTERED_INSTALLERS: dict[str, type[BaseInstaller]] = {}

_ENV_PIP = shlex.split(os.environ.get("PIP_RNS_PIP", "pip"))
_ENV_PIPX = shlex.split(os.environ.get("PIP_RNS_PIPX", "pipx"))
_ENV_UV = shlex.split(os.environ.get("PIP_RNS_UV", "uv"))
_ENV_POETRY = shlex.split(os.environ.get("PIP_RNS_POETRY", "poetry"))


def register_installer(name: str, cls: type[BaseInstaller]) -> None:
    """Register an installer backend class by name."""
    _REGISTERED_INSTALLERS[name] = cls


def get_installer(name: str = "pip", venv: str | None = None) -> BaseInstaller:
    """Return an installer instance for the given backend name."""
    cls = _REGISTERED_INSTALLERS.get(name)
    if cls is None:
        msg = (
            f"Unknown installer: {name!r}. "
            f"Available: {', '.join(_REGISTERED_INSTALLERS)}"
        )
        raise ValueError(msg)
    return cls(venv=venv)


def _venv_pip_cmd(venv: str) -> list[str]:
    base = Path(venv)
    python = (
        base / "Scripts" / "python.exe" if os.name == "nt" else base / "bin" / "python"
    )
    return [str(python), "-m", "pip"]


class BaseInstaller:
    """Abstract installer backend. Subclasses wrap pip, pipx, uv, etc."""

    name = ""

    def __init__(self, venv: str | None = None) -> None:
        self.venv = venv

    def install(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        raise NotImplementedError

    def update(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        raise NotImplementedError

    def inject(
        self,
        venv_name: str,
        package_path: Path,
        extra_args: list[str] | None = None,
    ) -> None:
        raise NotImplementedError

    def list_packages(self) -> None:
        raise NotImplementedError

    def uninstall(self, package: str) -> None:
        raise NotImplementedError

    def _cmd(self) -> list[str]:
        raise NotImplementedError


class PipInstaller(BaseInstaller):
    """Installs packages via pip."""

    name = "pip"

    def _cmd(self) -> list[str]:
        if self.venv:
            return _venv_pip_cmd(self.venv)
        return _ENV_PIP

    def install(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        args = [*self._cmd(), "install"]
        if editable:
            args.append("-e")
        args.append(str(package_path))
        if extra_args:
            args.extend(extra_args)
        subprocess.run(args, check=True)

    def update(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        args = [*self._cmd(), "install", "--force-reinstall", str(package_path)]
        if extra_args:
            args.extend(extra_args)
        subprocess.run(args, check=True)

    def inject(
        self,
        venv_name: str,
        package_path: Path,
        extra_args: list[str] | None = None,
    ) -> None:
        msg = "pip has no 'inject' command. Use pipx-rns inject instead."
        raise NotImplementedError(msg)

    def list_packages(self) -> None:
        subprocess.run([*self._cmd(), "list"])

    def uninstall(self, package: str) -> None:
        subprocess.run([*self._cmd(), "uninstall", package])


class PipxInstaller(BaseInstaller):
    """Installs packages via pipx (isolated per-package venvs)."""

    name = "pipx"

    def _cmd(self) -> list[str]:
        return _ENV_PIPX

    def install(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        args = [*self._cmd(), "install", str(package_path)]
        if extra_args:
            args.extend(extra_args)
        subprocess.run(args, check=True)

    def update(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        pkg_name = package_path.name
        args = [*self._cmd(), "upgrade", pkg_name]
        try:
            subprocess.run(
                args, check=True,
                capture_output=True, text=True,
            )
            return
        except Exception:
            pass
        args = [*self._cmd(), "install", "--force", str(package_path)]
        if extra_args:
            args.extend(extra_args)
        subprocess.run(args, check=True)

    def inject(
        self,
        venv_name: str,
        package_path: Path,
        extra_args: list[str] | None = None,
    ) -> None:
        args = [*self._cmd(), "inject", venv_name, str(package_path)]
        if extra_args:
            args.extend(extra_args)
        subprocess.run(args, check=True)

    def list_packages(self) -> None:
        subprocess.run([*self._cmd(), "list"])

    def uninstall(self, package: str) -> None:
        subprocess.run([*self._cmd(), "uninstall", package])


class UvInstaller(BaseInstaller):
    """Installs packages via uv (rust-based pip alternative)."""

    name = "uv"

    def _cmd(self) -> list[str]:
        return _ENV_UV

    def install(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        args = [*self._cmd(), "pip", "install"]
        if editable:
            args.append("-e")
        args.append(str(package_path))
        if extra_args:
            args.extend(extra_args)
        subprocess.run(args, check=True)

    def update(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        args = [
            *self._cmd(),
            "pip",
            "install",
            "--force-reinstall",
            str(package_path),
        ]
        if extra_args:
            args.extend(extra_args)
        subprocess.run(args, check=True)

    def inject(
        self,
        venv_name: str,
        package_path: Path,
        extra_args: list[str] | None = None,
    ) -> None:
        msg = "uv has no 'inject' command. Use pipx-rns inject instead."
        raise NotImplementedError(msg)

    def list_packages(self) -> None:
        subprocess.run([*self._cmd(), "pip", "list"])

    def uninstall(self, package: str) -> None:
        subprocess.run([*self._cmd(), "pip", "uninstall", package])


class PoetryInstaller(BaseInstaller):
    """Installs packages via poetry (adds as a project dependency)."""

    name = "poetry"

    def _cmd(self) -> list[str]:
        return _ENV_POETRY

    def install(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        args = [*self._cmd(), "add", str(package_path)]
        if editable:
            args.insert(1, "--editable")
        if extra_args:
            args.extend(extra_args)
        subprocess.run(args, check=True)

    def update(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        args = [*self._cmd(), "add", "--editable", str(package_path)]
        if extra_args:
            args.extend(extra_args)
        subprocess.run(args, check=True)

    def inject(
        self,
        venv_name: str,
        package_path: Path,
        extra_args: list[str] | None = None,
    ) -> None:
        msg = "poetry has no 'inject' command. Use pipx-rns inject instead."
        raise NotImplementedError(msg)

    def list_packages(self) -> None:
        subprocess.run([*self._cmd(), "show"])

    def uninstall(self, package: str) -> None:
        subprocess.run([*self._cmd(), "remove", package])


register_installer("pip", PipInstaller)
register_installer("pipx", PipxInstaller)
register_installer("uv", UvInstaller)
register_installer("poetry", PoetryInstaller)
