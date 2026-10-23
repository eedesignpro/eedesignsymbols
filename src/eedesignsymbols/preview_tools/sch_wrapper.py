"""Wrap one symbol unit into a throwaway one-symbol schematic.

``kicad-cli sym export svg`` has no font control at all: confirmed against
the KiCad 10.0.3 source, ``command_sym_export_svg.cpp`` has no font-handling
code, unlike the ``sch export`` command family, which reads a ``--default-font``
argument into ``JOB_SCH_RENDER::m_defaultFont``. Wrapping a symbol into a
minimal schematic is the only way to render it with a chosen font without
writing that font choice into the symbol itself, which must stay a render-time
choice, not a library asset property.

Every UUID here is freshly generated per call. These schematics are
gitignored and rebuilt on every render, so reproducibility buys nothing.
"""

from __future__ import annotations

import uuid as uuid_lib
from pathlib import Path

from eedesigncore import (
    Paper,
    RootInstancePath,
    Schematic,
    SheetInstances,
    Symbol,
    SymbolLib,
    inject_symbol,
)

from eedesignsymbols.bbox import BBox, symbol_bbox

_MARGIN_MM = 2.54
"""Blank border on all four sides of the fitted page. One KiCad grid step."""

_FALLBACK_BOX = BBox(-5.08, -5.08, 5.08, 5.08)
"""Used only when a unit draws nothing at all, which real content never does."""


def _with_hidden_fields(symbol: Symbol) -> Symbol:
    """Return a copy of ``symbol`` with every field (Reference, Value, the
    any library ``_SYM.*`` fields, and so on) marked not visible.

    A preview cares about the pin layout, not a field's text. Left visible,
    a long field value (the generated symbol's own name can run past forty
    characters, and a library lifecycle text item is its own long,
    unresolved token outside a real project) inflates the fitted page far
    past the actual drawing and clutters the render besides.
    """
    copy = symbol.model_copy(deep=True)
    for prop in copy.fields:
        prop.visible = False
    return copy


_MIN_PAPER_MM = 25.4
"""kicad-cli silently raises any smaller "User" page dimension to this floor
(confirmed empirically: a requested 20.32 mm height came back as 25.4 mm).
Applying the same floor here first keeps the centering math and the page
kicad-cli actually writes in agreement, on both axes independently."""


def _fitted_paper_and_placement(box: BBox) -> tuple[Paper, tuple[float, float]]:
    """Return a page sized and a placement point that fit ``box`` with a margin.

    ``box`` is in the symbol's own coordinates: X right, Y up (bbox.py's
    convention, matching the .kicad_sym file). A schematic placement is X
    right, Y *down*, so the placement point is derived from ``box.max_y``,
    not ``box.min_y``: the top of the symbol-local content has to land
    ``_MARGIN_MM`` below the page's top edge.

    Each axis is floored to :data:`_MIN_PAPER_MM` independently, and the
    margin actually used to center the content grows to match, rather than
    the requested-but-unmet margin from a page kicad-cli would have
    resized on just one axis. Without this, a unit small enough to trip
    the floor on only one axis renders correctly on the other axis and
    pinned to one edge on the floored one.
    """
    paper_w = max(box.width + 2 * _MARGIN_MM, _MIN_PAPER_MM)
    paper_h = max(box.height + 2 * _MARGIN_MM, _MIN_PAPER_MM)
    margin_x = (paper_w - box.width) / 2
    margin_y = (paper_h - box.height) / 2

    paper = Paper(paper_type="User", width=paper_w, height=paper_h)
    at = (margin_x - box.min_x, margin_y + box.max_y)
    return paper, at


