"""Install wheels from offline bundles."""

import os
import shutil
import subprocess
import sys
import zipfile

from opip.bundle import extract_bundle, verify_bundle_contents
from opip.resolver import detect_platform, detect_python_version, is_universal_platform
from opip.wheel import parse_wheel_filename, wheel_matches_platform


class InstallError(Exception):
    pass


def _find_pip():
    """Return True if pip is available for the current interpreter."""
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _select_wheels_for_install(manifest, wheels_dir):
    """Return wheel paths compatible with this machine."""
    py_version = detect_python_version()
    platform_tag = detect_platform()
    manifest_platform = manifest.get("platform")

    if not is_universal_platform(manifest_platform):
        return sorted(
            os.path.join(wheels_dir, w["filename"])
            for w in manifest.get("wheels", [])
            if os.path.isfile(os.path.join(wheels_dir, w["filename"]))
        )

    selected = []
    for w in manifest.get("wheels", []):
        whl_path = os.path.join(wheels_dir, w["filename"])
        if not os.path.isfile(whl_path):
            continue
        parsed = parse_wheel_filename(w["filename"])
        if parsed and wheel_matches_platform(parsed, py_version, platform_tag):
            selected.append(whl_path)

    if not selected:
        raise InstallError(
            "No wheels in universal bundle match Python {0} on {1}".format(
                py_version, platform_tag
            )
        )
    return sorted(selected)


def install_via_pip(wheels_dir, requirements_path, target=None, user=False, replace=False, wheels=None):
    """Install using pip --no-index --find-links."""
    import glob

    wheel_paths = wheels or sorted(glob.glob(os.path.join(wheels_dir, "*.whl")))
    cmd = [
        sys.executable,
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
    cmd.extend(wheel_paths if wheel_paths else ["-r", requirements_path])
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True
    )
    if result.returncode != 0:
        raise InstallError(
            "pip install failed:\n{0}".format(result.stderr or result.stdout)
        )
    return result.stdout


def install_wheel_manual(wheel_path, target_dir):
    """
    Install a single wheel by extracting into target_dir.

    Fallback when pip is not available.
    """
    os.makedirs(target_dir, exist_ok=True)
    with zipfile.ZipFile(wheel_path, "r") as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            dest = os.path.join(target_dir, name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(name) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)


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
):
    """
    Install all wheels from a bundle.

    Returns list of installed package names.
    """
    ctx = extract_bundle(bundle_path)
    extract_dir = ctx["dest_dir"]
    manifest = ctx["manifest"]

    try:
        if verify:
            errors = verify_bundle_contents(
                ctx,
                bundle_path=os.path.abspath(bundle_path),
                signer=signer,
                require_signature=require_signature,
            )
            if errors:
                raise InstallError(
                    "Bundle verification failed:\n" + "\n".join(errors)
                )

        wheels_dir = os.path.join(extract_dir, "wheels")
        req_path = os.path.join(extract_dir, "requirements.txt")

        if not os.path.isdir(wheels_dir):
            raise InstallError("Bundle missing wheels/ directory")

        packages = [w["package"] for w in manifest.get("wheels", [])]

        if _find_pip():
            wheel_paths = _select_wheels_for_install(manifest, wheels_dir)
            install_via_pip(
                wheels_dir,
                req_path,
                target=target,
                user=user,
                replace=replace or force,
                wheels=wheel_paths,
            )
        else:
            target_dir = target or _default_install_target(user)
            wheel_paths = _select_wheels_for_install(manifest, wheels_dir)
            for whl in wheel_paths:
                install_wheel_manual(whl, target_dir)

        if store is not None:
            bundle_name = manifest.get("name") or os.path.basename(bundle_path)
            store.record_install(
                bundle_name,
                packages,
                target=target,
                bundle_path=bundle_path,
            )
            store.register_bundle(bundle_name, bundle_path, manifest)

        return packages

    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)


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
):
    """Acquire bundle from any source and install."""
    from opip.sources import acquire_bundle

    from opip.storage import default_cache_dir

    cache_dir = cache_dir or os.path.join(default_cache_dir(), "acquired")
    os.makedirs(cache_dir, exist_ok=True)
    bundle_path = acquire_bundle(
        source, dest_dir=cache_dir, verify_identity=signer
    )
    return install_bundle(
        bundle_path,
        target=target,
        user=user,
        replace=replace,
        store=store,
        verify=verify,
        signer=signer,
        require_signature=require_signature,
    )


def uninstall_from_file(bundle_path, store=None, user=False, target=None):
    """Uninstall using the bundle name embedded in a .opip file."""
    from opip.bundle import bundle_info

    manifest = bundle_info(bundle_path)
    name = manifest.get("name") or os.path.splitext(os.path.basename(bundle_path))[0]
    from opip.uninstall import uninstall_bundle

    return uninstall_bundle(name, store=store, user=user, target=target)
