"""Interactive install mode chooser for bare remotes."""

from __future__ import annotations

from typing import NamedTuple

from opip.interactive import is_noninteractive

from .errors import UserCancelled
from .ui import bold, dim, yellow


class InstallChoice(NamedTuple):
    from_source: bool = False
    from_release: bool = False
    ref: str | None = None
    abort: bool = False


def _read_line(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError as exc:
        raise UserCancelled("Cancelled.") from exc
    except KeyboardInterrupt as exc:
        raise UserCancelled("Interrupted.") from exc


def _pick_release_tag(remote: str) -> str | None:
    from .releases import list_releases

    try:
        releases = list_releases(remote)
    except Exception as exc:
        print(f"  {dim(f'could not list releases: {exc}')}")
        return None
    published = [r for r in releases if r.get("status") == "published"] or list(
        releases,
    )
    if not published:
        print(f"  {dim('no releases found')}")
        return None
    print("Releases:")
    for i, rel in enumerate(published[:20], start=1):
        tag = rel.get("tag", "?")
        status = rel.get("status", "")
        print(f"  {i}) {tag}  {dim(status)}")
    raw = _read_line("Pick release number (or tag): ")
    if not raw:
        return None
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(published[:20]):
            return published[idx].get("tag")
        return None
    return raw


def offer_install_options(
    remote: str,
    *,
    no_interactive: bool = False,
) -> InstallChoice | None:
    """Prompt how to install a bare remote (no @ref / mode flags).

    Returns InstallChoice, or None to keep the default auto behavior
    (prefer release wheel, else clone).
    """
    if is_noninteractive(no_interactive):
        return None

    print(f"\n{yellow('No version/branch specified for')} {bold(remote)}")
    print("How do you want to install?")
    print("  1) Latest release wheel (default, preferred)")
    print("  2) Clone master (expensive on RNS)")
    print("  3) Clone main (expensive on RNS)")
    print("  4) Clone default branch (expensive on RNS)")
    print("  5) Pick a signed release tag")
    print("  6) Abort")
    choice = _read_line("Choice [1/2/3/4/5/6]: ") or "1"

    if choice == "1":
        return InstallChoice(from_release=False, from_source=False, ref=None)
    if choice == "2":
        return InstallChoice(from_source=True, ref="master")
    if choice == "3":
        return InstallChoice(from_source=True, ref="main")
    if choice == "4":
        return InstallChoice(from_source=True, ref=None)
    if choice == "5":
        tag = _pick_release_tag(remote)
        if not tag:
            raise UserCancelled("No release selected.")
        return InstallChoice(from_release=True, ref=tag)
    raise UserCancelled("Aborted.")