def wrap_unit(symbol: Symbol, unit: int, *, body_style: int = 1) -> Schematic:
    """Return a one-symbol schematic placing one unit of ``symbol``.

    The page is sized and the symbol positioned so the unit's own bounding
    box (:func:`eedesignsymbols.bbox.symbol_bbox`) fits with a uniform margin.
    Without this, a fixed page size only centers content that happens to
    match it, and anything smaller or larger renders offset toward one
    corner instead of filling the frame. Every field is hidden first
    (:func:`_with_hidden_fields`), because a field's text is not part of
    that bounding box question: a preview cares about the pin layout, and a
    long field value would both inflate the fitted page and clutter the
    render.

    Two more things are handled here that are not obvious from the
    ``kicad_file_io`` API alone, both confirmed by diffing a working
    reference schematic (built by a proven, independent tool) against this
    function's own output until they matched:

    1. ``lib_id`` is stripped back to a bare name. ``inject_symbol`` always
       qualifies a bare incoming name (an explicit nickname, a
       ``sym-lib-table`` match, or the ``kicad-file-io`` placeholder). A
       qualified ``Lib:Name`` id makes ``kicad-cli`` try to resolve ``Lib``
       against a project's ``sym-lib-table``, which does not exist for a
       throwaway render with no real backing library, and the schematic
       fails to load ("Failed to load schematic") even though the
       definition sits right there in ``lib_symbols``.
    2. ``generate_uuids`` is not called. ``inject_symbol`` already fills
       ``placed.uuid`` and every pin's ``uuid`` on its own. Calling
       ``generate_uuids`` on the whole schematic also adds a ``uuid`` to
       graphic items inside the embedded ``lib_symbols`` definition, which
       is invalid there (a symbol library's own graphic items never carry
       one) and makes ``kicad-cli`` refuse to load the file.
    """
    symbol = _with_hidden_fields(symbol)
    box = symbol_bbox(symbol, unit=unit, body_style=None) or _FALLBACK_BOX
    paper, at = _fitted_paper_and_placement(box)

    sch = Schematic()
    sch.uuid = str(uuid_lib.uuid4())
    sch.paper = paper
    sch.sheet_instances = SheetInstances(paths=[RootInstancePath(path="/", page="1")])

    placed = inject_symbol(
        sch,
        symbol,
        at=at,
        unit=unit,
        body_style=body_style,
        reference="U1",
        project_name="preview",
        sheet_path=f"/{sch.uuid}",
    )

    qualified = placed.lib_id
    if ":" in qualified:
        bare = qualified.split(":", 1)[1]
        for defn in sch.lib_symbols:
            if defn.name == qualified:
                defn.name = bare
        placed.lib_id = bare

    return sch


def renderable_units(symbol: Symbol) -> list[int]:
    """Return the unit indices worth rendering, in order. One entry per real unit.

    **Unit index 0 is not a unit.** It is KiCad's "common to all units" layer,
    holding the graphics every unit shares, and KiCad draws it merged into
    whichever unit is placed. Rendering it on its own therefore repeats a drawing
    the real unit already shows in full.

    A generated diode is the case that exposed it. Every one is a single-unit part
    stored as unit 0 (the body) plus unit 1 (the pins), and the preview rendered
    two SVGs whose only difference was the file name embedded in the SVG title.

    A symbol that carries nothing but unit 0 still renders once, because a drawing
    with no unit-specific content is all common layer.

    Args:
        symbol: The symbol to inspect.

    Returns:
        Sorted unit indices, with 0 dropped whenever a real unit exists.
    """
    indices = sorted({unit.unit_index for unit in symbol.units})
    return [index for index in indices if index != 0] or indices


def wrap_symbol_file(sym_path: Path, out_dir: Path) -> list[Path]:
    """Write one ``.kicad_sch`` per real unit in ``sym_path``'s symbol.

    One file per unit, so a single-unit part gives one and a four-unit part gives
    four. :func:`renderable_units` decides which, and states why unit 0 is not one
    of them.

    Args:
        sym_path: A ``.kicad_sym`` file holding exactly one symbol.
        out_dir: Directory to write the wrapped schematics into. Created if
            missing.

    Returns:
        The written paths, one per rendered unit, named
        ``<sym_path stem>_unit<N>.kicad_sch``.

    Raises:
        ValueError: ``sym_path`` holds anything other than exactly one symbol.
    """
    lib = SymbolLib.from_file(sym_path)
    if len(lib.symbols) != 1:
        raise ValueError(f"{sym_path}: expected exactly 1 symbol, found {len(lib.symbols)}")
    symbol = lib.symbols[0]

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for unit_index in renderable_units(symbol):
        sch = wrap_unit(symbol, unit_index, body_style=1)
        out_path = out_dir / f"{sym_path.stem}_unit{unit_index}.kicad_sch"
        sch.to_file(out_path)
        written.append(out_path)
    return written


__all__ = ["renderable_units", "wrap_symbol_file", "wrap_unit"]
