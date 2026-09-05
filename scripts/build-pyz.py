#!/usr/bin/env python3
"""Build standalone zipapps: dist/opip.pyz and dist/pip-rns.pyz."""

from __future__ import annotations

import argparse
import shutil
import sys
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
DIST = ROOT / "dist"


def _copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(
        src,
        dest,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            "*.pyo",
            ".mypy_cache",
            "*.ruff_cache",
        ),
    )


def _stage(workdir: Path) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    _copy_tree(SRC / "opip", workdir / "opip")
    _copy_tree(SRC / "pip_rns", workdir / "pip_rns")


def build_one(name: str, main: str, workdir: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}.pyz"
    if target.exists():
        target.unlink()
    zipapp.create_archive(
        workdir,
        target=str(target),
        interpreter="/usr/bin/env python3",
        main=main,
        compressed=True,
    )
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output-dir",
        default=str(DIST),
        help="Directory for .pyz files (default: dist/)",
    )
    parser.add_argument(
        "--only",
        choices=("opip", "pip-rns", "all"),
        default="all",
        help="Which zipapp to build",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.output_dir)
    work = out_dir / ".pyz-stage"
    if work.exists():
        shutil.rmtree(work)
    try:
        _stage(work)
        built: list[Path] = []
        if args.only in ("opip", "all"):
            built.append(build_one("opip", "opip.cli:main", work, out_dir))
        if args.only in ("pip-rns", "all"):
            built.append(build_one("pip-rns", "pip_rns.cli:main", work, out_dir))
        for path in built:
            size = path.stat().st_size
            print(f"built {path} ({size} bytes)")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
