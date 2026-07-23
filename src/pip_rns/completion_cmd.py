"""Install shell completion scripts into user directories."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


COMPLETION_FILES = {
    "bash": ("completions/pip-rns.bash", "pip-rns"),
    "zsh": ("completions/_pip-rns", "_pip-rns"),
    "fish": ("completions/pip-rns.fish", "pip-rns.fish"),
}


def detect_shell(explicit: str | None = None) -> str:
    if explicit:
        return explicit.strip().lower()
    shell = os.environ.get("SHELL", "")
    base = os.path.basename(shell).lower()
    if "zsh" in base:
        return "zsh"
    if "fish" in base:
        return "fish"
    return "bash"


def _dest_dir(shell: str) -> Path:
    home = Path.home()
    if shell == "bash":
        return home / ".local" / "share" / "bash-completion" / "completions"
    if shell == "zsh":
        return home / ".local" / "share" / "zsh" / "site-functions"
    if shell == "fish":
        return home / ".local" / "share" / "fish" / "vendor_completions.d"
    raise ValueError("Unsupported shell: {0} (use bash, zsh, or fish)".format(shell))


def _find_source(rel: str) -> Path | None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / rel,
        here.parents[1] / rel,
        Path.cwd() / rel,
    ]
    try:
        pass

        # packaged layout may expose completions next to project root only
    except Exception:
        pass
    for path in candidates:
        if path.is_file():
            return path
    return None


def install_completions(
    *,
    shell: str | None = None,
    dry_run: bool = False,
) -> list[str]:
    """
    Copy completion file for shell into the user dir.

    Returns list of human-readable action lines.
    """
    shell = detect_shell(shell)
    if shell not in COMPLETION_FILES:
        raise ValueError("Unsupported shell: {0}".format(shell))
    rel, dest_name = COMPLETION_FILES[shell]
    src = _find_source(rel)
    if src is None:
        raise FileNotFoundError(
            "Completion file not found: {0}. Run from a source checkout or reinstall pip-rns.".format(
                rel
            )
        )
    dest_dir = _dest_dir(shell)
    dest = dest_dir / dest_name
    lines = ["{0} -> {1}".format(src, dest)]
    if dry_run:
        return lines
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    if shell == "zsh":
        lines.append(
            "Ensure ~/.local/share/zsh/site-functions is on fpath, then reopen the shell."
        )
    elif shell == "bash":
        lines.append("Reopen the shell (bash-completion must be enabled).")
    else:
        lines.append("Reopen the fish shell.")
    return lines
