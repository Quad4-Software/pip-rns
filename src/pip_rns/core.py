"""High-level orchestration: resolve a remote, clone it, install it, clean up."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .installer import BaseInstaller, get_installer
from .resolver import Resolver, parse_ref
from .ui import bold, dim, green, header, success


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
    from_release: bool = False,
    verify_identity: str | None = None,
) -> None:
    """Clone a remote repository and install it as a Python package."""
    if from_release:
        install_from_release(remote, installer=installer, ref=ref, extra_args=extra_args, venv=venv, verify_identity=verify_identity)
        return
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
    from_release: bool = False,
    verify_identity: str | None = None,
) -> None:
    """Reinstall a package from a remote, forcing a fresh install."""
    if from_release:
        install_from_release(remote, installer=installer, ref=ref, extra_args=extra_args, venv=venv, verify_identity=verify_identity)
        return
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


def install_from_release(
    remote: str,
    *,
    installer: str = "pip",
    extra_args: list[str] | None = None,
    venv: str | None = None,
    ref: str | None = None,
    verify_identity: str | None = None,
) -> None:
    from .releases import (
        _normalize_remote,
        _parse_rns_url,
        _pick_whl,
        fetch_release_artifact,
        release_info,
    )

    remote = _normalize_remote(remote)
    _, group, repo = _parse_rns_url(remote)
    tag = ref or "latest"

    print(f"{header('⤵ Release')} {bold(tag)} {dim(f'{group}/{repo}')}")
    info = release_info(remote, tag)
    artifacts = info.get("artifacts", [])
    if not artifacts:
        print(f"  {dim('no artifacts found')}")
        return

    whl = _pick_whl(artifacts)
    if not whl:
        print(f"  {dim('no .whl found in release artifacts')}")
        return

    print(f"  {dim('artifact:')} {whl}")

    whl_path = fetch_release_artifact(remote, tag, whl, verify_identity=verify_identity)
    print(f"  {dim(f'downloaded {whl}')}")
    if verify_identity:
        print(f"  {green('signature valid')}")

    inst = get_installer(installer, venv=venv)
    inst.install(Path(whl_path), extra_args=extra_args)
    os.unlink(whl_path)
    print(f"{success('✓ Done')}")


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
