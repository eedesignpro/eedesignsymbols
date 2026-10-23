"""The bounding box of a symbol, as it lands on a schematic sheet.

A generator has to know how much room its output takes. Two symbols in a family
must not overlap when a librarian drops them side by side, and a courtyard-style
check needs a number to compare. KiCad computes this internally and does not
write it to the file, so this module reconstructs it from the drawing.

WHAT IS COUNTED

Only what the schematic draws:

- a graphic shape, unless it carries ``(private yes)``, which keeps a shape
  inside the symbol editor
- a pin, unless it is hidden, plus its name and its number when the symbol
  shows them
- a field (property), unless it is hidden
- a free text or text box, unless it is private or hidden

WHAT IS APPROXIMATED

The box is a superset. It is never smaller than the real drawing, so a fit test
against it is safe, and it is a few tenths of a millimetre larger where a
character or an arc is measured by rule rather than by rendering:

- text width is character count times :data:`GLYPH_ADVANCE`. The KiCad stroke
  font is proportional, so a string of narrow characters measures wide
- a text variable such as ``${REFERENCE}`` is measured as written, not resolved
- an arc is measured across its start, mid, and end points. The bulge between
  two of those points is not sampled
- a bezier is measured across its four control points, which encloses the curve
- pin name and pin number text is added to BOTH sides of the pin, because which
  side KiCad picks depends on the pin angle
- a stroke adds half its width on each side. Width 0 means "use the default",
  which is :data:`DEFAULT_STROKE_WIDTH`

COORDINATES

Millimetres, in the coordinate system the ``.kicad_sym`` file uses: X to the
right, Y up. The numbers are the ones you read in the file, unchanged.

USAGE

    from eedesignsymbols.bbox import file_bboxes, symbol_bbox

    for name, box in file_bboxes("Q_PMOS_GSD.kicad_sym").items():
        print(name, box)

From a command line::

    .venv\\Scripts\\python.exe -m eedesignsymbols.bbox path\\to\\lib.kicad_sym
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eedesigncore import JustifyH, JustifyV, SymbolLib

DEFAULT_STROKE_WIDTH = 0.1524
"""Millimetres. What KiCad draws for a stroke whose width token reads 0."""

GLYPH_ADVANCE = 0.72
"""Width of one character, as a fraction of the font size. See "approximated"."""

LINE_PITCH = 1.6
"""Distance between two text lines, as a fraction of the font size."""

NO_PIN_NAME = "~"
"""KiCad's spelling of "this pin has no name". Nothing is drawn for it."""


