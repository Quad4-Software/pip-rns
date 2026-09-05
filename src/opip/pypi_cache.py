# Copyright (c) 2026, Quad4 (quad4.io)
"""Disk cache for PyPI JSON metadata."""

import hashlib
import json
import os
import time

from opip.storage import default_cache_dir

CACHE_TTL = 86400


def _cache_dir():
    path = os.path.join(default_cache_dir(), "pypi")
    os.makedirs(path, exist_ok=True)
    return path


def _cache_path(key):
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return os.path.join(_cache_dir(), digest + ".json")


def get(key):
    path = _cache_path(key)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        if time.time() - payload.get("fetched", 0) > CACHE_TTL:
            return None
        return payload.get("data")
    except (OSError, ValueError, TypeError):
        return None


def put(key, data):
    path = _cache_path(key)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"fetched": time.time(), "data": data}, fh)
