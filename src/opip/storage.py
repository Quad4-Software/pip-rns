"""Local storage for bundle registry, install records, and preferred destinations."""

import json
import os
import sys


def default_data_dir():
    """Return platform-appropriate data directory for opip state."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "opip")
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    return os.path.join(base, "opip")


def default_cache_dir():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "opip", "cache")
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache"
    )
    return os.path.join(base, "opip")


class Store:
    """Persistent JSON-backed registry for bundles, installs, and dest prefs."""

    def __init__(self, data_dir=None):
        self.data_dir = data_dir or default_data_dir()
        self.bundles_path = os.path.join(self.data_dir, "bundles.json")
        self.installs_path = os.path.join(self.data_dir, "installs.json")
        self.prefs_path = os.path.join(self.data_dir, "prefs.json")
        os.makedirs(self.data_dir, exist_ok=True)
        self._bundles = self._load(self.bundles_path, {"bundles": []})
        self._installs = self._load(self.installs_path, {"installs": []})
        self._prefs = self._load(self.prefs_path, {"destinations": {}})

    def _load(self, path, default):
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        return default

    def _save(self, path, data):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")

    def save(self):
        self._save(self.bundles_path, self._bundles)
        self._save(self.installs_path, self._installs)
        self._save(self.prefs_path, self._prefs)

    def register_bundle(self, name, path, manifest):
        entry = {
            "name": name,
            "path": os.path.abspath(path),
            "manifest_name": manifest.get("name"),
            "wheel_count": len(manifest.get("wheels", [])),
            "python_version": manifest.get("python_version"),
            "platform": manifest.get("platform"),
            "created": manifest.get("created"),
        }
        self._bundles["bundles"] = [
            b for b in self._bundles["bundles"] if b["name"] != name
        ]
        self._bundles["bundles"].append(entry)
        self.save()

    def list_bundles(self):
        return list(self._bundles.get("bundles", []))

    def get_bundle(self, name):
        for b in self._bundles.get("bundles", []):
            if b["name"] == name:
                return b
        return None

    def remove_bundle(self, name):
        self._bundles["bundles"] = [
            b for b in self._bundles["bundles"] if b["name"] != name
        ]
        self.save()

    def record_install(self, bundle_name, packages, target=None, bundle_path=None):
        entry = {
            "bundle": bundle_name,
            "packages": packages,
            "target": target,
            "bundle_path": os.path.abspath(bundle_path) if bundle_path else None,
        }
        self._installs["installs"] = [
            i for i in self._installs["installs"] if i["bundle"] != bundle_name
        ]
        self._installs["installs"].append(entry)
        self.save()

    def get_install(self, bundle_name):
        for i in self._installs.get("installs", []):
            if i["bundle"] == bundle_name:
                return i
        return None

    def list_installs(self):
        return list(self._installs.get("installs", []))

    def remove_install(self, bundle_name):
        self._installs["installs"] = [
            i for i in self._installs["installs"] if i["bundle"] != bundle_name
        ]
        self.save()

    def get_preferred_target(self, name):
        dests = self._prefs.get("destinations") or {}
        path = dests.get(name)
        return path if path else None

    def set_preferred_target(self, name, path):
        if "destinations" not in self._prefs or not isinstance(
            self._prefs["destinations"], dict
        ):
            self._prefs["destinations"] = {}
        self._prefs["destinations"][name] = os.path.abspath(path)
        self.save()

    def forget_preferred_target(self, name):
        dests = self._prefs.get("destinations") or {}
        if name in dests:
            del dests[name]
            self._prefs["destinations"] = dests
            self.save()
            return True
        return False

    def list_preferred_targets(self):
        dests = self._prefs.get("destinations") or {}
        return sorted(dests.items())
