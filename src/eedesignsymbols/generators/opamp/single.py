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

Each code has the form ``<N>P_PINOUT<NN>``, for example ``5P_PINOUT02``.
``<N>`` is the total pin count. The number ``<NN>`` counts separately for each
amplifier count and pin count. Each number is written in the configuration, not
derived from row order, and a retired number is not used again. The description
lists the full pinout.

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
import re
from collections.abc import Sequence
from pathlib import Path

from eedesigncore import Pin, PinElectricalType, SchPolyline, SchRect, SymbolLib, SymbolUnit

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
from eedesignsymbols.generators.opamp.config import (
    ALL_TEMPLATE_PINS,
    ConfigError,
    PartSpec,
    load_config,
)
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


def fit_pin_name(pin: Pin, unit: SymbolUnit) -> None:
    """Shrink a visible pin name so it fits inside the body along the pin axis.

    The fit takes a width of one text size per visible character and keeps 2
    percent of the body width free for offsets, strokes, and a sloped body edge.
    It is an estimate, not a font measurement. A size set in the configuration is
    an upper limit. A hidden name stays hidden. The template is not changed.
    """
    if pin.name_text_size <= 0:
        return
    visible = re.sub(r"[~^_]\{([^{}]*)\}", r"\1", str(pin.name))
    if not visible or visible == "~":
        return
    vertical = pin.angle % 180 == 90
    cross_axis = 0 if vertical else 1
    along_axis = 1 - cross_axis
    cross = pin.position[cross_axis]
    spans = []
    for item in unit.items:
        if same_kind(item, SchPolyline) and item.pts and item.pts[0] == item.pts[-1]:
            points = item.pts
        elif same_kind(item, SchRect):
            x0, y0 = item.start
            x1, y1 = item.end
            points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        else:
            continue
        crossings = []
        for start, end in zip(points, points[1:], strict=False):
            a, b = start[cross_axis], end[cross_axis]
            if a != b and min(a, b) <= cross <= max(a, b):
                fraction = (cross - a) / (b - a)
                crossings.append(
                    start[along_axis] + fraction * (end[along_axis] - start[along_axis])
                )
        if crossings and max(crossings) > min(crossings):
            spans.append(max(crossings) - min(crossings))
    if spans:
        pin.name_text_size = min(pin.name_text_size, round(0.98 * max(spans) / len(visible), 4))


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
    if spec.channels != 1:
        raise GeneratorError(f"{spec.code}: use the dual generator for two channels")
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
            fit_pin_name(item, unit)
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
    annotate(symbol, pinout_description(spec))

    (route or default_route()).stamp(
        symbol, generator=GENERATOR, template=built_from, version=tool_version
    )
    set_provenance(lib, generator=GENERATOR, version=tool_version)

    return lib


def pinout_description(spec: PartSpec) -> str:
    """Return ``(pins 1=... 2=...)``, in pin number order.

    A pin of a two-channel row carries its channel, for example ``3=CHA.INA+``.
    """

    def label(slot: str, name: str) -> str:
        channel, separator, _ = slot.rpartition(".")
        return f"{channel}.{name}" if separator else name

    pin_entries = sorted(
        (
            (number, label(slot, ps.name))
            for slot, ps in spec.pins.items()
            if ps is not None
            for number in ps.numbers
        ),
        key=lambda entry: (0, int(entry[0])) if entry[0].isdecimal() else (1, entry[0]),
    )
    return "(pins " + " ".join(f"{number}={name}" for number, name in pin_entries) + ")"


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
    channels: int = 1,
    only: Sequence[str] = (),
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
        channels: 1 for single op-amp rows, 2 for dual rows. Every row in the
            configuration must have this channel count.
        only: The row codes to generate. Empty means every row.

    Every selected row is built before the first write, so a bad row writes
    nothing.
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
    if channels not in (1, 2) or any(spec.channels != channels for spec in specs):
        raise GeneratorError("The configuration channel count does not match this command.")
    if only:
        unknown = set(only) - {spec.code for spec in specs}
        if unknown:
            raise GeneratorError(f"Unknown part code(s): {', '.join(sorted(unknown))}")
        specs = [spec for spec in specs if spec.code in only]

    builder = build
    if channels == 2:
        from eedesignsymbols.generators.opamp.dual import build as build_dual

        builder = build_dual

    libraries = [(spec, builder(template, spec, route=route)) for spec in specs]

    results: list[ResultLike] = []
    for spec, lib in libraries:
        require_provenance(lib)
        try:
            if dry_run:
                results.append(route.plan(lib, out_dir))
            else:
                results.append(route.write(lib, out_dir))
        except route.refusals as exc:
            raise GeneratorError(f"{spec.code}: {exc}") from exc

    return results


def build_preview(
    results: Sequence[ResultLike], preview_dir: Path, *, generator: str = GENERATOR
) -> Path:
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
            category=generator,
            svg_paths=export_by_path[path].svg_paths,
            error=export_by_path[path].error,
        )
        for path in written
    ]
    return build_gallery(entries, preview_dir / "gallery.html")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(
    argv: Sequence[str] | None = None, *, route: Route | None = None, channels: int = 1
) -> int:
    """Command line entry point. See the rerun block at the top of this file.

    ``channels`` is 2 for the dual command, :mod:`eedesignsymbols.generators.opamp.dual`.
    """
    kind = "dual" if channels == 2 else "single"
    parser = argparse.ArgumentParser(
        prog=f"python -m eedesignsymbols.generators.opamp.{kind}",
        description=f"Generate {kind} op-amp symbols from a YAML config and one template.",
        allow_abbrev=False,
    )
    parser.add_argument("--config", required=True, type=Path, help="The YAML config file.")
    parser.add_argument(
        "--part",
        action="append",
        default=[],
        metavar="CODE",
        help="Generate only this configuration code. Repeat to select more than one.",
    )
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
    refused: tuple[type[Exception], ...] = (
        ConfigError,
        GeneratorError,
        FormatVersionError,
        *route.refusals,
    )
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
            args.config,
            template_dir,
            out_dir,
            dry_run=args.dry_run,
            route=route,
            channels=channels,
            only=args.part,
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
        gallery_path = build_preview(results, preview_dir, generator=f"opamp_{kind}")
        print(f"preview: {gallery_path}")

    return 0


__all__ = [
    "GENERATOR",
    "TEMPLATE_NAME",
    "GeneratorError",
    "build",
    "build_preview",
    "fit_pin_name",
    "generate_all",
    "main",
    "pinout_description",
]


if __name__ == "__main__":
    import sys

    sys.exit(main())
