# Copyright (c) 2026, Quad4 (quad4.io)
"""Verify bundle integrity, authenticity, and provenance."""

from opip.bundle import verify_bundle


def verify_bundle_file(
    bundle_path,
    signer=None,
    require_signature=False,
    require_pypi_hash=False,
):
    """Verify a bundle file. Returns (ok, errors, manifest)."""
    errors, manifest = verify_bundle(
        bundle_path,
        signer=signer,
        require_signature=require_signature,
        require_pypi_hash=require_pypi_hash,
    )
    return len(errors) == 0, errors, manifest
