"""Render any set of ``.kicad_sym`` files to SVG and browse them in one HTML page.

Generic and reusable: any generator points this at its own output directory
or file list after a run. Not opamp-specific, not specific to a library's rules.

    from eedesignsymbols.preview_tools import export_svgs, build_gallery, GalleryEntry

    results = export_svgs(sym_files, output_dir / "svgs")
    entries = [GalleryEntry(p.stem, p.parent.name, r.svg_paths, r.error)
               for p, r in zip(sym_files, results)]
    build_gallery(entries, output_dir / "gallery.html")

Every caller writes under a ``.preview/`` directory (see
:data:`eedesignsymbols.preview_tools.cli.DEFAULT_OUTPUT_DIRNAME`), which is the
one pattern the repo's ``.gitignore`` needs for every generator's preview
output.
"""

from __future__ import annotations

from eedesignsymbols.preview_tools.cli import DEFAULT_OUTPUT_DIRNAME
from eedesignsymbols.preview_tools.gallery import GalleryEntry, build_gallery
from eedesignsymbols.preview_tools.sch_wrapper import (
    renderable_units,
    wrap_symbol_file,
    wrap_unit,
)
from eedesignsymbols.preview_tools.svg_export import (
    DEFAULT_FONT,
    ExportResult,
    export_svgs,
    find_kicad_cli,
)

__all__ = [
    "DEFAULT_FONT",
    "DEFAULT_OUTPUT_DIRNAME",
    "ExportResult",
    "GalleryEntry",
    "build_gallery",
    "export_svgs",
    "find_kicad_cli",
    "renderable_units",
    "wrap_symbol_file",
    "wrap_unit",
]
