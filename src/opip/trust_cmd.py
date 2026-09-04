"""Shared pip-rns trust store access for opip."""

from __future__ import annotations

import json
import zipfile

from opip.publisher_meta import PUBLISHER_FILE


def _trust_store(config_dir=None):
    from pip_rns.trust import TrustStore

    return TrustStore(config_dir)


def resolve_signer(
    source,
    *,
    explicit=None,
    insecure=False,
    config_dir=None,
):
    """Resolve signer pin for verify/install.

    Priority: explicit --signer / OPIP_SIGNER, then per-remote trust,
    then publisher identity key in trust remotes, then default.
    """
    if insecure:
        return None
    if explicit:
        return explicit.strip()

    from pip_rns.trust import TrustStore

    store = TrustStore(config_dir)
    remote_key = _remote_trust_key(source)
    if remote_key:
        pinned = store.get_remote(remote_key)
        if pinned:
            return pinned

    publisher_id = _publisher_identity_from_source(source)
    if publisher_id:
        by_identity = store.get_remote(publisher_id)
        if by_identity:
            return by_identity
        # Allow trust add <identity> <identity> style pins via remotes map
        for name, identity in store.list_all():
            if name != "default" and identity == publisher_id:
                return identity

    return store.get_default()


def _remote_trust_key(source):
    if not source:
        return None
    text = str(source).strip()
    if text.startswith("rns://"):
        try:
            from pip_rns.releases import _normalize_remote

            # Strip @ref and :artifact for trust lookup
            base = text.split("@", 1)[0].split(":", 2)
            if len(base) >= 2 and base[0] == "rns":
                # rns://id/group/repo:artifact -> use path without artifact
                path = text
                if "@" in path:
                    path = path.split("@", 1)[0]
                # artifact after last colon only when not the scheme
                if path.count(":") > 1:
                    scheme, rest = path.split("://", 1)
                    if ":" in rest:
                        # identity/group/repo:file.opip
                        rest = rest.rsplit(":", 1)[0]
                        path = f"{scheme}://{rest}"
                return _normalize_remote(path)
        except Exception:
            return text.split("@", 1)[0]
    return None


def _publisher_identity_from_source(source):
    path = str(source or "")
    if not path.endswith(".opip") and not path.endswith(".OPIP"):
        return None
    try:
        with zipfile.ZipFile(path, "r") as zf:
            if PUBLISHER_FILE not in zf.namelist():
                return None
            data = json.loads(zf.read(PUBLISHER_FILE).decode("utf-8"))
    except Exception:
        return None
    identity = data.get("identity")
    if identity:
        return str(identity).strip()
    trust = data.get("trust") or {}
    identity = trust.get("identity")
    return str(identity).strip() if identity else None


def dispatch_trust(args, write_out, success, warn, error):
    """Handle opip trust subcommands. Returns exit code."""
    config_dir = getattr(args, "config", None) or None
    store = _trust_store(config_dir)
    cmd = getattr(args, "trust_command", None)

    if cmd == "ls":
        rows = store.list_all()
        if getattr(args, "json", False):
            write_out(
                json.dumps(
                    [{"name": n, "identity": i} for n, i in rows],
                    indent=2,
                    sort_keys=True,
                ),
            )
            return 0
        if not rows:
            write_out("No trusted publishers.")
            return 0
        for name, identity in rows:
            write_out(f"{name}\t{identity}")
        return 0

    if cmd == "add":
        target = args.remote_or_default
        identity = args.identity
        if target == "default":
            store.set_default(identity)
            success(f"default signer -> {identity}")
        else:
            key = target
            if target.startswith("rns://"):
                try:
                    from pip_rns.releases import _normalize_remote

                    key = _normalize_remote(target)
                except Exception:
                    key = target
            store.set_remote(key, identity)
            success(f"trusted {key} -> {identity}")
        return 0

    if cmd == "rm":
        target = args.remote_or_default
        if target == "default":
            ok = store.forget_default()
        else:
            key = target
            if target.startswith("rns://"):
                try:
                    from pip_rns.releases import _normalize_remote

                    key = _normalize_remote(target)
                except Exception:
                    key = target
            else:
                key = target
            ok = store.forget_remote(key)
        if ok:
            success(f"forgot {target}")
        else:
            warn(f"No trust entry for {target}")
        return 0

    if cmd == "set-default":
        store.set_default(args.identity)
        success(f"default signer -> {args.identity}")
        return 0

    if cmd == "forget-default":
        if store.forget_default():
            success("forgot default signer")
        else:
            warn("No default signer set")
        return 0

    error("Usage: opip trust add|rm|ls|set-default|forget-default")
    return 2
