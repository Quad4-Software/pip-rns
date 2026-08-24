"""Wheel provenance records and PyPI digest validation."""

from opip.integrity import file_hash


class ProvenanceError(Exception):
    pass


def build_wheel_record(wheel_path, spec=None, source="pypi", built_from=None):
    """
    Build a manifest wheel entry with bundled hash and PyPI provenance.

    source: pypi, local, cache
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
        pypi_sha = digests.get("sha256")
        if pypi_sha:
            record["pypi_sha256"] = pypi_sha
        if spec.get("url"):
            record["pypi_url"] = spec["url"]
        if pypi_sha:
            if bundled != pypi_sha:
                raise ProvenanceError(
                    f"Wheel {filename} hash {bundled[:16]} does not match PyPI digest {pypi_sha[:16]}"
                )
            record["provenance_verified"] = True
        else:
            record["provenance_verified"] = False

    if source == "local":
        record["provenance_verified"] = False
        record["built_from"] = built_from
        if spec and spec.get("project_name"):
            record["project_name"] = spec["project_name"]

    if source == "cache" and spec:
        pypi_sha = (spec.get("digests") or {}).get("sha256")
        if pypi_sha and bundled == pypi_sha:
            record["provenance_verified"] = True

    return record


def verify_wheel_provenance(wheel_path, record, require_pypi_hash=False):
    """Verify a wheel file matches its manifest record."""
    errors = []
    actual = file_hash(wheel_path)
    expected = record.get("sha256")
    if actual != expected:
        errors.append("Bundled hash mismatch for {}".format(record.get("filename")))

    pypi_sha = record.get("pypi_sha256")
    source = record.get("source", "pypi")

    if source == "pypi" or source == "cache":
        if require_pypi_hash and not pypi_sha:
            errors.append("Missing PyPI digest for {}".format(record.get("package")))
        if pypi_sha and actual != pypi_sha:
            errors.append("PyPI digest mismatch for {}".format(record.get("package")))

    if source == "local" and record.get("provenance_verified"):
        errors.append(
            "Local wheel {} cannot have provenance_verified=true".format(
                record.get("filename")
            )
        )

    return errors
