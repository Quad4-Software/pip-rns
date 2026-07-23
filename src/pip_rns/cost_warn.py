"""Warn before expensive Reticulum source clones."""

from __future__ import annotations

from opip.interactive import is_noninteractive

from .errors import UserCancelled
from .ui import bold, dim, yellow


def confirm_expensive_rns_clone(
    remote: str,
    *,
    no_interactive: bool = False,
    assume_yes: bool = False,
) -> None:
    """
    Interactive warning before a full RNS source clone.

    Skipped when non-interactive or assume_yes. Raises UserCancelled on no.
    """
    if assume_yes or is_noninteractive(no_interactive):
        return
    if not remote.startswith("rns://") and "://" in remote:
        return
    # Only warn for RNS-style remotes (rns:// or identity/group/repo)
    is_rns = remote.startswith("rns://") or (
        "/" in remote and "://" not in remote and not remote.startswith(("/", ".", "~"))
    )
    if not is_rns:
        return

    print(
        f"\n{yellow('RNS source clone is expensive')} "
        f"(slow link, large transfer).\n"
        f"  Prefer a release wheel when available "
        f"({bold('--from-release')}), or "
        f"{bold('pip-rns export')} + sneakernet.\n"
        f"  Remote: {dim(remote)}"
    )
    try:
        answer = input("Continue with source clone? [y/N]: ").strip().lower()
    except EOFError as exc:
        raise UserCancelled("Cancelled.") from exc
    except KeyboardInterrupt as exc:
        raise UserCancelled("Interrupted.") from exc
    if answer not in ("y", "yes"):
        raise UserCancelled("Aborted expensive RNS clone.")