@dataclass(frozen=True)
class BBox:
    """An axis-aligned box in millimetres. Y is up, as in the file."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        """Size along X."""
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        """Size along Y."""
        return self.max_y - self.min_y

    @property
    def center(self) -> tuple[float, float]:
        """The middle of the box, as (x, y)."""
        return ((self.min_x + self.max_x) / 2, (self.min_y + self.max_y) / 2)

    def union(self, other: BBox) -> BBox:
        """Return the smallest box that holds both boxes."""
        return BBox(
            min(self.min_x, other.min_x),
            min(self.min_y, other.min_y),
            max(self.max_x, other.max_x),
            max(self.max_y, other.max_y),
        )

    def __or__(self, other: BBox) -> BBox:
        """``a | b`` is ``a.union(b)``."""
        return self.union(other)

    def grown(self, margin: float) -> BBox:
        """Return the box with ``margin`` added on all four sides."""
        return BBox(
            self.min_x - margin,
            self.min_y - margin,
            self.max_x + margin,
            self.max_y + margin,
        )

    def rounded(self, ndigits: int = 4) -> BBox:
        """Return the box with every edge rounded, to hide float noise."""
        return BBox(
            round(self.min_x, ndigits),
            round(self.min_y, ndigits),
            round(self.max_x, ndigits),
            round(self.max_y, ndigits),
        )

    @classmethod
    def from_points(cls, points: Iterable[tuple[float, float]]) -> BBox | None:
        """Return the box around ``points``, or None when there are none."""
        xs: list[float] = []
        ys: list[float] = []
        for x, y in points:
            xs.append(x)
            ys.append(y)
        if not xs:
            return None
        return cls(min(xs), min(ys), max(xs), max(ys))

    def __str__(self) -> str:
        box = self.rounded(3)
        return (
            f"({box.min_x}, {box.min_y}) .. ({box.max_x}, {box.max_y}) "
            f"[{round(self.width, 3)} x {round(self.height, 3)} mm]"
        )


def union(boxes: Iterable[BBox | None]) -> BBox | None:
    """Return the box around every box given, ignoring None. None when empty."""
    result: BBox | None = None
    for box in boxes:
        if box is None:
            continue
        result = box if result is None else result.union(box)
    return result


# ----------------------------------------------------------------------
# Text
# ----------------------------------------------------------------------


def text_extent(content: str, size: tuple[float, float]) -> tuple[float, float]:
    """Return the (width, height) a string occupies, by the rule above."""
    lines = content.split("\n")
    columns = max((len(line) for line in lines), default=0)
    width = columns * size[0] * GLYPH_ADVANCE
    height = size[1] * (1 + (len(lines) - 1) * LINE_PITCH)
    return width, height


def text_bbox(
    content: str,
    position: tuple[float, float],
    size: tuple[float, float],
    *,
    angle_deg: float = 0.0,
    justify_h: Any = JustifyH.center,
    justify_v: Any = JustifyV.center,
) -> BBox | None:
    """Return the box a text item occupies. None when it draws nothing.

    ``position`` is the anchor. Justification says where the anchor sits inside
    the text, and ``angle_deg`` turns the text around the anchor.
    """
    width, height = text_extent(content, size)
    if width <= 0 or height <= 0:
        return None

    if justify_h is JustifyH.left:
        x0, x1 = 0.0, width
    elif justify_h is JustifyH.right:
        x0, x1 = -width, 0.0
    else:
        x0, x1 = -width / 2, width / 2

    if justify_v is JustifyV.top:
        y0, y1 = -height, 0.0
    elif justify_v is JustifyV.bottom:
        y0, y1 = 0.0, height
    else:
        y0, y1 = -height / 2, height / 2

    radians = math.radians(angle_deg)
    cos_a, sin_a = math.cos(radians), math.sin(radians)
    anchor_x, anchor_y = position
    return BBox.from_points(
        (anchor_x + dx * cos_a - dy * sin_a, anchor_y + dx * sin_a + dy * cos_a)
        for dx in (x0, x1)
        for dy in (y0, y1)
    )


def _attributes_of(item: Any) -> Any:
    """Return an item's text attributes, or a stand-in holding the defaults."""
    return item.attributes if item.attributes is not None else _DEFAULT_ATTRIBUTES


@dataclass(frozen=True)
class _DefaultAttributes:
    """What KiCad assumes when a text item writes no ``effects`` block."""

    font_size: tuple[float, float] = (1.27, 1.27)
    justify_h: Any = JustifyH.center
    justify_v: Any = JustifyV.center
    visible: bool = True


_DEFAULT_ATTRIBUTES = _DefaultAttributes()


# ----------------------------------------------------------------------
# Graphic shapes
# ----------------------------------------------------------------------


def _half_stroke(shape: Any) -> float:
    """Return how far a shape's outline reaches past its geometry."""
    width = getattr(shape, "stroke", None)
    raw = DEFAULT_STROKE_WIDTH if width is None or not width.width else width.width
    return raw / 2


def shape_bbox(shape: Any) -> BBox | None:
    """Return the box a graphic shape occupies, or None when it draws nothing.

    A private shape draws nothing: KiCad keeps it inside the symbol editor.
    """
    if getattr(shape, "private", False):
        return None

    kind = type(shape).__name__
    box: BBox | None
    if kind == "SchCircle":
        cx, cy = shape.center
        radius = abs(shape.radius)
        box = BBox(cx - radius, cy - radius, cx + radius, cy + radius)
    elif kind == "SchRect":
        box = BBox.from_points([shape.start, shape.end])
    elif kind == "SchArc":
        box = BBox.from_points([shape.start, shape.mid, shape.end])
    elif kind in ("SchPolyline", "SchBezier"):
        box = BBox.from_points(shape.pts)
    else:
        return None

    return None if box is None else box.grown(_half_stroke(shape))


def text_item_bbox(item: Any) -> BBox | None:
    """Return the box a ``text`` or ``text_box`` item occupies.

    ``SymText`` stores its angle in tenths of a degree. ``SymTextBox`` stores
    degrees, and carries its own size, so the box is taken from that size and
    the string inside it is not measured.
    """
    if getattr(item, "private", False):
        return None
    attributes = _attributes_of(item)
    if not attributes.visible:
        return None

    kind = type(item).__name__
    if kind == "SymText":
        return text_bbox(
            item.content,
            item.position,
            attributes.font_size,
            angle_deg=item.angle_degrees,
            justify_h=attributes.justify_h,
            justify_v=attributes.justify_v,
        )
    if kind == "SymTextBox":
        x, y = item.position
        width, height = item.size
        return BBox.from_points([(x, y), (x + width, y + height)])
    return None


# ----------------------------------------------------------------------
# Pins
# ----------------------------------------------------------------------


