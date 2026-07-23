"""Tests for resolver.py - URL normalization, ref parsing, hashing."""

from __future__ import annotations

from pip_rns.resolver import normalize_url, parse_ref, repo_hash


def test_normalize_url_bare_path_adds_rns_scheme():
    result = normalize_url("abc123/group/myapp")
    assert result == "rns://abc123/group/myapp", result


def test_normalize_url_full_rns_passthrough():
    result = normalize_url("rns://abc/group/repo")
    assert result == "rns://abc/group/repo"


def test_normalize_url_local_absolute_passthrough():
    result = normalize_url("/home/user/project")
    assert result == "/home/user/project"


def test_normalize_url_local_relative_passthrough():
    result = normalize_url("./some/pkg")
    assert result == "./some/pkg"


def test_normalize_url_home_expanded():
    result = normalize_url("~/projects/foo")
    assert result == "~/projects/foo"


def test_normalize_url_strips_whitespace():
    result = normalize_url("  abc/def/ghi  ")
    assert result == "rns://abc/def/ghi"


def test_parse_ref_no_at():
    remote, ref = parse_ref("abc/def/ghi")
    assert remote == "abc/def/ghi"
    assert ref is None


def test_parse_ref_with_tag():
    remote, ref = parse_ref("abc/def/ghi@v1.0.0")
    assert remote == "abc/def/ghi"
    assert ref == "v1.0.0"


def test_parse_ref_with_branch():
    remote, ref = parse_ref("abc/def/ghi@main")
    assert remote == "abc/def/ghi"
    assert ref == "main"


def test_parse_ref_trailing_at():
    remote, ref = parse_ref("abc/def/ghi@")
    assert remote == "abc/def/ghi"
    assert ref is None


def test_parse_ref_at_in_path_not_ref_when_before_last_slash():
    remote, ref = parse_ref("rns://user@host.com/group/repo")
    assert remote == "rns://user@host.com/group/repo"
    assert ref is None


def test_repo_hash_consistent():
    h1 = repo_hash("rns://abc/def/ghi")
    h2 = repo_hash("rns://abc/def/ghi")
    assert h1 == h2
    assert len(h1) == 16


def test_repo_hash_different_urls_differ():
    h1 = repo_hash("rns://abc/def/ghi")
    h2 = repo_hash("rns://xyz/def/ghi")
    assert h1 != h2


def test_rns_source_defaults_to_cache_and_updates():
    from unittest import mock

    from pip_rns.resolver import Resolver, CACHE_DIR, repo_hash

    url = "rns://aabb/g/repo"
    dest = CACHE_DIR / repo_hash(f"{url}@master")
    fake = mock.Mock()
    with mock.patch("pip_rns.resolver.get_resolver", return_value=fake):
        with mock.patch(
            "pip_rns.resolver._ensure_clone", return_value="updated"
        ) as ensure:
            path = Resolver().resolve(url, ref="master")
    assert path == dest
    assert ensure.called
    assert ensure.call_args.kwargs.get("update_existing") is True


def test_ensure_clone_updates_existing_git_checkout():
    from unittest import mock
    from pathlib import Path
    import tempfile

    from pip_rns.resolver import _ensure_clone

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "repo"
        dest.mkdir()
        (dest / ".git").mkdir()
        fake = mock.Mock()
        status = _ensure_clone(
            fake, "rns://id/g/r", dest, ref="master", update_existing=True
        )
        assert status == "updated"
        fake.update.assert_called_once()
        fake.clone.assert_not_called()


def test_ensure_clone_cleans_partial_on_interrupt():
    from unittest import mock
    from pathlib import Path
    import tempfile

    from pip_rns.resolver import _ensure_clone

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "repo"
        fake = mock.Mock()

        def boom(*_a, **_k):
            dest.mkdir(parents=True, exist_ok=True)
            raise KeyboardInterrupt()

        fake.clone.side_effect = boom
        try:
            _ensure_clone(
                fake, "rns://id/g/r", dest, ref="master", update_existing=True
            )
            assert False, "expected KeyboardInterrupt"
        except KeyboardInterrupt:
            pass
        assert not dest.exists()
