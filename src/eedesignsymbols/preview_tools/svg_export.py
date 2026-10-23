"""Multiprocessed SVG export for a set of ``.kicad_sym`` files, via ``kicad-cli``.

No rasterizer and no color theme. A preview gallery displays the SVG a browser
already knows how to render, so nothing here produces a PNG.

Renders through a wrapped schematic (see ``sch_wrapper.py``) rather than
``kicad-cli sym export svg`` directly, because the latter has no font
control at all: confirmed against the KiCad 10.0.3 source,
``command_sym_export_svg.cpp`` carries no font-handling code. ``kicad-cli
sch export svg --default-font`` does, so every symbol unit is wrapped into
a throwaway one-symbol schematic first.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from eedesignsymbols.preview_tools.sch_wrapper import wrap_symbol_file

_DEFAULT_CLI_PATH = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")

DEFAULT_FONT = "Cascadia Mono"
"""The font every preview render uses unless a caller overrides it."""

_WRAPPED_SUBDIR = "_wrapped"
"""Holds the throwaway .kicad_sch files, kept out of the *.svg glob below."""


def find_kicad_cli() -> Path:
    """Return the path to ``kicad-cli``.

    Checks the system PATH first, then the default KiCad 10 install location
    on Windows.

    Raises:
        FileNotFoundError: Neither location holds ``kicad-cli``.
    """
    found = shutil.which("kicad-cli")
    if found:
        return Path(found)
    if _DEFAULT_CLI_PATH.is_file():
        return _DEFAULT_CLI_PATH
    raise FileNotFoundError(
        "kicad-cli not found on PATH or at the default KiCad 10 install location "
        f"({_DEFAULT_CLI_PATH})"
    )


@dataclass(frozen=True)
class ExportTask:
    """One symbol library file to export. Picklable for a process pool."""

    sym_path: Path
    output_dir: Path
    kicad_cli: Path
    default_font: str = DEFAULT_FONT
    black_and_white: bool = False


@dataclass
class ExportResult:
    """The outcome of exporting one symbol library file."""

    sym_path: Path
    svg_paths: list[Path] = field(default_factory=list)
    error: str | None = None


def _run_export(task: ExportTask) -> ExportResult:
    """Run one export task. Module-level so a process pool can pickle it."""
    if task.output_dir.exists():
        shutil.rmtree(task.output_dir)
    task.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        sch_paths = wrap_symbol_file(task.sym_path, task.output_dir / _WRAPPED_SUBDIR)
    except ValueError as exc:
        return ExportResult(task.sym_path, error=str(exc))

    for sch_path in sch_paths:
        cmd = [
            str(task.kicad_cli),
            "sch",
            "export",
            "svg",
            "-o",
            str(task.output_dir),
            "--exclude-drawing-sheet",
            "--no-background-color",
            "--default-font",
            task.default_font,
            str(sch_path),
        ]
        if task.black_and_white:
            cmd.append("--black-and-white")

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()[:500]
            return ExportResult(task.sym_path, error=err)

    svg_paths = sorted(task.output_dir.glob("*.svg"))
    return ExportResult(task.sym_path, svg_paths=svg_paths)


def export_svgs(
    sym_paths: Sequence[Path],
    output_dir: Path,
    *,
    workers: int | None = None,
    default_font: str = DEFAULT_FONT,
    black_and_white: bool = False,
    kicad_cli: Path | None = None,
) -> list[ExportResult]:
    """Export every symbol in each of ``sym_paths`` to SVG.

    One worker process per file. Each file's SVGs land in
    ``output_dir / <file-stem>/``, which is cleared before that file's export
    runs, so a rename or a dropped unit in the source file cannot leave a
    stale SVG behind.

    Args:
        sym_paths: The ``.kicad_sym`` files to export. Each must hold
            exactly one symbol.
        output_dir: Root directory for the per-file SVG subdirectories.
        workers: Worker count. Defaults to ``ProcessPoolExecutor``'s own default.
        default_font: Passed through to ``kicad-cli sch export svg --default-font``.
        black_and_white: Passed through to ``kicad-cli sch export svg``.
        kicad_cli: Overrides the resolved ``kicad-cli`` path. Pass it in a test.
    """
    cli = kicad_cli or find_kicad_cli()
    tasks = [
        ExportTask(
            sym_path=p,
            output_dir=output_dir / p.stem,
            kicad_cli=cli,
            default_font=default_font,
            black_and_white=black_and_white,
        )
        for p in sym_paths
    ]

    results: list[ExportResult] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_export, t): t for t in tasks}
        for future in as_completed(futures):
            results.append(future.result())
    return results


__all__ = ["DEFAULT_FONT", "ExportResult", "ExportTask", "export_svgs", "find_kicad_cli"]
