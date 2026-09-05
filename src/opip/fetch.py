# Copyright (c) 2026, Quad4 (quad4.io)
"""Download wheels and files from remote sources (stdlib only)."""

import ftplib
import os
import shutil
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from opip.integrity import file_hash
from opip.safe_zip import contain_path, safe_artifact_name
from opip.wheel_cache import lookup_wheel, store_wheel

USER_AGENT = "opip/{} (+https://github.com/Quad4-Software/pip-rns)".format(
    __import__("opip").__version__,
)
CHUNK_SIZE = 65536


class FetchError(Exception):
    pass


def _build_opener(proxy=None):
    from opip.proxy import ProxyError, build_opener

    ctx = ssl.create_default_context()
    try:
        return build_opener(proxy=proxy, context=ctx)
    except ProxyError as exc:
        raise FetchError(str(exc)) from exc


def download_url(url, dest_path, timeout=120, expected_hash=None, proxy=None):
    """Download URL to dest_path. Optionally verify SHA-256."""
    opener = _build_opener(proxy=proxy)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener.open(req, timeout=timeout) as resp:
            os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
            with open(dest_path, "wb") as out:
                while True:
                    chunk = resp.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    out.write(chunk)
    except urllib.error.URLError as exc:
        raise FetchError(f"Download failed for {url}: {exc}")

    if expected_hash:
        actual = file_hash(dest_path)
        if actual != expected_hash:
            os.remove(dest_path)
            raise FetchError(
                f"Hash mismatch for {url}:"
                f" expected {expected_hash[:16]}, got {actual[:16]}",
            )
    return dest_path


def download_wheel(
    wheel_spec,
    dest_dir,
    timeout=120,
    use_cache=True,
    require_pypi_hash=False,
):
    """Download a wheel from resolver spec into dest_dir."""
    try:
        filename = safe_artifact_name(wheel_spec["filename"])
    except ValueError as exc:
        raise FetchError(str(exc))
    dest = os.path.join(dest_dir, filename)
    expected = None
    digests = wheel_spec.get("digests") or {}
    if "sha256" in digests:
        expected = digests["sha256"]
    elif require_pypi_hash:
        raise FetchError(
            f"PyPI provides no sha256 digest for {filename}."
            " use without --require-pypi-hash",
        )

    local_path = wheel_spec.get("path")
    url = wheel_spec.get("url") or ""
    if not local_path and url.startswith("file://"):
        local_path = url[7:]
        if (
            os.name == "nt"
            and local_path.startswith("/")
            and len(local_path) > 2
            and local_path[2] == ":"
        ):
            # file:///C:/path
            local_path = local_path[1:]

    if local_path and os.path.isfile(local_path):
        if expected and file_hash(local_path) != expected:
            raise FetchError(
                f"Hash mismatch for local {filename}: expected {expected[:16]}",
            )
        shutil.copy2(local_path, dest)
        if use_cache:
            store_wheel(dest, filename=filename, expected_hash=expected)
        return dest

    if use_cache:
        cached = lookup_wheel(filename, expected)
        if cached:
            if expected and file_hash(cached) != expected:
                os.remove(cached)
            else:
                shutil.copy2(cached, dest)
                return dest

    if not url or url.startswith("file://"):
        raise FetchError(f"No download URL for {filename}")

    download_url(url, dest, timeout=timeout, expected_hash=expected)
    if use_cache:
        store_wheel(dest, filename=filename, expected_hash=expected)
    return dest


def download_wheels_parallel(
    wheel_specs,
    dest_dir,
    jobs=8,
    timeout=120,
    use_cache=True,
    require_pypi_hash=False,
):
    """Download many wheels concurrently. Returns list of local paths."""
    if jobs < 2 or len(wheel_specs) < 2:
        return [
            download_wheel(
                spec,
                dest_dir,
                timeout=timeout,
                use_cache=use_cache,
                require_pypi_hash=require_pypi_hash,
            )
            for spec in wheel_specs
        ]

    paths = []
    errors = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {
            pool.submit(
                download_wheel,
                spec,
                dest_dir,
                timeout,
                use_cache,
                require_pypi_hash,
            ): spec
            for spec in wheel_specs
        }
        for future in as_completed(futures):
            spec = futures[future]
            try:
                paths.append(future.result())
            except FetchError as exc:
                errors.append("{}: {}".format(spec.get("filename"), exc))
    if errors:
        raise FetchError("Wheel download failures:\n" + "\n".join(errors))
    return paths


def fetch_ftp(url, dest_path, timeout=120):
    """Download a file via FTP. url format: ftp://host/path/to/file"""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or 21
    remote_path = parsed.path
    ftp = ftplib.FTP()
    ftp.connect(host, port, timeout=timeout)
    if parsed.username:
        ftp.login(parsed.username, parsed.password or "")
    else:
        ftp.login()
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with open(dest_path, "wb") as out:
        ftp.retrbinary("RETR " + remote_path, out.write)
    ftp.quit()
    return dest_path


def fetch_git(url, dest_dir, ref=None, subpath=None, timeout=300):
    """Clone or archive from a git repository.

    url: git URL or git+https://... style
    Returns path to fetched content directory or file.
    """
    from urllib.parse import urlparse

    raw = url
    if raw.startswith("git+"):
        raw = raw[4:]
    if raw.startswith("git://"):
        raw = "https://" + raw[6:]

    parsed = urlparse(raw)
    repo_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if repo_url.endswith(".git"):
        pass
    elif parsed.path and not parsed.path.endswith("/"):
        repo_url = repo_url + ".git"

    tmp_parent = tempfile.mkdtemp(prefix="opip-git-")
    clone_dir = os.path.join(tmp_parent, "repo")

    cmd = ["git", "clone", "--depth", "1"]
    if ref:
        cmd.extend(["--branch", ref])
    cmd.extend([repo_url, clone_dir])

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        shutil.rmtree(tmp_parent, ignore_errors=True)
        raise FetchError(
            "git is not installed. Install git or download the bundle manually.",
        )
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(tmp_parent, ignore_errors=True)
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        raise FetchError(f"git clone failed: {stderr.strip()}")

    if subpath:
        try:
            target = contain_path(clone_dir, subpath)
        except ValueError as exc:
            shutil.rmtree(tmp_parent, ignore_errors=True)
            raise FetchError(str(exc))
    else:
        target = clone_dir

    if not os.path.exists(target):
        shutil.rmtree(tmp_parent, ignore_errors=True)
        raise FetchError(f"Path not found in repository: {subpath}")

    return target, tmp_parent


def fetch_file(source, dest_path, timeout=120):
    """Fetch a file from http, https, ftp, or local path.

    Returns dest_path.
    """
    if source.startswith("ftp://"):
        return fetch_ftp(source, dest_path, timeout=timeout)

    if source.startswith(("http://", "https://")):
        return download_url(source, dest_path, timeout=timeout)

    if os.path.isfile(source):
        shutil.copy2(source, dest_path)
        return dest_path

    raise FetchError(f"Unsupported or missing source: {source}")
