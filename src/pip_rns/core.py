"""High-level orchestration: resolve a remote, clone it, install it, clean up."""

from __future__ import annotations

import os
import shutil

from .installer import BaseInstaller, get_installer
from .resolver import Resolver, parse_ref
from .ui import bold, dim, header, success


def _cleanup(path: str, editable: bool, use_cache: bool = False) -> None:
    if not editable and not use_cache:
        shutil.rmtree(path, ignore_errors=True)


def _action_install(
    inst: BaseInstaller,
    package_path: str,
    editable: bool,
    extra_args: list[str] | None,
    **kwargs: object,
) -> None:
    inst.install(package_path, editable=editable, extra_args=extra_args)


def _action_update(
    inst: BaseInstaller,
    package_path: str,
    editable: bool,
    extra_args: list[str] | None,
    **kwargs: object,
) -> None:
    inst.update(package_path, editable=editable, extra_args=extra_args)


def _action_inject(
    inst: BaseInstaller,
    package_path: str,
    editable: bool,
    extra_args: list[str] | None,
    inject_venv: str | None = None,
    **kwargs: object,
) -> None:
    if not inject_venv:
        msg = "inject requires a venv name"
        raise ValueError(msg)
    inst.inject(inject_venv, package_path, extra_args=extra_args)


_ACTIONS: dict[str, callable] = {
    "install": _action_install,
    "update": _action_update,
    "inject": _action_inject,
}


def _run(
    remote: str,
    action: str,
    installer: str = "pip",
    editable: bool = False,
    extra_args: list[str] | None = None,
    venv: str | None = None,
    inject_venv: str | None = None,
    ref: str | None = None,
    use_cache: bool = False,
) -> None:
    if ref is None:
        remote, ref = parse_ref(remote)

    label = (ref and f"{remote}@{ref}") or remote
    use_cache = use_cache or os.environ.get("PIP_RNS_USE_CACHE", "") == "1"

    print(f"{header('⤵ Resolving')} {bold(label)}")
    inst = get_installer(installer, venv=venv)
    package_path = Resolver().resolve(
        remote,
        editable=editable,
        ref=ref,
        use_cache=use_cache,
    )

    if use_cache and not editable:
        print(f"  {dim('using cached copy')}")

    fn = _ACTIONS.get(action)
    if fn is None:
        msg = f"Unknown action: {action}"
        raise ValueError(msg)

    try:
        fn(
            inst,
            package_path,
            editable=editable,
            extra_args=extra_args,
            inject_venv=inject_venv,
        )
    except Exception:
        _cleanup(package_path, editable, use_cache=use_cache)
        raise

    _cleanup(package_path, editable, use_cache=use_cache)
    print(f"{success('✓ Done')}")


def install(
    remote: str,
    *,
    installer: str = "pip",
    editable: bool = False,
    extra_args: list[str] | None = None,
    venv: str | None = None,
    ref: str | None = None,
    use_cache: bool = False,
) -> None:
    """Clone a remote repository and install it as a Python package."""
    _run(
        remote,
        "install",
        installer=installer,
        editable=editable,
        extra_args=extra_args,
        venv=venv,
        ref=ref,
        use_cache=use_cache,
    )


def update(
    remote: str,
    *,
    installer: str = "pip",
    editable: bool = False,
    extra_args: list[str] | None = None,
    venv: str | None = None,
    ref: str | None = None,
    use_cache: bool = False,
) -> None:
    """Reinstall a package from a remote, forcing a fresh install."""
    _run(
        remote,
        "update",
        installer=installer,
        editable=editable,
        extra_args=extra_args,
        venv=venv,
        ref=ref,
        use_cache=use_cache,
    )


def inject(
    remote: str,
    venv_name: str,
    *,
    installer: str = "pipx",
    extra_args: list[str] | None = None,
    ref: str | None = None,
    use_cache: bool = False,
) -> None:
    """Inject a package from a remote into an existing pipx-managed venv."""
    _run(
        remote,
        "inject",
        installer=installer,
        inject_venv=venv_name,
        extra_args=extra_args,
        ref=ref,
        use_cache=use_cache,
    )


def list_packages(installer: str = "pip") -> None:
    """List packages installed by the given backend."""
    get_installer(installer).list_packages()


def uninstall(package: str, installer: str = "pip") -> None:
    """Uninstall a package using the given backend."""
    get_installer(installer).uninstall(package)
