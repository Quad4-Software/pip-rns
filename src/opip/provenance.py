# Copyright (c) 2026, Quad4 (quad4.io)
"""Wheel provenance records and PyPI digest validation."""

from opip.integrity import file_hash


class ProvenanceError(Exception):
    pass


def build_wheel_record(wheel_path, spec=None, source="pypi", built_from=None):
    """Build a manifest wheel entry with bundled hash and source provenance.

    source: pypi, local, cache, find-links
    """
    from opip.wheel import read_wheel_metadata

    filename = __import__("os").path.basename(wheel_path)
    if spec and spec.get("filename"):
        filename = spec["filename"]
    meta = read_wheel_metadata(wheel_path)
    bundled = file_hash(wheel_path)

    record = {
        "filename": filename,
        "package": meta["name"],
        "version": meta["version"],
        "sha256": bundled,
        "source": source,
    }

    if spec:
        digests = spec.get("digests") or {}
        source_sha = digests.get("sha256")
        if source_sha:
            record["source_sha256"] = source_sha
            record["pypi_sha256"] = source_sha
        if spec.get("url"):
            record["source_url"] = spec["url"]
            record["pypi_url"] = spec["url"]
        if source_sha:
            if bundled != source_sha:
                raise ProvenanceError(
                    f"Wheel {filename} hash {bundled[:16]} does not match "
                    f"source digest {source_sha[:16]}",
                )
            record["provenance_verified"] = True
        else:
            record["provenance_verified"] = False

    if source == "local":
        record["provenance_verified"] = False
        record["built_from"] = built_from
        if spec and spec.get("project_name"):
            record["project_name"] = spec["project_name"]

    if source in ("cache", "find-links") and spec:
        source_sha = (spec.get("digests") or {}).get("sha256")
        if source_sha and bundled == source_sha:
            record["provenance_verified"] = True

    return record


def verify_wheel_provenance(wheel_path, record, require_pypi_hash=False):
    """Verify a wheel file matches its manifest record."""
    errors = []
    actual = file_hash(wheel_path)
    expected = record.get("sha256")
    if actual != expected:
        errors.append("Bundled hash mismatch for {}".format(record.get("filename")))

    source_sha = record.get("source_sha256") or record.get("pypi_sha256")
    source = record.get("source", "pypi")

    if source in ("pypi", "cache", "find-links"):
        if require_pypi_hash and not source_sha:
            errors.append("Missing source digest for {}".format(record.get("package")))
        if source_sha and actual != source_sha:
            errors.append("Source digest mismatch for {}".format(record.get("package")))

    if source == "local" and record.get("provenance_verified"):
        errors.append(
            "Local wheel {} cannot have provenance_verified=true".format(
                record.get("filename"),
            ),
        )

    return errors
