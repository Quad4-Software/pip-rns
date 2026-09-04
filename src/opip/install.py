"""Install wheels from offline bundles."""

import os
import shutil
import subprocess
import sys

from opip.bundle import extract_bundle, verify_bundle_contents
from opip.resolver import detect_platform, detect_python_version
from opip.safe_zip import UnsafeZipError, extract_zip_safe, safe_artifact_name
from opip.wheel import parse_wheel_filename, wheel_matches_platform


class InstallError(Exception):
    pass


class InstallOutcome(list):
    """Package name list plus install destination metadata."""

    def __init__(self, packages, dest=None, venv=None):
        super().__init__(packages)
        self.dest = dest
        self.venv = venv


def _find_pip(python=None):
    """Return True if pip is available for the given interpreter."""
    python = python or sys.executable
    try:
        subprocess.run(
            [python, "-m", "pip", "--version"],
            check=True,
            capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def is_externally_managed_error(text):
    """True when pip refused install due to PEP 668."""
    low = (text or "").lower()
    return (
        "externally-managed-environment" in low
        or "pep 668" in low
        or "externally managed" in low
    )


def _venv_python(venv_dir):
    if os.name == "nt":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def _interpreter_version(python):
    """Return 'X.Y' for a Python executable, or None."""
    try:
        result = subprocess.run(
            [
                python,
                "-c",
                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    return (result.stdout or "").strip() or None


def _bootstrap_pip(python, venv_dir):
    from opip import terminal

    terminal.info(f"Bootstrapping pip in venv ({python} -m ensurepip)")
    result = subprocess.run(
        [python, "-m", "ensurepip", "--upgrade"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not _find_pip(python):
        detail = (result.stderr or result.stdout or "").strip()
        raise InstallError(
            f"pip unavailable in venv {venv_dir}."
            + (f"\n{detail}" if detail else "")
            + f"\nTry: {python} -m ensurepip --upgrade"
        )


def _confirm_recreate_venv(path, got, required, no_interactive):
    from opip import terminal
    from opip.interactive import is_noninteractive

    msg = f"Venv {path} uses Python {got} but this install needs Python {required}."
    if is_noninteractive(no_interactive):
        raise InstallError(
            msg + f"\nRecreate it: rm -rf {path} && opip install <bundle> --venv {path}"
        )
    terminal.warn(msg)
    try:
        sys.stdout.write("Recreate this venv with the current Python? [Y/n] ")
        sys.stdout.flush()
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt) as exc:
        raise InstallError("Cancelled.") from exc
    if answer in ("", "y", "yes"):
        return True
    raise InstallError(
        "Cancelled."
        f"\nUse a matching venv or: rm -rf {path} && opip install <bundle> --venv {path}"
    )


def ensure_venv(path, required_version=None, no_interactive=False):
    """
    Create or reuse a venv at path.

    Ensures the venv Python matches required_version (default: current
    interpreter). Recreates on mismatch when confirmed.
    """
    from opip import terminal

    required_version = required_version or detect_python_version()
    host_version = detect_python_version()
    if host_version != required_version:
        raise InstallError(
            f"Current Python is {host_version} but this bundle needs "
            f"Python {required_version}. Run opip with that interpreter."
        )

    dest = os.path.abspath(os.path.expanduser(path))
    py = _venv_python(dest)

    if os.path.isfile(py):
        got = _interpreter_version(py)
        if got is None:
            raise InstallError(
                f"Could not determine Python version for venv interpreter: {py}"
            )
        if got != required_version and _confirm_recreate_venv(
            dest, got, required_version, no_interactive
        ):
            terminal.info(f"Removing mismatched venv {dest}")
            shutil.rmtree(dest, ignore_errors=True)
            py = _venv_python(dest)

    if not os.path.isfile(py):
        terminal.info(f"Creating venv at {dest} (Python {required_version})")
        subprocess.run([sys.executable, "-m", "venv", dest], check=True)
        py = _venv_python(dest)
        if not os.path.isfile(py):
            raise InstallError(f"venv created but python missing: {dest}")

    got = _interpreter_version(py)
    if got is None:
        raise InstallError(
            f"Could not determine Python version for venv interpreter: {py}"
        )
    if got != required_version:
        raise InstallError(
            f"Venv {dest} still reports Python {got}, expected {required_version}."
        )

    if not _find_pip(py):
        _bootstrap_pip(py, dest)
    return dest


def _pep668_hints():
    return [
        "System Python is externally managed (PEP 668).",
        "Retry with one of:",
        "  opip install <bundle> --venv .venv",
        "  opip install <bundle> --user",
        "  opip install <bundle> --target ./vendor",
        "Or: python -m venv .venv && opip install <bundle> --venv .venv",
        "Note: on Arch/CachyOS, --user needs --break-system-packages "
        "(opip adds this automatically).",
    ]


def _offer_pep668_recovery(no_interactive=False, required_version=None):
    """
    Prompt for recovery after PEP 668 failure.

    Returns dict with keys among: venv, user, target, break_system_packages.
    """
    from opip import terminal
    from opip.interactive import is_noninteractive

    if is_noninteractive(no_interactive):
        raise InstallError("\n".join(_pep668_hints()))

    terminal.write_out("")
    terminal.warn("System Python is externally managed (PEP 668).")
    terminal.write_out("Choose how to continue:")
    terminal.write_out("  1) Create/use a venv and retry")
    terminal.write_out("  2) Install with --user (uses --break-system-packages)")
    terminal.write_out("  3) Install to a --target directory")
    terminal.write_out("  4) Abort")
    try:
        sys.stdout.write("Choice [1/2/3/4]: ")
        sys.stdout.flush()
        choice = input().strip() or "1"
    except (EOFError, KeyboardInterrupt) as exc:
        raise InstallError("Cancelled.") from exc

    if choice == "2":
        return {"user": True, "break_system_packages": True}
    if choice == "3":
        try:
            sys.stdout.write("Target directory: ")
            sys.stdout.flush()
            path = input().strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise InstallError("Cancelled.") from exc
        if not path:
            raise InstallError("Cancelled: empty --target path.")
        return {"target": os.path.abspath(os.path.expanduser(path))}
    if choice != "1":
        raise InstallError("Cancelled.")

    try:
        sys.stdout.write("Venv path [.venv]: ")
        sys.stdout.flush()
        path = input().strip() or ".venv"
    except (EOFError, KeyboardInterrupt) as exc:
        raise InstallError("Cancelled.") from exc
    try:
        venv = ensure_venv(
            path,
            required_version=required_version,
            no_interactive=no_interactive,
        )
    except InstallError:
        raise
    except Exception as exc:
        raise InstallError(f"Could not create venv: {exc}") from exc
    return {"venv": venv}


def _select_wheels_for_install(manifest, wheels_dir):
    """Return wheel paths compatible with this machine."""
    py_version = detect_python_version()
    platform_tag = detect_platform()
    required = manifest.get("python_version")
    if required and required != py_version:
        raise InstallError(
            f"This bundle was built for Python {required}, "
            f"but the current interpreter is {py_version} ({sys.executable})."
        )

    def _wheel_path(record):
        filename = safe_artifact_name(record["filename"])
        return os.path.join(wheels_dir, filename)

    selected = []
    skipped = []
    for w in manifest.get("wheels", []):
        try:
            whl_path = _wheel_path(w)
        except ValueError as exc:
            raise InstallError(str(exc))
        if not os.path.isfile(whl_path):
            continue
        parsed = parse_wheel_filename(w["filename"])
        if parsed is None:
            skipped.append(w["filename"])
            continue
        if wheel_matches_platform(parsed, py_version, platform_tag):
            selected.append(whl_path)
        else:
            skipped.append(w["filename"])

    if not selected:
        detail = ""
        if skipped:
            detail = "\nSkipped incompatible wheels:\n  " + "\n  ".join(skipped[:12])
        raise InstallError(
            f"No wheels in bundle match Python {py_version} on {platform_tag}." + detail
        )
    return sorted(selected)


def install_via_pip(
    wheels_dir,
    requirements_path,
    target=None,
    user=False,
    replace=False,
    wheels=None,
    python=None,
    break_system_packages=False,
):
    """Install using pip --no-index --find-links."""
    import glob

    python = python or sys.executable
    wheel_paths = wheels or sorted(glob.glob(os.path.join(wheels_dir, "*.whl")))
    cmd = [
        python,
        "-m",
        "pip",
        "install",
        "--no-index",
        "--pre",
        "--find-links",
        wheels_dir,
    ]
    if replace:
        cmd.extend(["--upgrade", "--force-reinstall"])
    if target:
        cmd.extend(["--target", target])
    if user:
        cmd.append("--user")
    if break_system_packages:
        cmd.append("--break-system-packages")
    cmd.extend(wheel_paths if wheel_paths else ["-r", requirements_path])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr or result.stdout or ""
        raise InstallError(f"pip install failed:\n{detail}")
    return result.stdout


def install_wheel_manual(wheel_path, target_dir):
    """
    Install a single wheel by extracting into target_dir.

    Fallback when pip is not available.
    """
    os.makedirs(target_dir, exist_ok=True)
    try:
        extract_zip_safe(wheel_path, target_dir)
    except UnsafeZipError as exc:
        raise InstallError(str(exc))


def _dest_label(target=None, user=False, venv=None):
    if venv:
        return f"venv {venv}"
    if target:
        return target
    if user:
        return "user site"
    return "system/active"


def _unsupported_wheel_hint(exc_text, required_version=None):
    low = (exc_text or "").lower()
    if "not a supported wheel on this platform" not in low:
        return None
    req = required_version or detect_python_version()
    return (
        "\nA wheel in this bundle does not match the install Python."
        f"\nBundle / expected Python: {req}"
        f"\nCurrent interpreter: {sys.executable} ({detect_python_version()})"
        "\nIf you pointed --venv at an old environment, recreate it with this Python:"
        "\n  rm -rf .venv && opip install <bundle> --venv .venv"
    )


def _run_pip_install_with_recovery(
    wheels_dir,
    req_path,
    wheel_paths,
    *,
    target=None,
    user=False,
    replace=False,
    venv=None,
    no_interactive=False,
    required_version=None,
    break_system_packages=False,
):
    """Install via pip, offering PEP 668 recovery when needed."""
    from opip import terminal

    current_target = target
    current_user = user
    current_venv = venv
    current_break = break_system_packages
    attempts = 0

    while True:
        python = _venv_python(current_venv) if current_venv else sys.executable
        if current_venv and not os.path.isfile(python):
            raise InstallError(f"venv python not found: {python}")
        if not _find_pip(python):
            if current_venv:
                raise InstallError(
                    f"pip unavailable in venv {current_venv}. "
                    f"Try: {python} -m ensurepip"
                )
            return current_target, current_user, current_venv, False
        try:
            install_via_pip(
                wheels_dir,
                req_path,
                target=current_target,
                user=current_user,
                replace=replace,
                wheels=wheel_paths,
                python=python,
                break_system_packages=current_break,
            )
            if current_venv:
                activate = (
                    os.path.join(current_venv, "Scripts", "activate")
                    if os.name == "nt"
                    else os.path.join(current_venv, "bin", "activate")
                )
                terminal.info(f"Installed into venv {current_venv}")
                if os.name == "nt":
                    terminal.info(f"Activate with: {activate}")
                else:
                    terminal.info(f"Activate with: source {activate}")
            return current_target, current_user, current_venv, True
        except InstallError as exc:
            text = str(exc)
            tip = _unsupported_wheel_hint(text, required_version=required_version)
            if tip and current_venv:
                raise InstallError(text + tip) from exc

            if current_target or current_venv:
                raise
            if not is_externally_managed_error(text):
                raise

            # Arch/CachyOS: --user still needs --break-system-packages.
            if current_user and not current_break:
                terminal.info("Retrying --user with --break-system-packages (PEP 668)")
                current_break = True
                continue

            attempts += 1
            if attempts > 2:
                raise InstallError(text + "\n\n" + "\n".join(_pep668_hints())) from exc
            recovered = _offer_pep668_recovery(
                no_interactive=no_interactive,
                required_version=required_version,
            )
            if recovered.get("venv"):
                current_venv = recovered["venv"]
                current_target = None
                current_user = False
                current_break = False
            elif recovered.get("user"):
                current_user = True
                current_break = bool(recovered.get("break_system_packages"))
            elif recovered.get("target"):
                current_target = recovered["target"]
                current_user = False
                current_break = False


def install_bundle(
    bundle_path,
    target=None,
    user=False,
    force=False,
    replace=False,
    store=None,
    verify=True,
    signer=None,
    require_signature=False,
    target_explicit=False,
    remember_target=False,
    forget_target=False,
    no_interactive=False,
    venv=None,
):
    """
    Install all wheels from a bundle.

    Returns InstallOutcome (list of package names with .dest / .venv).
    """
    from opip import terminal
    from opip.interactive import is_noninteractive

    ctx = extract_bundle(bundle_path)
    extract_dir = ctx["dest_dir"]
    manifest = ctx["manifest"]
    bundle_name = (
        manifest.get("name") or os.path.splitext(os.path.basename(bundle_path))[0]
    )
    noninteractive = is_noninteractive(no_interactive)
    required_version = manifest.get("python_version") or detect_python_version()

    try:
        if forget_target and store is not None:
            store.forget_preferred_target(bundle_name)

        if target is None and venv is None and store is not None:
            remembered = store.get_preferred_target(bundle_name)
            if remembered:
                target = remembered
                terminal.info(f"Using remembered target: {target}")

        if venv:
            venv = ensure_venv(
                venv,
                required_version=required_version,
                no_interactive=noninteractive,
            )

        if verify:
            errors = verify_bundle_contents(
                ctx,
                bundle_path=os.path.abspath(bundle_path),
                signer=signer,
                require_signature=require_signature,
            )
            if errors:
                raise InstallError("Bundle verification failed:\n" + "\n".join(errors))

        wheels_dir = os.path.join(extract_dir, "wheels")
        req_path = os.path.join(extract_dir, "requirements.txt")

        if not os.path.isdir(wheels_dir):
            raise InstallError("Bundle missing wheels/ directory")

        packages = [w["package"] for w in manifest.get("wheels", [])]
        wheel_paths = _select_wheels_for_install(manifest, wheels_dir)

        used_pip = False
        if _find_pip() or (venv and _find_pip(_venv_python(venv))):
            target, user, venv, used_pip = _run_pip_install_with_recovery(
                wheels_dir,
                req_path,
                wheel_paths,
                target=target,
                user=user,
                replace=replace or force,
                venv=venv,
                no_interactive=noninteractive,
                required_version=required_version,
            )

        if not used_pip:
            target_dir = target or _default_install_target(user)
            for whl in wheel_paths:
                install_wheel_manual(whl, target_dir)
            if target is None and venv is None:
                target = target_dir

        dest = _dest_label(target=target, user=user, venv=venv)

        if store is not None:
            store.record_install(
                bundle_name,
                packages,
                target=target or venv,
                bundle_path=bundle_path,
            )
            store.register_bundle(bundle_name, bundle_path, manifest)
            _maybe_remember_target(
                store,
                bundle_name,
                target,
                target_explicit=target_explicit,
                remember_target=remember_target,
                no_interactive=noninteractive,
            )

        return InstallOutcome(packages, dest=dest, venv=venv)

    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)


def _maybe_remember_target(
    store,
    bundle_name,
    target,
    target_explicit=False,
    remember_target=False,
    no_interactive=False,
):
    if not target:
        return
    from opip import terminal

    if remember_target:
        store.set_preferred_target(bundle_name, target)
        terminal.info(f"Remembered target for {bundle_name}: {target}")
        return
    if not target_explicit or no_interactive:
        return
    existing = store.get_preferred_target(bundle_name)
    if existing and os.path.abspath(existing) == os.path.abspath(target):
        return
    sys.stdout.write(f"Remember {target} for {bundle_name}? [y/N] ")
    sys.stdout.flush()
    try:
        answer = input().strip().lower()
    except EOFError:
        answer = ""
    if answer in ("y", "yes"):
        store.set_preferred_target(bundle_name, target)
        terminal.info(f"Remembered target for {bundle_name}: {target}")


def _default_install_target(user):
    if user:
        import site

        paths = site.getusersitepackages()
        if isinstance(paths, str):
            return paths
        return paths[0] if paths else site.USER_SITE

    import site

    return site.getsitepackages()[0]


def install_from_source(
    source,
    target=None,
    user=False,
    replace=False,
    store=None,
    cache_dir=None,
    verify=True,
    signer=None,
    require_signature=False,
    target_explicit=False,
    remember_target=False,
    forget_target=False,
    no_interactive=False,
    venv=None,
):
    """Acquire bundle from any source and install."""
    from opip.sources import acquire_bundle
    from opip.storage import default_cache_dir

    cache_dir = cache_dir or os.path.join(default_cache_dir(), "acquired")
    os.makedirs(cache_dir, exist_ok=True)
    bundle_path = acquire_bundle(source, dest_dir=cache_dir, verify_identity=signer)
    return install_bundle(
        bundle_path,
        target=target,
        user=user,
        replace=replace,
        store=store,
        verify=verify,
        signer=signer,
        require_signature=require_signature,
        target_explicit=target_explicit,
        remember_target=remember_target,
        forget_target=forget_target,
        no_interactive=no_interactive,
        venv=venv,
    )


def uninstall_from_file(bundle_path, store=None, user=False, target=None):
    """Uninstall using the bundle name embedded in a .opip file."""
    from opip.bundle import bundle_info

    manifest = bundle_info(bundle_path)
    name = manifest.get("name") or os.path.splitext(os.path.basename(bundle_path))[0]
    from opip.uninstall import uninstall_bundle

    return uninstall_bundle(name, store=store, user=user, target=target)
