#!/usr/bin/env python3
# Copyright (c) 2026, Quad4 (quad4.io)
"""Bootstrap opip.pyz / pip-rns.pyz without pip or a prior install.

Stdlib only. Typical uses:

  # You already downloaded pip_rns-*.whl from PyPI/GitHub (browser + Tor):
  python3 get-opip.py --from-wheel pip_rns-1.5.0-py3-none-any.whl -o .

  # Copy from a USB that already has dist/*.pyz:
  python3 get-opip.py --from-dir /media/usb/dist -o .

  # Download release zipapps (optional Tor):
  python3 get-opip.py --proxy socks5h://127.0.0.1:9050 -o .

Then:
  python3 opip.pyz kit create nomadnet -o /media/usb \\
    --find-links ./wheels --offline --with-runtime --as-app
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import socket
import ssl
import struct
import sys
import tempfile
import zipapp
import zipfile
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse

# Default release assets (override with --url / OPIP_BOOTSTRAP_URL).
DEFAULT_OPIP_URL = os.environ.get(
    "OPIP_BOOTSTRAP_URL",
    "https://github.com/Quad4-Software/pip-rns/releases/latest/download/opip.pyz",
)
DEFAULT_PIP_RNS_URL = os.environ.get(
    "PIP_RNS_BOOTSTRAP_URL",
    "https://github.com/Quad4-Software/pip-rns/releases/latest/download/pip-rns.pyz",
)


class BootstrapError(Exception):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _socks5_connect(
    proxy_host: str,
    proxy_port: int,
    dest_host: str,
    dest_port: int,
    *,
    resolve_remote: bool,
    timeout: float | None = None,
) -> socket.socket:
    sock = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
    try:
        sock.sendall(b"\x05\x01\x00")
        resp = sock.recv(2)
        if len(resp) < 2 or resp[0] != 0x05 or resp[1] != 0x00:
            raise BootstrapError("SOCKS5 greeting failed")
        if resolve_remote:
            host_b = dest_host.encode("idna")
            req = (
                bytes([0x05, 0x01, 0x00, 0x03, len(host_b)])
                + host_b
                + struct.pack("!H", dest_port)
            )
        else:
            addr = socket.inet_aton(socket.gethostbyname(dest_host))
            req = bytes([0x05, 0x01, 0x00, 0x01]) + addr + struct.pack("!H", dest_port)
        sock.sendall(req)
        hdr = sock.recv(4)
        if len(hdr) < 4 or hdr[1] != 0x00:
            raise BootstrapError("SOCKS5 connect failed")
        atyp = hdr[3]
        if atyp == 0x01:
            sock.recv(6)
        elif atyp == 0x03:
            ln = sock.recv(1)[0]
            sock.recv(ln + 2)
        elif atyp == 0x04:
            sock.recv(18)
        return sock
    except Exception:
        sock.close()
        raise


def _build_opener(proxy: str | None):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_default_certs()
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = True
    if not proxy:
        return urllib_request.build_opener(urllib_request.HTTPSHandler(context=ctx))
    parsed = urlparse(proxy)
    scheme = (parsed.scheme or "").lower()
    if scheme in ("http", "https"):
        return urllib_request.build_opener(
            urllib_request.ProxyHandler({"http": proxy, "https": proxy}),
            urllib_request.HTTPSHandler(context=ctx),
        )
    if scheme not in ("socks5", "socks5h"):
        raise BootstrapError(f"Unsupported proxy scheme: {scheme}")
    resolve_remote = scheme == "socks5h"
    proxy_host = parsed.hostname or "127.0.0.1"
    proxy_port = parsed.port or 1080

    class SocksHTTPS(urllib_request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(self._conn, req)

        def _conn(self, host, **kwargs):
            from http.client import HTTPSConnection

            class Conn(HTTPSConnection):
                def connect(self):
                    sock = _socks5_connect(
                        proxy_host,
                        proxy_port,
                        self.host,
                        self.port,
                        resolve_remote=resolve_remote,
                        timeout=self.timeout,
                    )
                    self.sock = ctx.wrap_socket(sock, server_hostname=self.host)

            return Conn(host, **kwargs)

    return urllib_request.build_opener(SocksHTTPS(context=ctx))


def download(url: str, dest: Path, *, proxy: str | None, expected: str | None) -> Path:
    opener = _build_opener(proxy)
    req = urllib_request.Request(url, headers={"User-Agent": "get-opip/1.5"})
    try:
        with opener.open(req, timeout=120) as resp, open(dest, "wb") as out:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                out.write(chunk)
    except urllib_error.URLError as exc:
        raise BootstrapError(f"Download failed: {exc}") from exc
    if expected:
        got = _sha256(dest)
        if got != expected:
            dest.unlink(missing_ok=True)
            raise BootstrapError(f"Hash mismatch for {dest.name}")
    return dest


def build_from_wheel(wheel: Path, out_dir: Path) -> tuple[Path, Path]:
    """Extract pip-rns wheel and build both zipapps."""
    if not wheel.is_file():
        raise BootstrapError(f"Wheel not found: {wheel}")
    work = Path(tempfile.mkdtemp(prefix="get-opip-"))
    try:
        with zipfile.ZipFile(wheel, "r") as zf:
            zf.extractall(work)
        # Wheel may place packages at top level
        opip_pkg = work / "opip"
        pip_pkg = work / "pip_rns"
        if not opip_pkg.is_dir() or not pip_pkg.is_dir():
            raise BootstrapError(
                f"Wheel {wheel.name} does not contain opip/ and pip_rns/ packages",
            )
        stage = work / "stage"
        stage.mkdir()
        shutil.copytree(opip_pkg, stage / "opip")
        shutil.copytree(pip_pkg, stage / "pip_rns")
        out_dir.mkdir(parents=True, exist_ok=True)
        opip_pyz = out_dir / "opip.pyz"
        pip_rns_pyz = out_dir / "pip-rns.pyz"
        for path in (opip_pyz, pip_rns_pyz):
            if path.exists():
                path.unlink()
        zipapp.create_archive(
            stage,
            target=str(opip_pyz),
            interpreter="/usr/bin/env python3",
            main="opip.cli:main",
            compressed=True,
        )
        zipapp.create_archive(
            stage,
            target=str(pip_rns_pyz),
            interpreter="/usr/bin/env python3",
            main="pip_rns.cli:main",
            compressed=True,
        )
        return opip_pyz, pip_rns_pyz
    finally:
        shutil.rmtree(work, ignore_errors=True)


def copy_from_dir(src: Path, out_dir: Path) -> tuple[Path, Path]:
    opip_src = src / "opip.pyz"
    pip_src = src / "pip-rns.pyz"
    if not opip_src.is_file():
        raise BootstrapError(f"Missing {opip_src}")
    out_dir.mkdir(parents=True, exist_ok=True)
    opip_dst = out_dir / "opip.pyz"
    pip_dst = out_dir / "pip-rns.pyz"
    shutil.copy2(opip_src, opip_dst)
    if pip_src.is_file():
        shutil.copy2(pip_src, pip_dst)
    else:
        # Still usable with opip alone
        pip_dst = pip_src
    return opip_dst, pip_dst if pip_dst.is_file() else opip_dst


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", default=".", help="Directory for .pyz files")
    parser.add_argument(
        "--from-wheel",
        metavar="WHEEL",
        help="Build zipapps from a downloaded pip_rns-*.whl (no network)",
    )
    parser.add_argument(
        "--from-dir",
        metavar="DIR",
        help="Copy opip.pyz / pip-rns.pyz from an existing directory",
    )
    parser.add_argument("--url", default=None, help="Download opip.pyz from this URL")
    parser.add_argument(
        "--pip-rns-url",
        default=None,
        help="Also download pip-rns.pyz from this URL",
    )
    parser.add_argument(
        "--proxy",
        default=os.environ.get("OPIP_PROXY"),
        help="HTTP/HTTPS/SOCKS5(h) proxy (Tor: socks5h://127.0.0.1:9050)",
    )
    parser.add_argument("--sha256", default=None, help="Expected sha256 of opip.pyz")
    args = parser.parse_args(argv)
    out = Path(args.output).expanduser().resolve()

    try:
        if args.from_wheel:
            opip_pyz, pip_rns_pyz = build_from_wheel(
                Path(args.from_wheel).expanduser().resolve(),
                out,
            )
        elif args.from_dir:
            opip_pyz, pip_rns_pyz = copy_from_dir(
                Path(args.from_dir).expanduser().resolve(),
                out,
            )
        else:
            out.mkdir(parents=True, exist_ok=True)
            opip_url = args.url or DEFAULT_OPIP_URL
            opip_pyz = out / "opip.pyz"
            print(f"Downloading {opip_url}", file=sys.stderr)
            download(opip_url, opip_pyz, proxy=args.proxy, expected=args.sha256)
            pip_url = args.pip_rns_url or DEFAULT_PIP_RNS_URL
            pip_rns_pyz = out / "pip-rns.pyz"
            try:
                print(f"Downloading {pip_url}", file=sys.stderr)
                download(pip_url, pip_rns_pyz, proxy=args.proxy, expected=None)
            except BootstrapError as exc:
                print(f"warning: pip-rns.pyz skipped: {exc}", file=sys.stderr)
                pip_rns_pyz = opip_pyz

        print(f"ok {opip_pyz}")
        if pip_rns_pyz.is_file() and pip_rns_pyz != opip_pyz:
            print(f"ok {pip_rns_pyz}")
        print("Next: python3 opip.pyz help airgap", file=sys.stderr)
        return 0
    except BootstrapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    # Fix typo in zipapp interpreter if any - check build_from_wheel
    sys.exit(main())
