"""Export / mirror rngit release artifacts for sneakernet."""

from __future__ import annotations

import shutil
from pathlib import Path

from .releases import (
    _normalize_remote,
    _parse_rns_url,
    _pick_whl,
    _rsg_name_for_artifact,
    fetch_release_artifact,
    release_has_signatures,
    release_info,
)
from .trust import resolve_verify_identity
from .ui import bold, dim, green, header, success


def export_release(
    remote: str,
    output: str,
    *,
    ref: str | None = None,
    verify_identity: str | None = None,
    insecure: bool = False,
    config_dir: str | None = None,
    all_artifacts: bool = False,
) -> list[str]:
    """
    Download release artifacts into output directory for offline sharing.

    Returns list of written file paths.
    """
    remote = _normalize_remote(remote)
    _, group, repo = _parse_rns_url(remote)
    tag = ref or "latest"
    out = Path(output).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    signer = resolve_verify_identity(
        remote,
        explicit=verify_identity,
        insecure=insecure,
        config_dir=config_dir,
    )

    print(f"{header('⤵ Export')} {bold(tag)} {dim(f'{group}/{repo}')}")
    info = release_info(remote, tag)
    artifacts = info.get("artifacts", [])
    if not artifacts:
        raise RuntimeError(f"Release {tag}: no artifacts found")

    if all_artifacts:
        names = [a["name"] for a in artifacts if not a["name"].endswith(".rsm")]
    else:
        whl = _pick_whl(artifacts)
        if not whl:
            raise RuntimeError(f"Release {tag}: no .whl found")
        names = [whl]
        rsg = _rsg_name_for_artifact(whl)
        if any(a["name"] == rsg for a in artifacts):
            names.append(rsg)

    written: list[str] = []
    for name in names:
        print(f"  {dim('fetch:')} {name}")
        fetched = fetch_release_artifact(remote, tag, name, verify_identity=signer)
        dest = out / Path(fetched.path).name
        if dest.exists():
            dest.unlink()
        shutil.move(fetched.path, str(dest))
        written.append(str(dest))
        if fetched.verified or release_has_signatures(artifacts):
            who = signer or fetched.signer or "release .rsm/.rsg"
            print(f"  {green('signature valid')} {dim(who)}")

    print(f"{success('✓ Exported')} {len(written)} file(s) → {out}")
    return written
