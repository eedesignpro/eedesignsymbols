"""Command line entry point for the preview gallery tool.

    python -m eedesignsymbols.preview_tools <path> [<path> ...] [options]

Each positional argument is a ``.kicad_sym`` file, or a directory searched
recursively for ``.kicad_sym`` files. Any generator can call
:func:`eedesignsymbols.preview_tools.export_svgs` and
:func:`eedesignsymbols.preview_tools.build_gallery` directly instead of going
through this CLI.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

from eedesignsymbols.preview_tools.gallery import GalleryEntry, build_gallery
from eedesignsymbols.preview_tools.svg_export import DEFAULT_FONT, export_svgs

DEFAULT_OUTPUT_DIRNAME = ".preview"
"""Every caller writes under a directory of this name, so one `.gitignore`
pattern covers every generator's preview output. See CLAUDE.md."""


def _collect_sym_files(paths: Sequence[Path]) -> list[Path]:
    """Resolve ``paths`` to a deduplicated, sorted list of ``.kicad_sym`` files."""
    found: set[Path] = set()
    for p in paths:
        if p.is_dir():
            found.update(p.rglob("*.kicad_sym"))
        elif p.is_file():
            found.add(p)
        else:
            raise FileNotFoundError(f"not a file or directory: {p}")
    return sorted(found)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = argparse.ArgumentParser(
        prog="python -m eedesignsymbols.preview_tools",
        description="Render a set of .kicad_sym files to SVG and build a preview gallery.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help=".kicad_sym files, or directories to search recursively for them.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=f"Root output directory (default: ./{DEFAULT_OUTPUT_DIRNAME}).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Worker process count (default: ProcessPoolExecutor's own default).",
    )
    parser.add_argument(
        "--default-font",
        default=DEFAULT_FONT,
        help=f"Passed to kicad-cli sch export svg --default-font (default: {DEFAULT_FONT}).",
    )
    parser.add_argument(
        "--black-and-white",
        action="store_true",
        help="Passed through to kicad-cli sch export svg.",
    )
    args = parser.parse_args(argv)

    output_dir: Path = args.output_dir or Path.cwd() / DEFAULT_OUTPUT_DIRNAME
    sym_files = _collect_sym_files(args.paths)
    if not sym_files:
        print("error: no .kicad_sym files found in the given paths")
        return 1

    results = export_svgs(
        sym_files,
        output_dir / "svgs",
        workers=args.workers,
        default_font=args.default_font,
        black_and_white=args.black_and_white,
    )
    results_by_path = {r.sym_path: r for r in results}

    entries = [
        GalleryEntry(
            name=path.stem,
            category=os.path.basename(os.path.dirname(path)) or ".",
            svg_paths=results_by_path[path].svg_paths,
            error=results_by_path[path].error,
        )
        for path in sym_files
    ]

    gallery_path = build_gallery(entries, output_dir / "gallery.html")

    error_count = sum(1 for r in results if r.error)
    print(f"{len(results)} file(s) exported, {error_count} error(s)")
    print(f"gallery: {gallery_path}")
    return 1 if error_count else 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
