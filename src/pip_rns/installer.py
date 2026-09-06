# Copyright (c) 2026, Quad4 (quad4.io)
"""Pluggable package installer backends (pip, pipx, uv, poetry)."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

_REGISTERED_INSTALLERS: dict[str, type[BaseInstaller]] = {}

_ENV_PIP = shlex.split(os.environ.get("PIP_RNS_PIP", "pip"))
_ENV_PIPX = shlex.split(os.environ.get("PIP_RNS_PIPX", "pipx"))
_ENV_UV = shlex.split(os.environ.get("PIP_RNS_UV", "uv"))
_ENV_POETRY = shlex.split(os.environ.get("PIP_RNS_POETRY", "poetry"))


class InstallerError(RuntimeError):
    """Friendly installer failure with optional recovery kind and hints."""

    def __init__(
        self,
        message: str,
        *,
        kind: str | None = None,
        hints: list[str] | None = None,
        output: str | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.hints = list(hints or [])
        self.output = output or ""


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


def _venv_python(venv: str) -> Path:
    base = Path(venv)
    if os.name == "nt":
        return base / "Scripts" / "python.exe"
    return base / "bin" / "python"


def _venv_pip_cmd(venv: str) -> list[str]:
    return [str(_venv_python(venv)), "-m", "pip"]


def classify_install_failure(
    cmd: list[str],
    returncode: int,
    output: str,
) -> InstallerError:
    """Map backend stderr/stdout into an InstallerError with hints."""
    text = output or ""
    low = text.lower()
    tool = cmd[0] if cmd else "installer"

    if (
        "externally-managed-environment" in low
        or "externally managed" in low
        or "pep 668" in low
    ):
        return InstallerError(
            "System Python is externally managed (PEP 668).",
            kind="externally_managed",
            hints=[
                "Install into a virtual environment:",
                "  pip-rns install <remote> --venv .venv",
                "  python -m venv .venv && pip-rns install <remote> --venv .venv",
                "Or use an isolated app install:",
                "  pip-rns install <remote> --pipx",
                "  pipx-rns install <remote>",
            ],
            output=text,
        )

    if "no module named pip" in low or "no module named 'pip'" in low:
        return InstallerError(
            "pip is not available in this Python environment.",
            kind="missing_pip",
            hints=[
                "Create a venv with pip, then retry:",
                "  python -m venv .venv && .venv/bin/python -m ensurepip",
                "  pip-rns install <remote> --venv .venv",
                "Or use uv / manual / zipapp (no system pip):",
                "  pip-rns install <remote> --uv --venv .venv",
                "  python3 pip-rns.pyz install ./pkg.whl",
                "  python3 pip-rns.pyz self-install --user",
            ],
            output=text,
        )

    if "permission denied" in low or "operation not permitted" in low:
        return InstallerError(
            "Permission denied while installing packages.",
            kind="permission",
            hints=[
                "Avoid system site-packages. Use a venv or pipx:",
                "  pip-rns install <remote> --venv .venv",
                "  pip-rns install <remote> --pipx",
            ],
            output=text,
        )

    if "no space left on device" in low:
        return InstallerError(
            "Disk full while installing packages.",
            kind="disk_full",
            hints=["Free disk space and retry."],
            output=text,
        )

    if "could not find a version that satisfies" in low or (
        "no matching distribution" in low
    ):
        return InstallerError(
            "No matching package distribution found.",
            kind="not_found",
            hints=[
                "Check the package name, Python version, and platform tags.",
                "Try --from-source if a release wheel is wrong for this host.",
            ],
            output=text,
        )

    if "error: failed to build" in low or (
        "building wheel for" in low and "error" in low
    ):
        return InstallerError(
            "Package build failed.",
            kind="build_failed",
            hints=[
                "Install build deps for this package, or use "
                "--from-release when a wheel exists.",
            ],
            output=text,
        )

    summary = text.strip().splitlines()
    tail = summary[-8:] if summary else [f"{tool} exited with code {returncode}"]
    return InstallerError(
        "Package install failed.",
        kind="install_failed",
        hints=[
            "Retry with an isolated target:",
            "  pip-rns install <remote> --venv .venv",
            "  pip-rns install <remote> --pipx",
        ]
        + [f"  {line}" for line in tail if line.strip()],
        output=text,
    )


def run_installer_cmd(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run an installer command and raise InstallerError on failure."""
    try:
        result = subprocess.run(args, capture_output=True, text=True)
    except FileNotFoundError as exc:
        missing = args[0] if args else "command"
        raise InstallerError(
            f"Command not found: {missing}",
            kind="missing_command",
            hints=[
                f"Install {missing} and ensure it is on PATH.",
                "For pip installs into a venv: pip-rns install <remote> --venv .venv",
                "For apps: pip-rns install <remote> --pipx",
            ],
        ) from exc

    stdout = result.stdout if isinstance(result.stdout, str) else ""
    stderr = result.stderr if isinstance(result.stderr, str) else ""
    returncode = result.returncode if isinstance(result.returncode, int) else 0

    if stdout:
        sys.stdout.write(stdout)
        if not stdout.endswith("\n"):
            sys.stdout.write("\n")
    if stderr:
        sys.stderr.write(stderr)
        if not stderr.endswith("\n"):
            sys.stderr.write("\n")

    if returncode != 0:
        raise classify_install_failure(args, returncode, stderr + stdout)
    return result


