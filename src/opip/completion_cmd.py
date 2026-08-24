"""Install shell completion scripts for opip."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

COMPLETION_FILES = {
    "bash": ("completions/opip.bash", "opip"),
    "zsh": ("completions/_opip", "_opip"),
    "fish": ("completions/opip.fish", "opip.fish"),
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
    raise ValueError(f"Unsupported shell: {shell} (use bash, zsh, or fish)")


def _find_source(rel: str) -> Path | None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / rel,
        here.parents[1] / rel,
        Path.cwd() / rel,
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def install_completions(
    *, shell: str | None = None, dry_run: bool = False
) -> list[str]:
    shell = detect_shell(shell)
    if shell not in COMPLETION_FILES:
        raise ValueError(f"Unsupported shell: {shell}")
    rel, dest_name = COMPLETION_FILES[shell]
    src = _find_source(rel)
    if src is None:
        raise FileNotFoundError(
            f"Completion file not found: {rel}. Run from a source checkout or reinstall."
        )
    dest_dir = _dest_dir(shell)
    dest = dest_dir / dest_name
    lines = [f"{src} -> {dest}"]
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
