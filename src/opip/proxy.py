# Copyright (c) 2026, Quad4 (quad4.io)
"""HTTP and SOCKS5(h) proxy support for opip downloads (stdlib only)."""

from __future__ import annotations

import os
import socket
import ssl
import struct
from urllib import request as urllib_request
from urllib.parse import urlparse

_PROXY_ENV = "OPIP_PROXY"
_active_proxy: str | None = None


class ProxyError(Exception):
    pass


def tls_context() -> ssl.SSLContext:
    """Default TLS context that rejects TLS 1.0 and 1.1."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLS_1_2
    ctx.load_default_certs()
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = True
    return ctx


def get_proxy(explicit: str | None = None) -> str | None:
    """Return active proxy URL from explicit arg, module state, or OPIP_PROXY."""
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()
    if _active_proxy:
        return _active_proxy
    env = os.environ.get(_PROXY_ENV)
    if env and env.strip():
        return env.strip()
    for key in (
        "ALL_PROXY",
        "all_proxy",
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
    ):
        val = os.environ.get(key)
        if val and val.strip():
            return val.strip()
    return None


def set_proxy(url: str | None) -> None:
    """Set process-wide proxy used by opip fetch/resolver when no per-call override."""
    global _active_proxy
    _active_proxy = url.strip() if url else None


def clear_proxy() -> None:
    """Clear the process-wide proxy set by set_proxy."""
    set_proxy(None)


def _socks5_connect(
    proxy_host: str,
    proxy_port: int,
    dest_host: str,
    dest_port: int,
    *,
    resolve_remote: bool,
    timeout: float | None = None,
    username: str | None = None,
    password: str | None = None,
) -> socket.socket:
    """Open a TCP connection to dest via a SOCKS5 proxy."""
    sock = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
    try:
        methods = [0x00]
        if username is not None:
            methods = [0x02, 0x00]
        sock.sendall(bytes([0x05, len(methods), *methods]))
        resp = sock.recv(2)
        if len(resp) < 2 or resp[0] != 0x05:
            raise ProxyError("Invalid SOCKS5 greeting response")
        method = resp[1]
        if method == 0xFF:
            raise ProxyError("SOCKS5 proxy rejected authentication methods")
        if method == 0x02:
            user_b = (username or "").encode("utf-8")
            pass_b = (password or "").encode("utf-8")
            if len(user_b) > 255 or len(pass_b) > 255:
                raise ProxyError("SOCKS5 username/password too long")
            sock.sendall(
                bytes([0x01, len(user_b)]) + user_b + bytes([len(pass_b)]) + pass_b,
            )
            auth = sock.recv(2)
            if len(auth) < 2 or auth[1] != 0x00:
                raise ProxyError("SOCKS5 authentication failed")

        if resolve_remote:
            host_b = dest_host.encode("idna")
            if len(host_b) > 255:
                raise ProxyError("Destination hostname too long for SOCKS5")
            req = (
                bytes([0x05, 0x01, 0x00, 0x03, len(host_b)])
                + host_b
                + struct.pack("!H", dest_port)
            )
        else:
            try:
                ip = socket.inet_aton(dest_host)
                atyp = 0x01
                addr = ip
            except OSError:
                ip6 = socket.inet_pton(socket.AF_INET6, dest_host)
                atyp = 0x04
                addr = ip6
            req = bytes([0x05, 0x01, 0x00, atyp]) + addr + struct.pack("!H", dest_port)

        sock.sendall(req)
        hdr = sock.recv(4)
        if len(hdr) < 4 or hdr[0] != 0x05:
            raise ProxyError("Invalid SOCKS5 connect response")
        if hdr[1] != 0x00:
            codes = {
                0x01: "general failure",
                0x02: "not allowed",
                0x03: "network unreachable",
                0x04: "host unreachable",
                0x05: "connection refused",
                0x06: "TTL expired",
                0x07: "command not supported",
                0x08: "address type not supported",
            }
            raise ProxyError(f"SOCKS5 connect failed: {codes.get(hdr[1], hdr[1])}")
        atyp = hdr[3]
        if atyp == 0x01:
            sock.recv(4 + 2)
        elif atyp == 0x03:
            ln = sock.recv(1)
            sock.recv(ln[0] + 2)
        elif atyp == 0x04:
            sock.recv(16 + 2)
        else:
            raise ProxyError(f"Unknown SOCKS5 address type: {atyp}")
        return sock
    except Exception:
        sock.close()
        raise


class _SocksHTTPSHandler(urllib_request.HTTPSHandler):
    def __init__(self, proxy_url: str, context=None):
        super().__init__(context=context)
        self._proxy = urlparse(proxy_url)
        if self._proxy.scheme not in ("socks5", "socks5h"):
            raise ProxyError(f"Unsupported SOCKS scheme: {self._proxy.scheme}")
        self._resolve_remote = self._proxy.scheme == "socks5h"

    def https_open(self, req):
        return self.do_open(self._https_connection, req)

    def _https_connection(self, host, **kwargs):
        from http.client import HTTPSConnection

        proxy_host = self._proxy.hostname
        proxy_port = self._proxy.port or 1080
        if not proxy_host:
            raise ProxyError("SOCKS proxy host missing")
        username = self._proxy.username
        password = self._proxy.password
        resolve_remote = self._resolve_remote
        context = self._context

        class Conn(HTTPSConnection):
            def connect(self):
                sock = _socks5_connect(
                    proxy_host,
                    proxy_port,
                    self.host,
                    self.port,
                    resolve_remote=resolve_remote,
                    timeout=self.timeout,
                    username=username,
                    password=password,
                )
                if context:
                    self.sock = context.wrap_socket(sock, server_hostname=self.host)
                else:
                    self.sock = tls_context().wrap_socket(
                        sock,
                        server_hostname=self.host,
                    )

        return Conn(host, **kwargs)


class _SocksHTTPHandler(urllib_request.HTTPHandler):
    def __init__(self, proxy_url: str):
        super().__init__()
        self._proxy = urlparse(proxy_url)
        self._resolve_remote = self._proxy.scheme == "socks5h"

    def http_open(self, req):
        return self.do_open(self._http_connection, req)

    def _http_connection(self, host, **kwargs):
        from http.client import HTTPConnection

        proxy_host = self._proxy.hostname
        proxy_port = self._proxy.port or 1080
        if not proxy_host:
            raise ProxyError("SOCKS proxy host missing")
        username = self._proxy.username
        password = self._proxy.password
        resolve_remote = self._resolve_remote

        class Conn(HTTPConnection):
            def connect(self):
                self.sock = _socks5_connect(
                    proxy_host,
                    proxy_port,
                    self.host,
                    self.port,
                    resolve_remote=resolve_remote,
                    timeout=self.timeout,
                    username=username,
                    password=password,
                )

        return Conn(host, **kwargs)


def build_opener(
    proxy: str | None = None,
    context: ssl.SSLContext | None = None,
) -> urllib_request.OpenerDirector:
    """Build a urllib opener honoring HTTP(S) or SOCKS5(h) proxies."""
    proxy_url = get_proxy(proxy)
    handlers: list[urllib_request.BaseHandler] = []
    if context is None:
        context = tls_context()
    handlers.append(urllib_request.HTTPSHandler(context=context))
    if not proxy_url:
        return urllib_request.build_opener(*handlers)

    parsed = urlparse(proxy_url)
    scheme = (parsed.scheme or "").lower()
    if scheme in ("socks5", "socks5h"):
        socks_handlers: list[urllib_request.BaseHandler] = [
            _SocksHTTPHandler(proxy_url),
            _SocksHTTPSHandler(proxy_url, context=context),
        ]
        return urllib_request.build_opener(*socks_handlers)

    if scheme in ("http", "https"):
        handlers.append(
            urllib_request.ProxyHandler(
                {
                    "http": proxy_url,
                    "https": proxy_url,
                },
            ),
        )
        return urllib_request.build_opener(*handlers)

    raise ProxyError(
        f"Unsupported proxy scheme {scheme!r}. "
        "Use http://, https://, socks5://, or socks5h://",
    )
