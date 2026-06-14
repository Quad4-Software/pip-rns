"""Download wheels and files from remote sources (stdlib only)."""

import ftplib
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from opip.integrity import file_hash
from opip.wheel_cache import lookup_wheel, store_wheel

USER_AGENT = "opip/{0} (+https://github.com/Quad4-Software/pip-rns)".format(
    __import__("opip").__version__
)
CHUNK_SIZE = 65536


class FetchError(Exception):
    pass


def _build_opener():
    ctx = ssl.create_default_context()
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx)
    )


def download_url(url, dest_path, timeout=120, expected_hash=None):
    """Download URL to dest_path. Optionally verify SHA-256."""
    opener = _build_opener()
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
        raise FetchError("Download failed for {0}: {1}".format(url, exc))

    if expected_hash:
        actual = file_hash(dest_path)
        if actual != expected_hash:
            os.remove(dest_path)
            raise FetchError(
                "Hash mismatch for {0}: expected {1}, got {2}".format(
                    url, expected_hash[:16], actual[:16]
                )
            )
    return dest_path


def download_wheel(wheel_spec, dest_dir, timeout=120, use_cache=True, require_pypi_hash=False):
    """Download a wheel from resolver spec into dest_dir."""
    url = wheel_spec["url"]
    filename = wheel_spec["filename"]
    dest = os.path.join(dest_dir, filename)
    expected = None
    digests = wheel_spec.get("digests") or {}
    if "sha256" in digests:
        expected = digests["sha256"]
    elif require_pypi_hash:
        raise FetchError(
            "PyPI provides no sha256 digest for {0}; use without --require-pypi-hash".format(
                filename
            )
        )

    if use_cache:
        cached = lookup_wheel(filename, expected)
        if cached:
            if expected and file_hash(cached) != expected:
                os.remove(cached)
            else:
                shutil.copy2(cached, dest)
                return dest

    download_url(url, dest, timeout=timeout, expected_hash=expected)
    if use_cache:
        store_wheel(dest, filename=filename, expected_hash=expected)
    return dest


def download_wheels_parallel(
    wheel_specs, dest_dir, jobs=8, timeout=120, use_cache=True, require_pypi_hash=False
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
                errors.append("{0}: {1}".format(spec.get("filename"), exc))
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
    """
    Clone or archive from a git repository.

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
    repo_url = "{0}://{1}{2}".format(parsed.scheme, parsed.netloc, parsed.path)
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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except FileNotFoundError:
        shutil.rmtree(tmp_parent, ignore_errors=True)
        raise FetchError(
            "git is not installed. Install git or download the bundle manually."
        )
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(tmp_parent, ignore_errors=True)
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        raise FetchError("git clone failed: {0}".format(stderr.strip()))

    if subpath:
        target = os.path.join(clone_dir, subpath.replace("/", os.sep))
    else:
        target = clone_dir

    if not os.path.exists(target):
        shutil.rmtree(tmp_parent, ignore_errors=True)
        raise FetchError("Path not found in repository: {0}".format(subpath))

    return target, tmp_parent


def fetch_file(source, dest_path, timeout=120):
    """
    Fetch a file from http, https, ftp, or local path.

    Returns dest_path.
    """
    if source.startswith("ftp://"):
        return fetch_ftp(source, dest_path, timeout=timeout)

    if source.startswith(("http://", "https://")):
        return download_url(source, dest_path, timeout=timeout)

    if os.path.isfile(source):
        shutil.copy2(source, dest_path)
        return dest_path

    raise FetchError("Unsupported or missing source: {0}".format(source))