def _beside_axis(
    center: tuple[float, float],
    axis: tuple[float, float],
    content: str,
    size: float,
) -> BBox | None:
    """Return the box for text set along an axis, centred on ``center``.

    The text is placed on both sides of the axis. KiCad puts it on one side,
    chosen by the pin angle, so covering both keeps the result a superset.
    """
    width, height = text_extent(content, (size, size))
    if width <= 0:
        return None
    ax, ay = axis
    px, py = -ay, ax
    cx, cy = center
    return BBox.from_points(
        (
            cx + along * width / 2 * ax + across * height * px,
            cy + along * width / 2 * ay + across * height * py,
        )
        for along in (-1, 1)
        for across in (-1, 1)
    )


def pin_bbox(
    pin: Any,
    *,
    show_names: bool = True,
    show_numbers: bool = True,
    name_offset: float = 0.0,
    include_text: bool = True,
) -> BBox | None:
    """Return the box a pin occupies, or None when the pin is hidden.

    The pin line runs from the connection point at ``pin.position`` along
    ``pin.angle`` for ``pin.length``. Angle 0 points right, 90 up.

    ``name_offset`` is the symbol's ``pin_names`` offset. Above 0, KiCad sets
    the name inside the body, that far past the end of the pin line. At 0, it
    sets the name beside the line, outside the body.
    """
    if not pin.visible:
        return None

    radians = math.radians(pin.angle)
    ax, ay = math.cos(radians), math.sin(radians)
    tip_x, tip_y = pin.position
    end = (tip_x + pin.length * ax, tip_y + pin.length * ay)
    box = BBox.from_points([(tip_x, tip_y), end])
    if box is None or not include_text:
        return box

    middle = ((tip_x + end[0]) / 2, (tip_y + end[1]) / 2)
    parts: list[BBox | None] = [box]

    if show_numbers and pin.number:
        parts.append(_beside_axis(middle, (ax, ay), pin.number, pin.number_text_size))

    if show_names and pin.name and pin.name != NO_PIN_NAME:
        if name_offset > 0:
            width, height = text_extent(pin.name, (pin.name_text_size,) * 2)
            px, py = -ay, ax
            parts.append(
                BBox.from_points(
                    (
                        end[0] + reach * ax + across * height / 2 * px,
                        end[1] + reach * ay + across * height / 2 * py,
                    )
                    for reach in (name_offset, name_offset + width)
                    for across in (-1, 1)
                )
            )
        else:
            parts.append(_beside_axis(middle, (ax, ay), pin.name, pin.name_text_size))

    return union(parts)


# ----------------------------------------------------------------------
# Fields
# ----------------------------------------------------------------------


def field_bbox(field: Any) -> BBox | None:
    """Return the box a symbol field occupies, or None when it is hidden."""
    attributes = _attributes_of(field)
    if not field.visible or not attributes.visible:
        return None
    content = f"{field.name}: {field.value}" if field.show_name else field.value
    return text_bbox(
        content,
        field.position,
        attributes.font_size,
        angle_deg=field.angle,
        justify_h=attributes.justify_h,
        justify_v=attributes.justify_v,
    )


# ----------------------------------------------------------------------
# Symbols
# ----------------------------------------------------------------------


def _selected_units(
    symbol: Any,
    unit: int | None,
    body_style: int | None,
) -> Iterator[Any]:
    """Yield the units a schematic draws for the requested unit and body style.

    Index 0 means "common to every unit", or "common to every body style", so
    it is always drawn.
    """
    for sub in symbol.units:
        if unit is not None and sub.unit_index not in (0, unit):
            continue
        if body_style is not None and sub.body_style_index not in (0, body_style):
            continue
        yield sub


def symbol_bbox(
    symbol: Any,
    *,
    parent: Any = None,
    unit: int | None = None,
    body_style: int | None = None,
    include_fields: bool = True,
    include_pin_text: bool = True,
) -> BBox | None:
    """Return the box ``symbol`` occupies on a sheet. None when it draws nothing.

    ``unit`` and ``body_style`` select what a sheet shows. None takes every
    unit and every body style at once, which is the largest answer and the one
    to use when asking "how much room does this symbol need".

    A derived symbol (one with ``extends``) holds no drawing of its own. Pass
    the symbol that holds the drawing as ``parent``, or use
    :func:`library_bboxes`, which finds it in the same library. A chain of
    ``extends`` must already be followed to its root: ``parent`` is used as
    given.

    ``include_fields`` counts the Reference, the Value, and any other visible
    field. A long value string can be wider than the drawing, so turn this off
    to measure the body alone.
    """
    drawing = parent if (parent is not None and symbol.extends) else symbol
    show_names = drawing.show_pin_names
    show_numbers = drawing.show_pin_numbers
    name_offset = drawing.pin_name_offset or 0.0

    parts: list[BBox | None] = []
    for sub in _selected_units(drawing, unit, body_style):
        for item in sub.items:
            if type(item).__name__ == "Pin":
                parts.append(
                    pin_bbox(
                        item,
                        show_names=show_names,
                        show_numbers=show_numbers,
                        name_offset=name_offset,
                        include_text=include_pin_text,
                    )
                )
            elif type(item).__name__ in ("SymText", "SymTextBox"):
                parts.append(text_item_bbox(item))
            else:
                parts.append(shape_bbox(item))

    if include_fields:
        parts.extend(field_bbox(field) for field in symbol.fields)

    return union(parts)


