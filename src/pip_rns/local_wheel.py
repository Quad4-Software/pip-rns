"""Install from local wheel files and export directories (sneakernet)."""

from __future__ import annotations

from pathlib import Path

from opip.signing import has_signature, verify_bundle_signature_info

from .installer import get_installer
from .ui import bold, dim, green, header, success, yellow


def is_wheel_source(path: str) -> bool:
    """True when path is a .whl file or directory containing wheel(s)."""
    p = Path(path.strip()).expanduser()
    if p.is_file() and p.suffix == ".whl":
        return True
    if p.is_dir():
        return bool(_find_wheels(p))
    return False


def _find_wheels(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.whl"))


def resolve_wheel_path(path: str) -> Path:
    """Resolve a wheel file from a path or export directory."""
    p = Path(path.strip()).expanduser().resolve()
    if p.is_file():
        if p.suffix != ".whl":
            msg = f"Not a wheel file: {p}"
            raise ValueError(msg)
        return p
    if p.is_dir():
        wheels = _find_wheels(p)
        if not wheels:
            msg = f"No .whl files in directory: {p}"
            raise FileNotFoundError(msg)
        if len(wheels) > 1:
            preferred = [w for w in wheels if not w.name.endswith("-none-any.whl")]
            return preferred[0] if preferred else wheels[0]
        return wheels[0]
    msg = f"Wheel path not found: {p}"
    raise FileNotFoundError(msg)


def verify_local_wheel(
    whl_path: Path,
    *,
    verify_identity: str | None = None,
    insecure: bool = False,
) -> tuple[bool, str | None]:
    """
    Verify .rsg sidecar when present.

    Returns (verified, signer_identity).
    """
    whl = str(whl_path)
    if not has_signature(whl):
        return True, None
    if insecure:
        return False, None
    errors, identity = verify_bundle_signature_info(whl, signer=verify_identity)
    if errors:
        raise RuntimeError(errors[0])
    return True, identity


def install_local_wheel(
    path: str,
    *,
    installer: str = "pip",
    extra_args: list[str] | None = None,
    venv: str | None = None,
    verify_identity: str | None = None,
    insecure: bool = False,
    no_interactive: bool = False,
    config_dir: str | None = None,
) -> None:
    """Install a local .whl (and verify .rsg when present)."""
    whl_path = resolve_wheel_path(path)
    print(f"{header('⤵ Local wheel')} {bold(whl_path.name)}")

    signer = verify_identity
    verified, discovered = verify_local_wheel(
        whl_path,
        verify_identity=signer,
        insecure=insecure,
    )
    if has_signature(str(whl_path)):
        if verified:
            print(f"  {green('signature valid')}")
            if discovered:
                print(f"  {dim('signer:')} {discovered}")
        elif insecure:
            print(f"  {yellow('insecure: skipping signature confirmation')}")
        else:
            raise RuntimeError(
                "Signed wheel verification failed. "
                "Use --verify IDENTITY, pip-rns trust add, or --insecure."
            )
    else:
        print(f"  {dim('unsigned wheel')}")

    inst = get_installer(installer, venv=venv)
    inst.install(whl_path, editable=False, extra_args=extra_args)
    print(f"{success('Done')}")