def format_installer_error(exc: InstallerError) -> str:
    """Render InstallerError for stderr."""
    return "\n".join([f"error: {exc}", *exc.hints])


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
        run_installer_cmd(args)

    def update(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        args = [*self._cmd(), "install", "--force-reinstall", str(package_path)]
        if extra_args:
            args.extend(extra_args)
        run_installer_cmd(args)

    def inject(
        self,
        venv_name: str,
        package_path: Path,
        extra_args: list[str] | None = None,
    ) -> None:
        msg = "pip has no 'inject' command. Use pipx-rns inject instead."
        raise NotImplementedError(msg)

    def list_packages(self) -> None:
        run_installer_cmd([*self._cmd(), "list"])

    def uninstall(self, package: str) -> None:
        run_installer_cmd([*self._cmd(), "uninstall", "-y", package])


class PipxInstaller(BaseInstaller):
    """Installs packages via pipx (isolated per-package venvs)."""

    name = "pipx"

    def _cmd(self) -> list[str]:
        return _ENV_PIPX

    def _pkg_name(self, package_path: Path) -> str:
        return _detect_pkg_name(package_path) or package_path.name

    def install(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        args = [*self._cmd(), "install", str(package_path)]
        if extra_args:
            args.extend(extra_args)
        try:
            run_installer_cmd(args)
        except InstallerError as exc:
            pkg = self._pkg_name(package_path)
            out = (exc.output or "").lower()
            if "already" in out and "installed" in out:
                print(
                    f"  {pkg} is already installed. reinstalling "
                    "(use 'pipx-rns update' next time)",
                )
                self.update(
                    package_path,
                    editable=editable,
                    extra_args=extra_args,
                )
                return
            runpip_args = [
                *self._cmd(),
                "runpip",
                pkg,
                "install",
                "--force-reinstall",
                str(package_path),
            ]
            try:
                run_installer_cmd(runpip_args)
                return
            except InstallerError:
                pass
            raise

    def update(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        pkg = self._pkg_name(package_path)
        runpip_args = [
            *self._cmd(),
            "runpip",
            pkg,
            "install",
            "--force-reinstall",
            str(package_path),
        ]
        try:
            run_installer_cmd(runpip_args)
            return
        except InstallerError:
            pass
        extra_args = extra_args or []
        args = [*self._cmd(), "install", "--force", str(package_path), *extra_args]
        run_installer_cmd(args)

    def inject(
        self,
        venv_name: str,
        package_path: Path,
        extra_args: list[str] | None = None,
    ) -> None:
        args = [*self._cmd(), "inject", venv_name, str(package_path)]
        if extra_args:
            args.extend(extra_args)
        run_installer_cmd(args)

    def list_packages(self) -> None:
        run_installer_cmd([*self._cmd(), "list"])

    def uninstall(self, package: str) -> None:
        run_installer_cmd([*self._cmd(), "uninstall", package])


class UvInstaller(BaseInstaller):
    """Installs packages via uv (rust-based pip alternative)."""

    name = "uv"

    def _cmd(self) -> list[str]:
        return _ENV_UV

    def _python_args(self) -> list[str]:
        if not self.venv:
            return []
        return ["--python", str(_venv_python(self.venv))]

    def install(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        args = [*self._cmd(), "pip", "install", *self._python_args()]
        if editable:
            args.append("-e")
        args.append(str(package_path))
        if extra_args:
            args.extend(extra_args)
        run_installer_cmd(args)

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
            "--reinstall",
            *self._python_args(),
            str(package_path),
        ]
        if extra_args:
            args.extend(extra_args)
        run_installer_cmd(args)

    def inject(
        self,
        venv_name: str,
        package_path: Path,
        extra_args: list[str] | None = None,
    ) -> None:
        msg = "uv has no 'inject' command. Use pipx-rns inject instead."
        raise NotImplementedError(msg)

    def list_packages(self) -> None:
        run_installer_cmd([*self._cmd(), "pip", "list", *self._python_args()])

    def uninstall(self, package: str) -> None:
        run_installer_cmd(
            [*self._cmd(), "pip", "uninstall", *self._python_args(), package],
        )


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
        args = [*self._cmd(), "add"]
        if editable:
            args.append("--editable")
        args.append(str(package_path))
        if extra_args:
            args.extend(extra_args)
        run_installer_cmd(args)

    def update(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        args = [*self._cmd(), "add", "--editable", str(package_path)]
        if extra_args:
            args.extend(extra_args)
        run_installer_cmd(args)

    def inject(
        self,
        venv_name: str,
        package_path: Path,
        extra_args: list[str] | None = None,
    ) -> None:
        msg = "poetry has no 'inject' command. Use pipx-rns inject instead."
        raise NotImplementedError(msg)

    def list_packages(self) -> None:
        run_installer_cmd([*self._cmd(), "show"])

    def uninstall(self, package: str) -> None:
        run_installer_cmd([*self._cmd(), "remove", package])


register_installer("pip", PipInstaller)
register_installer("pipx", PipxInstaller)
register_installer("uv", UvInstaller)
register_installer("poetry", PoetryInstaller)


class ManualInstaller(BaseInstaller):
    """Extract a wheel into site-packages without pip."""

    name = "manual"

    def install(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        if editable:
            raise InstallerError(
                "manual backend cannot install editable packages",
                kind="unsupported",
            )
        from opip.install import install_wheel_manual

        if self.venv:
            pyver = f"python{sys.version_info.major}.{sys.version_info.minor}"
            if os.name == "nt":
                target = Path(self.venv) / "Lib" / "site-packages"
            else:
                target = Path(self.venv) / "lib" / pyver / "site-packages"
        else:
            import site

            paths = site.getusersitepackages()
            target = Path(paths if isinstance(paths, str) else paths[0])
        install_wheel_manual(str(package_path), str(target))

    def update(
        self,
        package_path: Path,
        editable: bool = False,
        extra_args: list[str] | None = None,
    ) -> None:
        self.install(package_path, editable=editable, extra_args=extra_args)

    def inject(
        self,
        venv_name: str,
        package_path: Path,
        extra_args: list[str] | None = None,
    ) -> None:
        raise NotImplementedError("manual has no inject")

    def list_packages(self) -> None:
        raise NotImplementedError("manual has no list")

    def uninstall(self, package: str) -> None:
        raise NotImplementedError("manual has no uninstall")


register_installer("manual", ManualInstaller)


def _pip_module_available() -> bool:
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            check=True,
            capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False


def resolve_installer_name(preferred: str = "pip", venv: str | None = None) -> str:
    """Pick an installer when preferred pip is missing."""
    if preferred and preferred != "pip":
        return preferred
    if preferred == "pip" and _pip_module_available():
        return "pip"
    if shutil.which("uv") or (os.environ.get("PIP_RNS_UV")):
        # uv may still work when python -m pip does not
        try:
            get_installer("uv", venv=venv)
            return "uv"
        except Exception:
            pass
    return "manual"


def _detect_pkg_name(repo_path: Path) -> str | None:
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text()
            m = re.search(r'^name\s*=\s*"([^"]+)"', text, re.MULTILINE)
            if m:
                return m.group(1)
        except Exception:
            pass
    setup = repo_path / "setup.py"
    if setup.exists():
        try:
            text = setup.read_text()
            m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', text)
            if m:
                return m.group(1)
        except Exception:
            pass
    return None
