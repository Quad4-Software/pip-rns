"""High-level orchestration: resolve a remote, clone it, install it, clean up."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable

from .installer import BaseInstaller, InstallerError, get_installer
from .resolver import Resolver, normalize_url, parse_ref, ref_implies_source
from .ui import bold, dim, green, header, success, yellow


def _cleanup(path: Path, editable: bool, use_cache: bool = False) -> None:
    if not editable and not use_cache:
        shutil.rmtree(path, ignore_errors=True)


def _action_install(
    inst: BaseInstaller,
    package_path: Path,
    editable: bool,
    extra_args: list[str] | None,
    **kwargs: object,
) -> None:
    inst.install(package_path, editable=editable, extra_args=extra_args)


def _action_update(
    inst: BaseInstaller,
    package_path: Path,
    editable: bool,
    extra_args: list[str] | None,
    **kwargs: object,
) -> None:
    inst.update(package_path, editable=editable, extra_args=extra_args)


def _action_inject(
    inst: BaseInstaller,
    package_path: Path,
    editable: bool,
    extra_args: list[str] | None,
    inject_venv: str | None = None,
    **kwargs: object,
) -> None:
    if not inject_venv:
        msg = "inject requires a venv name"
        raise ValueError(msg)
    inst.inject(inject_venv, package_path, extra_args=extra_args)


_ActionFn = Callable[..., None]

_ACTIONS: dict[str, _ActionFn] = {
    "install": _action_install,
    "update": _action_update,
    "inject": _action_inject,
}


def _resolve_remote_label(remote: str) -> str:
    from .aliases import get_manager as get_alias_mgr
    from .indexes import get_manager as get_index_mgr

    amgr = get_alias_mgr()
    if amgr is not None:
        remote = amgr.resolve(remote)
    imgr = get_index_mgr()
    if imgr is not None:
        remote = imgr.resolve(remote)
    return normalize_url(remote)


def _print_status(
    *,
    resolved: str,
    mode: str,
    artifact: str | None = None,
    dest: str | None = None,
    signer: str | None = None,
) -> None:
    print(f"  {dim('Resolved:')} {resolved}")
    print(f"  {dim('Mode:')} {mode}")
    if artifact:
        print(f"  {dim('Artifact:')} {artifact}")
    print(f"  {dim('Dest:')} {dest or 'active environment'}")
    print(f"  {dim('Signer:')} {signer or 'not requested'}")


def _dest_label(venv: str | None) -> str:
    if venv:
        return f"venv {venv}"
    return "active environment"


def _venv_python(path: str | Path) -> Path:
    base = Path(path)
    if os.name == "nt":
        return base / "Scripts" / "python.exe"
    return base / "bin" / "python"


def _venv_has_pip(venv: str) -> bool:
    import subprocess

    py = _venv_python(venv)
    if not py.is_file():
        return False
    result = subprocess.run(
        [str(py), "-m", "pip", "--version"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _bootstrap_pip(venv: str) -> bool:
    """Try ensurepip so python -m pip works in the venv."""
    import subprocess

    py = _venv_python(venv)
    if not py.is_file():
        return False
    print(f"  {dim('bootstrapping pip in venv (ensurepip)')}")
    result = subprocess.run(
        [str(py), "-m", "ensurepip", "--upgrade"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    return _venv_has_pip(venv)


def _installer_for_venv(venv: str, preferred: str = "pip") -> str:
    """Pick pip or uv for a venv that may lack pip (common with uv-created envs)."""
    import shutil

    if preferred != "pip":
        return preferred
    if _venv_has_pip(venv):
        return "pip"
    if _bootstrap_pip(venv):
        return "pip"
    if shutil.which("uv") is not None:
        print(f"  {dim('venv has no pip; using uv pip --python')}")
        return "uv"
    return "pip"


def _ensure_venv(path: str) -> str:
    """Create a venv at path when missing. Returns absolute path."""
    import subprocess
    import sys

    dest = Path(path).expanduser().resolve()
    py = _venv_python(dest)
    if py.is_file():
        return str(dest)
    print(f"  {dim(f'creating venv at {dest}')}")
    subprocess.run([sys.executable, "-m", "venv", str(dest)], check=True)
    return str(dest)


def _offer_managed_env_recovery(
    *,
    installer: str,
    venv: str | None,
    no_interactive: bool,
) -> tuple[str, str | None] | None:
    """
    Prompt for recovery after PEP 668 / managed env failure.

    Returns (installer, venv) to retry, or None to abort.
    """
    from opip.interactive import is_noninteractive

    if installer not in ("pip", "uv") or (venv and installer == "uv"):
        return None
    if venv:
        # Already targeting a venv but pip was missing: switch to uv if possible
        chosen = _installer_for_venv(venv, preferred="pip")
        if chosen != installer:
            return chosen, venv
        return None
    if is_noninteractive(no_interactive):
        return None

    print(f"\n{yellow('System Python is externally managed (PEP 668).')}")
    print("Choose how to continue:")
    print("  1) Create/use a venv and retry")
    print("  2) Retry with --pipx")
    print("  3) Abort")
    try:
        choice = input("Choice [1/2/3]: ").strip() or "1"
    except (EOFError, KeyboardInterrupt) as exc:
        from .errors import UserCancelled

        raise UserCancelled("Cancelled.") from exc

    if choice == "2":
        return "pipx", None
    if choice != "1":
        return None

    try:
        path = input("Venv path [.venv]: ").strip() or ".venv"
    except (EOFError, KeyboardInterrupt) as exc:
        from .errors import UserCancelled

        raise UserCancelled("Cancelled.") from exc
    try:
        created = _ensure_venv(path)
    except Exception as exc:
        print(f"error: could not create venv: {exc}", file=__import__("sys").stderr)
        return None
    return _installer_for_venv(created, preferred="pip"), created


def _install_package(
    inst: BaseInstaller,
    package_path: Path,
    *,
    editable: bool = False,
    extra_args: list[str] | None = None,
    installer_name: str = "pip",
    venv: str | None = None,
    no_interactive: bool = False,
) -> tuple[BaseInstaller, str | None]:
    """Install with optional PEP 668 recovery. Returns (installer, venv used)."""
    current = inst
    current_installer = installer_name
    current_venv = venv
    attempts = 0
    while True:
        try:
            current.install(package_path, editable=editable, extra_args=extra_args)
            return current, current_venv
        except InstallerError as exc:
            if exc.kind not in ("externally_managed", "permission", "missing_pip"):
                raise
            attempts += 1
            if attempts > 2:
                raise
            recovered = _offer_managed_env_recovery(
                installer=current_installer,
                venv=current_venv,
                no_interactive=no_interactive,
            )
            if recovered is None:
                raise
            current_installer, current_venv = recovered
            current = get_installer(current_installer, venv=current_venv)


def _probe_release_wheel(remote: str, ref: str | None) -> tuple[str, str] | None:
    """Return (tag, whl_name) if a release wheel is available, else None."""
    from .releases import _normalize_remote, _pick_whl, release_info

    remote = _normalize_remote(remote)
    tag = ref or "latest"
    try:
        info = release_info(remote, tag)
    except Exception:
        return None
    artifacts = info.get("artifacts", [])
    whl = _pick_whl(artifacts)
    if not whl:
        return None
    return tag, whl


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
    no_interactive: bool = False,
) -> None:
    if ref is None:
        remote, ref = parse_ref(remote)

    label = (ref and f"{remote}@{ref}") or remote
    use_cache = use_cache or os.environ.get("PIP_RNS_USE_CACHE", "") == "1"
    resolved = _resolve_remote_label(remote)

    print(f"{header('⤵ Resolving')} {bold(label)}")
    inst = get_installer(installer, venv=venv)
    resolver = Resolver()
    package_path = resolver.resolve(
        remote,
        editable=editable,
        ref=ref,
        use_cache=use_cache,
    )

    status = getattr(resolver, "last_status", None)
    if status == "updated":
        print(f"  {dim('updated cached clone')}")
    elif status == "cached":
        print(f"  {dim('using cached clone')}")
    elif use_cache and not editable:
        print(f"  {dim('cached clone ready')}")

    fn = _ACTIONS.get(action)
    if fn is None:
        msg = f"Unknown action: {action}"
        raise ValueError(msg)

    try:
        if action == "install":
            _inst, venv = _install_package(
                inst,
                package_path,
                editable=editable,
                extra_args=extra_args,
                installer_name=installer,
                venv=venv,
                no_interactive=no_interactive,
            )
        else:
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
    _print_status(
        resolved=resolved,
        mode="source clone",
        dest=_dest_label(venv),
        signer="not requested",
    )
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
    from_source: bool = False,
    verify_identity: str | None = None,
    venv_explicit: bool = False,
    remember_venv: bool = False,
    forget_venv: bool = False,
    no_interactive: bool = False,
    config_dir: str | None = None,
) -> None:
    """Install a package from a remote (prefer release wheel when available)."""
    if from_release and from_source:
        raise ValueError("Use either --from-release or --from-source, not both")

    remote_base, embedded_ref = parse_ref(remote)
    if ref is None:
        ref = embedded_ref
    explicit_from_source = from_source
    # Branch-like @master/@main skips release probe; version tags still prefer wheels
    if (
        not from_release
        and not from_source
        and not editable
        and ref_implies_source(ref)
    ):
        from_source = True

    resolved = _resolve_remote_label(remote_base)
    # Prefer full normalize after alias resolve with ref stripped for prefs key
    from .releases import _normalize_remote
    from .venv_prefs import VenvPrefs, maybe_remember_venv

    prefs = VenvPrefs(config_dir)
    remote_key = _normalize_remote(resolved)
    if forget_venv:
        prefs.forget_remote(remote_key)

    if not venv_explicit:
        remembered = prefs.resolve(remote_key, None)
        if remembered:
            venv = remembered
            print(f"  {dim('Using remembered venv:')} {venv}")
    elif venv:
        venv = str(Path(venv).expanduser().resolve())

    # Bare remote (no ref / mode): offer interactive choices
    if not ref and not from_source and not from_release and not editable:
        from .install_prompt import offer_install_options

        choice = offer_install_options(resolved, no_interactive=no_interactive)
        if choice is not None:
            from_source = choice.from_source
            from_release = choice.from_release
            if choice.ref is not None:
                ref = choice.ref
            if from_source:
                explicit_from_source = True

    if editable or from_source:
        if from_release:
            raise ValueError(
                "--from-release cannot be combined with --editable/--from-source"
            )
        if explicit_from_source:
            print(f"  {dim('Cloning source (--from-source)')}")
        elif ref:
            print(f"  {dim(f'Cloning source (@{ref})')}")
        _run(
            resolved,
            "install",
            installer=installer,
            editable=editable,
            extra_args=extra_args,
            venv=venv,
            ref=ref,
            use_cache=use_cache,
            no_interactive=no_interactive,
        )
        maybe_remember_venv(
            prefs,
            remote_key,
            venv,
            venv_explicit=venv_explicit,
            remember=remember_venv,
            forget=False,
            no_interactive=no_interactive,
        )
        return

    if from_release:
        venv = install_from_release(
            resolved,
            installer=installer,
            ref=ref,
            extra_args=extra_args,
            venv=venv,
            verify_identity=verify_identity,
            require_wheel=True,
            no_interactive=no_interactive,
        )
        maybe_remember_venv(
            prefs,
            remote_key,
            venv,
            venv_explicit=venv_explicit or bool(venv),
            remember=remember_venv,
            forget=False,
            no_interactive=no_interactive,
        )
        return

    probe_remote = resolved
    probe_ref = ref
    hit = _probe_release_wheel(probe_remote, probe_ref)
    if hit:
        tag, whl = hit
        print(f"  {dim('Using release')} {bold(tag)} {dim(f'({whl})')}")
        venv = install_from_release(
            probe_remote,
            installer=installer,
            ref=tag if probe_ref is None and tag != "latest" else (probe_ref or tag),
            extra_args=extra_args,
            venv=venv,
            verify_identity=verify_identity,
            require_wheel=True,
            no_interactive=no_interactive,
        )
    else:
        print(f"  {dim('No release wheel; cloning source')}")
        _run(
            resolved,
            "install",
            installer=installer,
            editable=editable,
            extra_args=extra_args,
            venv=venv,
            ref=ref,
            use_cache=use_cache,
            no_interactive=no_interactive,
        )

    maybe_remember_venv(
        prefs,
        remote_key,
        venv,
        venv_explicit=venv_explicit or bool(venv),
        remember=remember_venv,
        forget=False,
        no_interactive=no_interactive,
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
    from_source: bool = False,
    verify_identity: str | None = None,
    venv_explicit: bool = False,
    remember_venv: bool = False,
    forget_venv: bool = False,
    no_interactive: bool = False,
    config_dir: str | None = None,
) -> None:
    """Reinstall a package from a remote, forcing a fresh install."""
    install(
        remote,
        installer=installer,
        editable=editable,
        extra_args=extra_args,
        venv=venv,
        ref=ref,
        use_cache=use_cache,
        from_release=from_release,
        from_source=from_source,
        verify_identity=verify_identity,
        venv_explicit=venv_explicit,
        remember_venv=remember_venv,
        forget_venv=forget_venv,
        no_interactive=no_interactive,
        config_dir=config_dir,
    )


def install_from_release(
    remote: str,
    *,
    installer: str = "pip",
    extra_args: list[str] | None = None,
    venv: str | None = None,
    ref: str | None = None,
    verify_identity: str | None = None,
    require_wheel: bool = False,
    no_interactive: bool = False,
) -> str | None:
    from .releases import (
        _normalize_remote,
        _parse_rns_url,
        _pick_whl,
        fetch_release_artifact,
        release_has_signatures,
        release_info,
    )

    remote = _normalize_remote(remote)
    _, group, repo = _parse_rns_url(remote)
    tag = ref or "latest"

    print(f"{header('⤵ Release')} {bold(tag)} {dim(f'{group}/{repo}')}")
    info = release_info(remote, tag)
    artifacts = info.get("artifacts", [])
    if not artifacts:
        msg = "no artifacts found"
        if require_wheel:
            raise RuntimeError(f"Release {tag}: {msg}")
        print(f"  {dim(msg)}")
        return venv

    whl = _pick_whl(artifacts)
    if not whl:
        msg = "no .whl found in release artifacts"
        if require_wheel:
            raise RuntimeError(f"Release {tag}: {msg}")
        print(f"  {dim(msg)}")
        return venv

    print(f"  {dim('artifact:')} {whl}")

    fetched = fetch_release_artifact(remote, tag, whl, verify_identity=verify_identity)
    whl_path = fetched.path
    print(f"  {dim(f'downloaded {whl}')}")
    # rngit release fetch validates .rsm and artifact .rsg before returning
    print(f"  {green('signature valid')}")
    if verify_identity:
        signer_status = f"verified {verify_identity}"
    elif fetched.signer:
        signer_status = f"verified {fetched.signer}"
    elif fetched.verified or release_has_signatures(artifacts):
        signer_status = "verified (release .rsm/.rsg)"
    else:
        signer_status = "verified (release fetch)"

    inst = get_installer(installer, venv=venv)
    try:
        _inst, venv = _install_package(
            inst,
            Path(whl_path),
            extra_args=extra_args,
            installer_name=installer,
            venv=venv,
            no_interactive=no_interactive,
        )
    finally:
        if os.path.isfile(whl_path):
            os.unlink(whl_path)
    _print_status(
        resolved=remote,
        mode=f"release {tag}",
        artifact=whl,
        dest=_dest_label(venv),
        signer=signer_status,
    )
    print(f"{success('✓ Done')}")
    return venv


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