def _root_drawing(symbol: Any, by_name: dict[str, Any]) -> Any:
    """Follow ``extends`` to the symbol that holds the drawing.

    A chain can be more than one link long, and a broken or looping chain must
    not hang the caller, so a name already seen ends the walk.

    **The lookup is verbatim, and ``kicad-file-io``'s own resolver is not.** Both sides come
    from the loader unchanged, so a stored name matches a stored ``extends`` value.
    ``kicad-file-io`` 0.10.0 unescapes ``{slash}`` and falls back to a bare-name index
    before it gives up, so a legacy symbol named ``A/B`` that extends ``A{slash}B``
    resolves in ``kicad-file-io`` and not here. That symbol holds no units, so this function
    returns it and the measurement covers its own fields alone. No measured library asset
    carries ``{slash}``, and this tool never writes, so the divergence is recorded
    rather than repaired. ADR-082, and section 9 of
    ``context/audit/fileio-report-0.10.0-symbol-dcm-surface-2026-08-18.md``.
    """
    seen = {symbol.name}
    current = symbol
    while current.extends:
        parent = by_name.get(current.extends)
        if parent is None or parent.name in seen:
            break
        seen.add(parent.name)
        current = parent
    return current


def library_bboxes(
    lib: Any,
    **options: Any,
) -> dict[str, BBox | None]:
    """Return the box of every symbol in a library, keyed by symbol name.

    A derived symbol is measured against the symbol it extends, through as many
    links of ``extends`` as the symbol library uses. Every keyword of
    :func:`symbol_bbox` is accepted and passed through.
    """
    by_name = {symbol.name: symbol for symbol in lib.symbols}
    boxes: dict[str, BBox | None] = {}
    for symbol in lib.symbols:
        parent = _root_drawing(symbol, by_name) if symbol.extends else None
        boxes[symbol.name] = symbol_bbox(symbol, parent=parent, **options)
    return boxes


def file_bboxes(path: str | Path, **options: Any) -> dict[str, BBox | None]:
    """Return the box of every symbol in a ``.kicad_sym`` file, by symbol name."""
    return library_bboxes(SymbolLib.from_file(Path(path)), **options)


# ----------------------------------------------------------------------
# Command line
# ----------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    """Print the bounding box of every symbol in each file given."""
    parser = argparse.ArgumentParser(
        prog="python -m eedesignsymbols.bbox",
        description="Print the schematic bounding box of every symbol in a .kicad_sym file.",
    )
    parser.add_argument("files", nargs="+", type=Path, help="One or more .kicad_sym files.")
    parser.add_argument("--unit", type=int, default=None, help="Measure this unit only.")
    parser.add_argument(
        "--body-style", type=int, default=None, help="Measure this body style only."
    )
    parser.add_argument(
        "--no-fields", action="store_true", help="Leave the visible fields out of the box."
    )
    parser.add_argument(
        "--no-pin-text", action="store_true", help="Leave pin names and numbers out of the box."
    )
    args = parser.parse_args(argv)

    failed = False
    for path in args.files:
        print(path)
        try:
            boxes = file_bboxes(
                path,
                unit=args.unit,
                body_style=args.body_style,
                include_fields=not args.no_fields,
                include_pin_text=not args.no_pin_text,
            )
        except (OSError, ValueError) as error:
            print(f"  ERROR: {error}", file=sys.stderr)
            failed = True
            continue
        for name, box in boxes.items():
            print(f"  {name}: {box if box is not None else 'nothing visible'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_STROKE_WIDTH",
    "GLYPH_ADVANCE",
    "LINE_PITCH",
    "BBox",
    "field_bbox",
    "file_bboxes",
    "library_bboxes",
    "pin_bbox",
    "shape_bbox",
    "symbol_bbox",
    "text_bbox",
    "text_extent",
    "text_item_bbox",
    "union",
]
