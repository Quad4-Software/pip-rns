"""Offline mode and fail-closed signature tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

from pip_rns.core import install_from_release
from pip_rns.releases import ArtifactFetch
from pip_rns.resolver import OfflineError, Resolver


def test_resolver_offline_miss_raises():
    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch("pip_rns.resolver.CACHE_DIR", Path(tmp) / "cache"):
            with mock.patch("pip_rns.resolver.PERSISTENT_DIR", Path(tmp) / "edit"):
                r = Resolver()
                try:
                    r.resolve(
                        "rns://aabbccddeeff00112233445566778899/g/repo",
                        offline=True,
                    )
                    raise AssertionError("expected OfflineError")
                except OfflineError as exc:
                    assert "Offline" in str(exc)


def test_resolver_offline_hit_uses_cache():
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "cache"
        url = "rns://aabbccddeeff00112233445566778899/g/repo"
        from pip_rns.resolver import repo_hash

        dest = cache / repo_hash(url)
        dest.mkdir(parents=True)
        (dest / ".git").mkdir()
        with mock.patch("pip_rns.resolver.CACHE_DIR", cache):
            r = Resolver()
            path = r.resolve(url, offline=True)
            assert path == dest
            assert r.last_status == "cached"


def test_fail_closed_signed_unverified():
    artifacts = [
        {"name": "pkg-1.0-py3-none-any.whl", "size": "1 KB"},
        {"name": "pkg-1.0-py3-none-any.whl.rsg", "size": "1 KB"},
    ]
    whl = Path(tempfile.mkdtemp()) / "pkg-1.0-py3-none-any.whl"
    whl.write_bytes(b"wheel")
    fetched = ArtifactFetch(path=str(whl), signer=None, verified=False)

    with mock.patch(
        "pip_rns.releases.release_info",
        return_value={"tag": "v1", "artifacts": artifacts},
    ):
        with mock.patch(
            "pip_rns.releases.fetch_release_artifact", return_value=fetched
        ):
            try:
                install_from_release(
                    "rns://aabbccddeeff00112233445566778899/g/repo",
                    ref="v1",
                    require_wheel=True,
                    no_interactive=True,
                )
                raise AssertionError("expected fail-closed RuntimeError")
            except RuntimeError as exc:
                assert "fail closed" in str(exc).lower() or "Refuse" in str(exc)


def test_insecure_allows_unverified_signed():
    artifacts = [
        {"name": "pkg-1.0-py3-none-any.whl", "size": "1 KB"},
        {"name": "pkg-1.0-py3-none-any.whl.rsg", "size": "1 KB"},
    ]
    whl = Path(tempfile.mkdtemp()) / "pkg-1.0-py3-none-any.whl"
    whl.write_bytes(b"wheel")
    fetched = ArtifactFetch(path=str(whl), signer=None, verified=False)

    class FakeInst:
        def install(self, *a, **k):
            return None

    with mock.patch(
        "pip_rns.releases.release_info",
        return_value={"tag": "v1", "artifacts": artifacts},
    ):
        with mock.patch(
            "pip_rns.releases.fetch_release_artifact", return_value=fetched
        ):
            with mock.patch("pip_rns.core.get_installer", return_value=FakeInst()):
                with mock.patch(
                    "pip_rns.core._install_package",
                    return_value=(FakeInst(), None),
                ):
                    install_from_release(
                        "rns://aabbccddeeff00112233445566778899/g/repo",
                        ref="v1",
                        require_wheel=True,
                        insecure=True,
                        no_interactive=True,
                    )
