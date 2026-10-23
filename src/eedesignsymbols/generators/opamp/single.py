"""The single op-amp generator: a config-driven copy-edit of one template.

Every decision belongs to the config file, not this module: which pin to
keep, its manufacturer name, its pin number, its electrical type, and the
generated symbol's own name. See
:mod:`eedesignsymbols.generators.opamp.config`. This module only executes the
decision.

NAMING

The generated symbol's name is ``OPAMP_SINGLE_<code>_SYMGEN``, where
``code`` comes straight from the config row's own ``code`` field, never
derived from a manufacturer part number. A pinout shape is shared by
however many real parts happen to match it, and none of them gets to name
the symbol.

A librarian composes ``code`` from a fixed order of segments, joined with
``_``, so two rows never collide by construction:

1. Pin count, as ``<N>p`` (``5p``, ``6p``, ...). Always present, always
   first: the coarsest, least opinionated split.
2. The control pin's own rendered text, with ``~{X}`` written as ``nX``
   (``~{SHDN}`` becomes ``nSHDN``). Every active-low control pin is
   written this way, whatever bar or slash or nothing the source used
   (a source pin bare-named ``SD`` still renders as ``~{SD}`` on the
   generated symbol, and its code segment is ``nSD``). Omitted when the
   row has no control pin.
3. ``FB`` when the row keeps ``FB_OUT``. Omitted otherwise.
4. ``PAD<type>`` when the row keeps ``PAD``, where ``<type>`` is
   ``pwr`` (electrical type ``power_in``), ``passive``, or ``nc``
   (``no_connect``). Omitted when the row drops ``PAD``.
5. ``NC`` when the row keeps any ``NC`` pin. Omitted otherwise.

No segment ranks the shapes it names: ``6p_nSHDN`` is not "more standard"
than ``6p_EN``, only differently shaped. A segment's absence is a fact
about that row's pins, not a judgment about it.

RERUN THIS GENERATOR
--------------------
Every part row in the config is generated. A file that already holds the same
content is left alone, and any other is overwritten. Safe to paste as often as
you like::

    .venv\\Scripts\\python.exe -m eedesignsymbols.generators.opamp.single \\
        --config "src\\eedesignsymbols\\generators\\opamp\\single_opamp_parts.yaml" \\
        --dir "<output dir>"

Add ``--dry-run`` to see what it would do without writing.

A real (non-dry-run) run also renders every symbol it wrote and builds an
HTML preview gallery, under ``./.preview`` by default, never inside
``--dir``: an output folder is not a place for render output to
accumulate. Pass ``--no-preview`` to skip it, or ``--preview-dir`` to
write it somewhere else.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from eedesigncore import Pin, PinElectricalType, SchPolyline, SymbolLib

from eedesignsymbols import version
from eedesignsymbols.format_version import FormatVersionError, require_current_format
from eedesignsymbols.generators import common
from eedesignsymbols.generators.common import (
    annotate,
    generated_name,
    rename_symbol,
    require_provenance,
    same_kind,
    set_provenance,
)
from eedesignsymbols.generators.opamp.config import ALL_TEMPLATE_PINS, PartSpec, load_config
from eedesignsymbols.preview_tools import (
    DEFAULT_OUTPUT_DIRNAME,
    GalleryEntry,
    build_gallery,
    export_svgs,
)
from eedesignsymbols.symbol_fields import DESCRIPTION_FIELD, set_field
from eedesignsymbols.writing import Outcome, ResultLike, Route, default_route

GENERATOR = "opamp_single"
TEMPLATE_NAME = "_OPAMP_SINGLE_SYMGEN_TEMPLATE"

_FB_OUT_SLOT = "FB_OUT"

_FB_OUT_STUB_PTS = ((6.35, -2.54), (5.08, 0.0))
"""The exact points of the short diagonal line joining the FB_OUT pin stub
to the triangle body, on _OPAMP_SINGLE_SYMGEN_TEMPLATE. Fixed rather than
found by position or count: the template may carry any number of other
polylines (an OUT-side stub, and whatever comes next), and this is the one
specific graphic tied to FB_OUT, identified by what it draws, not by where
it sits in the file."""


class GeneratorError(ValueError):
    """The template, or a config row, cannot be built into a symbol."""


def _pin_number_text(numbers: tuple[str, ...]) -> str:
    """Return one KiCad pin-number string for every physical number given.

    A single number passes through unchanged. More than one becomes
    ``[n1,n2,...]``: one electrical pin, drawn once, carrying every
    physical package pin it connects to. KiCad reads this as one pin, not
    as several pins stacked at the same position.
    """
    if len(numbers) == 1:
        return numbers[0]
    return f"[{','.join(numbers)}]"


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def build(
    template: SymbolLib,
    spec: PartSpec,
    *,
    tool_version: str | None = None,
    route: Route | None = None,
) -> SymbolLib:
    """Return a new library holding one part's finished symbol.

    Copy-edits the template per ``spec``. Every pin ``spec`` marks for
    deletion is removed; for ``FB_OUT``, so is the diagonal graphic line
    that goes with it. Every pin that survives is renamed, renumbered, and
    retyped from ``spec``. The input is not modified. ``route`` adds its own
    fields to the output, and defaults to
    :func:`~eedesignsymbols.writing.default_route`.
    """
    if len(template.symbols) != 1:
        raise GeneratorError(f"expected exactly 1 symbol, found {len(template.symbols)}")

    lib = template.model_copy(deep=True)
    symbol = lib.symbols[0]
    built_from = symbol.name

    found_slots: set[str] = set()

    for unit in symbol.units:
        kept_items: list[object] = []
        fb_out_deleted = False

        for item in unit.items:
            if not same_kind(item, Pin):
                kept_items.append(item)
                continue

            slot = str(item.name)
            if slot not in ALL_TEMPLATE_PINS:
                raise GeneratorError(f"{built_from}: unexpected pin {slot!r} on the template")
            found_slots.add(slot)

            pin_spec = spec.kept(slot)
            if pin_spec is None:
                if slot == _FB_OUT_SLOT:
                    fb_out_deleted = True
                continue  # this pin is dropped

            item.name = pin_spec.name
            if pin_spec.electrical_type is not None:
                item.electrical_type = PinElectricalType(pin_spec.electrical_type)
            if pin_spec.name_text_size is not None:
                item.name_text_size = pin_spec.name_text_size

            item.number = _pin_number_text(pin_spec.numbers)
            kept_items.append(item)

        if fb_out_deleted:
            fb_stub = next(
                (
                    i
                    for i in kept_items
                    if same_kind(i, SchPolyline) and tuple(i.pts) == _FB_OUT_STUB_PTS
                ),
                None,
            )
            if fb_stub is None:
                raise GeneratorError(
                    f"{built_from}: could not find the FB_OUT stub polyline (expected "
                    f"points {_FB_OUT_STUB_PTS}) in unit {unit.unit_index} to drop it. "
                    "The template shape changed; update _FB_OUT_STUB_PTS to match."
                )
            kept_items = [i for i in kept_items if i is not fb_stub]

        unit.items = kept_items

    missing_slots = set(ALL_TEMPLATE_PINS) - found_slots
    if missing_slots:
        raise GeneratorError(
            f"{built_from}: template is missing pin slot(s) {sorted(missing_slots)}"
        )

    # Pin number visibility is inherited from the template, never set here. Same
    # operator ruling as `pinout.Family.build`, 2026-08-26: a template that hides
    # its pin numbers is stating how the part is drawn, and a generator does not
    # overrule the drawing.

    rename_symbol(symbol, generated_name(built_from, spec.code))

    set_field(symbol, DESCRIPTION_FIELD, spec.description)
    pin_entries = sorted(
        (
            (int(number), number, ps.name)
            for slot in ALL_TEMPLATE_PINS
            if (ps := spec.kept(slot)) is not None
            for number in ps.numbers
        ),
        key=lambda entry: entry[0],
    )
    pin_list = " ".join(f"{number}={name}" for _, number, name in pin_entries)
    annotate(symbol, f"(pins {pin_list})")

    (route or default_route()).stamp(
        symbol, generator=GENERATOR, template=built_from, version=tool_version
    )
    set_provenance(lib, generator=GENERATOR, version=tool_version)

    return lib


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def generate_all(
    config_path: Path | str,
    template_dir: Path | str | None,
    out_dir: Path | str,
    *,
    dry_run: bool = False,
    route: Route | None = None,
) -> list[ResultLike]:
    """Bring ``out_dir`` up to date with every part row in ``config_path``.

    The route writes each row, exactly as for the permutation generators. The
    default route writes nothing when the file already holds the same bytes, and
    overwrites it otherwise.

    Args:
        config_path: The YAML config file.
        template_dir: Directory holding the template file. None reads it from the
            route's own folder: the template this package ships, for the default
            route.
        out_dir: Destination directory. Must exist.
        dry_run: Decide and report, but write nothing.
        route: Defaults to :func:`~eedesignsymbols.writing.default_route`.
    """
    route = route or default_route()
    out_dir = Path(out_dir)
    folder = template_dir if template_dir is not None else route.template_dir()
    if folder is None:
        raise GeneratorError("this route needs a template folder")

    try:
        template_path = route.find_template(Path(folder), TEMPLATE_NAME)
    except route.refusals as exc:
        raise GeneratorError(str(exc)) from exc
    if template_path is None:
        raise GeneratorError(route.missing_message(GENERATOR, [TEMPLATE_NAME], Path(folder)))

    template = SymbolLib.from_file(template_path)
    require_current_format(template, template_path)

    specs = load_config(config_path)

    results: list[ResultLike] = []
    for spec in specs:
        lib = build(template, spec, route=route)
        require_provenance(lib)
        try:
            if dry_run:
                results.append(route.plan(lib, out_dir))
            else:
                results.append(route.write(lib, out_dir))
        except route.refusals as exc:
            raise GeneratorError(f"{spec.code}: {exc}") from exc

    return results


def build_preview(results: Sequence[ResultLike], preview_dir: Path) -> Path:
    """Render every symbol ``results`` names and write a gallery for them.

    Only the files this run actually touched, not the rest of whatever
    directory they landed in: an output folder can hold hundreds of
    unrelated symbols, and a librarian checking one generator run does not
    want those in the way.

    Returns the written gallery's path.
    """
    written = [r.path for r in results if r.path.is_file()]
    export_results = export_svgs(written, preview_dir / "svgs")
    export_by_path = {r.sym_path: r for r in export_results}

    entries = [
        GalleryEntry(
            name=path.stem,
            category=GENERATOR,
            svg_paths=export_by_path[path].svg_paths,
            error=export_by_path[path].error,
        )
        for path in written
    ]
    return build_gallery(entries, preview_dir / "gallery.html")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None, *, route: Route | None = None) -> int:
    """Command line entry point. See the rerun block at the top of this file."""
    parser = argparse.ArgumentParser(
        prog="python -m eedesignsymbols.generators.opamp.single",
        description="Generate single op-amp symbols from a YAML config and one template.",
        allow_abbrev=False,
    )
    parser.add_argument("--config", required=True, type=Path, help="The YAML config file.")
    parser.add_argument(
        "--dir",
        required=True,
        type=Path,
        help="The output directory.",
    )
    parser.add_argument("--out", type=Path, default=None, help="Write here instead of --dir.")
    parser.add_argument(
        "--templates",
        type=Path,
        default=None,
        help="Directory holding the SYMGEN template file "
        "(default: the template this package ships).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would happen, and write nothing."
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Permit a write from a modified or unidentified tool tree. Scratch copies only.",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Skip building an HTML preview gallery of the symbols this run writes.",
    )
    parser.add_argument(
        "--preview-dir",
        type=Path,
        default=None,
        help=f"Preview gallery output directory (default: ./{DEFAULT_OUTPUT_DIRNAME}, "
        "relative to the current directory, never inside --dir).",
    )
    args = parser.parse_args(argv)

    route = route or default_route()
    refused: tuple[type[Exception], ...] = (GeneratorError, FormatVersionError, *route.refusals)
    template_dir: Path = args.templates or route.template_dir() or args.dir
    out_dir: Path = args.out or args.dir
    if not args.dir.is_dir():
        parser.error(f"--dir is not a directory: {args.dir}")
    if not out_dir.is_dir():
        parser.error(f"--out is not a directory: {out_dir}")
    if not template_dir.is_dir():
        parser.error(f"--templates is not a directory: {template_dir}")

    if not args.dry_run:
        stamp = common.tool_version()
        if not version.write_permitted(stamp):
            if not args.allow_dirty:
                print(f"error: {version.unidentified_tree_message(stamp)}")
                return 1
            print(f"--allow-dirty overrode a refusal: the stamp reads {stamp!r}.")

    tally: dict[str, int] = {outcome.value: 0 for outcome in Outcome}
    try:
        results = generate_all(
            args.config, template_dir, out_dir, dry_run=args.dry_run, route=route
        )
    except refused as exc:
        print(f"error: {exc}")
        return 1

    print(f"{TEMPLATE_NAME}:")
    for result in results:
        outcome = str(result.outcome.value)
        tally[outcome] = tally.get(outcome, 0) + 1
        line = f"    {outcome:<11} {result.path.name}"
        if result.superseded is not None:
            line += f"  (deprecated {result.superseded.name})"
        print(line)

    prefix = "would be" if args.dry_run else ""
    summary = ", ".join(f"{count} {outcome}" for outcome, count in tally.items() if count)
    print(f"\n{prefix} {summary}".strip())

    if not args.dry_run and not args.no_preview:
        preview_dir = args.preview_dir or Path.cwd() / DEFAULT_OUTPUT_DIRNAME
        gallery_path = build_preview(results, preview_dir)
        print(f"preview: {gallery_path}")

    return 0


__all__ = [
    "GENERATOR",
    "TEMPLATE_NAME",
    "GeneratorError",
    "build",
    "build_preview",
    "generate_all",
    "main",
]


if __name__ == "__main__":
    import sys

    sys.exit(main())
