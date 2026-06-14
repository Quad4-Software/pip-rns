"""Resolve pip-rns aliases and indexes for opip remote sources."""

import os


def resolve_remote_source(source):
    """
    Apply pip-rns alias and index resolution to a remote string.

    Preserves @ref and :artifact suffixes on the source.
    """
    last_slash = source.rfind("/")
    last_at = source.rfind("@")
    suffix = ""
    base = source
    if last_at > last_slash:
        suffix = source[last_at:]
        base = source[:last_at]

    try:
        from pip_rns.aliases import get_manager as get_alias_mgr
        from pip_rns.aliases import init as alias_init
        from pip_rns.indexes import get_manager as get_index_mgr
        from pip_rns.indexes import init as index_init

        config = os.environ.get("PIP_RNS_CONFIG")
        alias_init(config)
        index_init()
        amgr = get_alias_mgr()
        if amgr:
            base = amgr.resolve(base)
        imgr = get_index_mgr()
        if imgr:
            base = imgr.resolve(base)
    except ImportError:
        pass

    return base + suffix
