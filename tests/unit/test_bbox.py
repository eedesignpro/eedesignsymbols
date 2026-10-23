"""The bounding box helper, checked against a real library asset and hand-built parts.

The golden NMOS template is drawn on a known grid, so its box can be worked out
by hand: the three pin tips sit at +-5.08, and the body circle reaches
1.651 + 2.794 = 4.445, plus half of its 0.254 stroke.
"""

from pathlib import Path
from typing import Any

import pytest
from eedesigncore.common.models import JustifyH, JustifyV, Property, Stroke, TextAttributes
from eedesigncore.sym import (
    Pin,
    PinElectricalType,
    PinShape,
    SchArc,
    SchCircle,
    SchPolyline,
    SchRect,
    Symbol,
    SymbolLib,
    SymbolUnit,
    SymText,
    SymTextBox,
)

from eedesignsymbols.bbox import (
    BBox,
    field_bbox,
    file_bboxes,
    library_bboxes,
    main,
    pin_bbox,
    shape_bbox,
    symbol_bbox,
    text_bbox,
    text_extent,
    text_item_bbox,
    union,
)

GATE_TIP_X = -5.08
BODY_RIGHT = 4.445 + 0.127  # circle edge plus half its stroke
PIN_TIP_Y = 5.08


def approx(box: BBox) -> tuple[float, float, float, float]:
    """The four edges, rounded, so a comparison reads as one line."""
    rounded = box.rounded(3)
    return (rounded.min_x, rounded.min_y, rounded.max_x, rounded.max_y)


# ----------------------------------------------------------------------
# BBox itself
# ----------------------------------------------------------------------


def test_from_points_returns_none_for_no_points() -> None:
    assert BBox.from_points([]) is None


def test_from_points_spans_every_point() -> None:
    box = BBox.from_points([(1, 2), (-3, 7), (0, 0)])
    assert box is not None
    assert approx(box) == (-3, 0, 1, 7)


def test_union_ignores_none() -> None:
    box = union([None, BBox(0, 0, 1, 1), None, BBox(-1, 5, 0, 6)])
    assert box is not None
    assert approx(box) == (-1, 0, 1, 6)


def test_union_of_nothing_is_none() -> None:
    assert union([None, None]) is None


def test_or_is_union() -> None:
    assert BBox(0, 0, 1, 1) | BBox(-1, 5, 0, 6) == BBox(-1, 0, 1, 6)


def test_width_height_and_center() -> None:
    box = BBox(-2, -4, 4, 4)
    assert (box.width, box.height) == (6, 8)
    assert box.center == (1, 0)


def test_grown_adds_the_margin_on_four_sides() -> None:
    assert approx(BBox(0, 0, 1, 1).grown(0.5)) == (-0.5, -0.5, 1.5, 1.5)


# ----------------------------------------------------------------------
# Text
# ----------------------------------------------------------------------


def test_text_extent_counts_the_widest_line() -> None:
    width, height = text_extent("ab\nabcd", (1.0, 1.0))
    assert width == pytest.approx(4 * 0.72)
    assert height == pytest.approx(1 + 1.6)


def test_empty_text_draws_nothing() -> None:
    assert text_bbox("", (0, 0), (1.27, 1.27)) is None


def test_left_justified_text_runs_right_from_the_anchor() -> None:
    box = text_bbox("AB", (1.0, 0.0), (1.0, 1.0), justify_h=JustifyH.left)
    assert box is not None
    assert approx(box) == (1.0, -0.5, 1.0 + round(2 * 0.72, 3), 0.5)


def test_right_justified_text_runs_left_from_the_anchor() -> None:
    box = text_bbox("AB", (0.0, 0.0), (1.0, 1.0), justify_h=JustifyH.right)
    assert box is not None
    assert approx(box) == (-round(2 * 0.72, 3), -0.5, 0.0, 0.5)


def test_top_justified_text_hangs_below_the_anchor() -> None:
    box = text_bbox("A", (0.0, 0.0), (1.0, 1.0), justify_v=JustifyV.top)
    assert box is not None
    assert approx(box)[1:4:2] == (-1.0, 0.0)


def test_bottom_justified_text_stands_above_the_anchor() -> None:
    box = text_bbox("A", (0.0, 0.0), (1.0, 1.0), justify_v=JustifyV.bottom)
    assert box is not None
    assert approx(box)[1:4:2] == (0.0, 1.0)


def test_rotating_text_by_90_degrees_swaps_its_sides() -> None:
    flat = text_bbox("ABCD", (0.0, 0.0), (1.0, 1.0))
    turned = text_bbox("ABCD", (0.0, 0.0), (1.0, 1.0), angle_deg=90)
    assert flat is not None and turned is not None
    assert turned.width == pytest.approx(flat.height)
    assert turned.height == pytest.approx(flat.width)


# ----------------------------------------------------------------------
# Shapes
# ----------------------------------------------------------------------


def test_circle_box_is_the_square_around_it() -> None:
    box = shape_bbox(SchCircle(center=(1.0, 0.0), radius=2.0, stroke=Stroke(width=0.2)))
    assert box is not None
    assert approx(box) == (-1.1, -2.1, 3.1, 2.1)


def test_stroke_width_zero_uses_the_kicad_default() -> None:
    box = shape_bbox(SchRect(start=(0, 0), end=(1, 1)))
    assert box is not None
    assert approx(box) == (-0.076, -0.076, 1.076, 1.076)


def test_rectangle_box_survives_reversed_corners() -> None:
    box = shape_bbox(SchRect(start=(2, 3), end=(0, 1), stroke=Stroke(width=0.0001)))
    assert box is not None
    assert approx(box) == (0, 1, 2, 3)


def test_arc_box_spans_start_mid_and_end() -> None:
    arc = SchArc(start=(-1, 0), mid=(0, 1), end=(1, 0), stroke=Stroke(width=0.0001))
    box = shape_bbox(arc)
    assert box is not None
    assert approx(box) == (-1, 0, 1, 1)


def test_private_shape_draws_nothing() -> None:
    shape = SchPolyline(pts=[(0, 0), (10, 10)], private=True)
    assert shape_bbox(shape) is None


# ----------------------------------------------------------------------
# Free text and text boxes
# ----------------------------------------------------------------------


def test_free_text_is_measured_from_its_string() -> None:
    box = text_item_bbox(SymText(content="AB", position=(0.0, 0.0)))
    assert box is not None
    assert box.width == pytest.approx(2 * 1.27 * 0.72)
    assert box.height == pytest.approx(1.27)


def test_free_text_angle_is_read_as_tenths_of_a_degree() -> None:
    flat = text_item_bbox(SymText(content="ABCD", position=(0.0, 0.0)))
    turned = text_item_bbox(SymText.from_degrees(90, content="ABCD", position=(0.0, 0.0)))
    assert flat is not None and turned is not None
    assert turned.width == pytest.approx(flat.height)


def test_hidden_text_item_draws_nothing() -> None:
    text = SymText(content="X", position=(9, 9), attributes=TextAttributes(visible=False))
    assert text_item_bbox(text) is None


def test_private_text_item_draws_nothing() -> None:
    assert text_item_bbox(SymText(content="X", position=(9, 9), private=True)) is None


def test_text_box_is_measured_from_its_own_size() -> None:
    box = text_item_bbox(SymTextBox(content="anything", position=(1.0, 2.0), size=(10.0, 5.0)))
    assert box is not None
    assert approx(box) == (1.0, 2.0, 11.0, 7.0)


# ----------------------------------------------------------------------
# Pins
# ----------------------------------------------------------------------


def a_pin(**overrides: Any) -> Pin:
    """A passive pin at the origin, pointing right, with no text."""
    defaults: dict[str, Any] = {
        "electrical_type": PinElectricalType.passive,
        "shape": PinShape.line,
        "position": (0.0, 0.0),
        "angle": 0.0,
        "length": 2.54,
        "name": "~",
        "number": "",
    }
    defaults.update(overrides)
    return Pin(**defaults)


def test_pin_at_angle_zero_runs_right_from_its_tip() -> None:
    box = pin_bbox(a_pin(position=(-5.08, 1.27)))
    assert box is not None
    assert approx(box) == (-5.08, 1.27, -2.54, 1.27)


def test_pin_at_angle_90_runs_up_from_its_tip() -> None:
    box = pin_bbox(a_pin(position=(2.54, -5.08), angle=90))
    assert box is not None
    assert approx(box) == (2.54, -5.08, 2.54, -2.54)


def test_hidden_pin_draws_nothing() -> None:
    assert pin_bbox(a_pin(visible=False)) is None


def test_pin_named_tilde_adds_no_name_text() -> None:
    bare = pin_bbox(a_pin(name="~"))
    named = pin_bbox(a_pin(name="VCC"))
    assert bare is not None and named is not None
    assert named.height > bare.height


def test_pin_number_widens_the_box_on_both_sides() -> None:
    box = pin_bbox(a_pin(number="12"))
    assert box is not None
    # 1.27 mm of text above and below the pin line, which lies on y = 0.
    assert approx(box)[1:4:2] == (-1.27, 1.27)


def test_pin_text_can_be_left_out() -> None:
    box = pin_bbox(a_pin(number="12", name="VCC"), include_text=False)
    assert box is not None
    assert approx(box) == (0, 0, 2.54, 0)


def test_a_name_offset_puts_the_name_past_the_end_of_the_pin() -> None:
    box = pin_bbox(a_pin(name="VCC"), name_offset=0.508, show_numbers=False)
    assert box is not None
    # 2.54 pin + 0.508 offset + three characters at 1.27 mm.
    assert box.max_x == pytest.approx(2.54 + 0.508 + 3 * 1.27 * 0.72)


# ----------------------------------------------------------------------
# Fields
# ----------------------------------------------------------------------


def test_hidden_field_draws_nothing() -> None:
    assert field_bbox(Property(name="Footprint", value="R_0402", visible=False)) is None


def test_visible_field_is_measured_from_its_value() -> None:
    field = Property(
        name="Reference",
        value="Q",
        position=(5.08, -1.27),
        visible=True,
        attributes=TextAttributes(justify_h=JustifyH.left),
    )
    box = field_bbox(field)
    assert box is not None
    assert box.min_x == pytest.approx(5.08)
    assert box.max_x == pytest.approx(5.08 + 1.27 * 0.72)


def test_show_name_makes_the_field_wider() -> None:
    plain = Property(name="Reference", value="Q", visible=True)
    labelled = Property(name="Reference", value="Q", visible=True, show_name=True)
    plain_box, labelled_box = field_bbox(plain), field_bbox(labelled)
    assert plain_box is not None and labelled_box is not None
    assert labelled_box.width > plain_box.width


# ----------------------------------------------------------------------
# Symbols
# ----------------------------------------------------------------------


def test_symbol_with_nothing_visible_has_no_box() -> None:
    symbol = Symbol(name="EMPTY")
    assert symbol_bbox(symbol) is None


def test_unit_selection_leaves_other_units_out() -> None:
    symbol = Symbol(name="U")
    symbol.units = [
        SymbolUnit.for_symbol("U", unit_index=1, items=[SchRect(start=(0, 0), end=(1, 1))]),
        SymbolUnit.for_symbol("U", unit_index=2, items=[SchRect(start=(50, 50), end=(51, 51))]),
    ]
    everything = symbol_bbox(symbol, include_fields=False)
    first = symbol_bbox(symbol, unit=1, include_fields=False)
    assert everything is not None and first is not None
    assert everything.max_x > 50
    assert first.max_x < 2


def test_body_style_selection_leaves_the_other_style_out() -> None:
    symbol = Symbol(name="U")
    symbol.units = [
        SymbolUnit.for_symbol("U", body_style_index=1, items=[SchRect(start=(0, 0), end=(1, 1))]),
        SymbolUnit.for_symbol(
            "U", body_style_index=2, items=[SchRect(start=(50, 50), end=(51, 51))]
        ),
    ]
    box = symbol_bbox(symbol, body_style=1, include_fields=False)
    assert box is not None
    assert box.max_x < 2


def test_unit_zero_is_drawn_with_every_unit() -> None:
    symbol = Symbol(name="U")
    symbol.units = [
        SymbolUnit.for_symbol("U", unit_index=0, items=[SchRect(start=(0, 0), end=(1, 1))]),
        SymbolUnit.for_symbol("U", unit_index=2, items=[SchRect(start=(50, 50), end=(51, 51))]),
    ]
    box = symbol_bbox(symbol, unit=2, include_fields=False)
    assert box is not None
    assert box.min_x < 0.1


# ----------------------------------------------------------------------
# The golden asset
# ----------------------------------------------------------------------


def test_golden_template_body_matches_the_drawing(golden_nmos: Path) -> None:
    """Body alone: gate pin tip on the left, circle on the right, pin tips top and bottom."""
    boxes = file_bboxes(golden_nmos, include_fields=False)
    box = next(iter(boxes.values()))
    assert box is not None
    assert approx(box) == (
        GATE_TIP_X,
        -PIN_TIP_Y,
        round(BODY_RIGHT, 3),
        PIN_TIP_Y,
    )


def test_golden_template_fields_widen_the_box(golden_nmos: Path) -> None:
    """The Value field carries the long versioned name, so it reaches past the body."""
    with_fields = next(iter(file_bboxes(golden_nmos).values()))
    body = next(iter(file_bboxes(golden_nmos, include_fields=False).values()))
    assert with_fields is not None and body is not None
    assert with_fields.max_x > body.max_x
    assert with_fields.min_x == body.min_x


def test_hidden_pin_names_are_not_counted(golden_nmos: Path) -> None:
    """The template sets ``pin_names (hide yes)``, so no pin name is drawn.

    A name long enough to reach past the body proves the flag is read: the box
    only grows once the symbol says it shows names.
    """
    lib = SymbolLib.from_file(golden_nmos)
    symbol = lib.symbols[0]
    assert symbol.show_pin_names is False
    body = symbol_bbox(symbol, include_fields=False)

    symbol.units[-1].items[0].name = "A_VERY_LONG_PIN_NAME"
    hidden = symbol_bbox(symbol, include_fields=False)
    symbol.show_pin_names = True
    shown = symbol_bbox(symbol, include_fields=False)

    assert body is not None and hidden is not None and shown is not None
    assert hidden == body
    assert shown.height > body.height


def test_derived_symbol_is_measured_against_its_parent(golden_nmos: Path) -> None:
    lib = SymbolLib.from_file(golden_nmos)
    parent = lib.symbols[0]
    child = Symbol.new("CHILD")
    child.extends = parent.name
    lib.symbols.append(child)

    boxes = library_bboxes(lib, include_fields=False)
    assert boxes["CHILD"] == boxes[parent.name]


def test_a_broken_extends_chain_does_not_hang(golden_nmos: Path) -> None:
    lib = SymbolLib.from_file(golden_nmos)
    orphan = Symbol.new("ORPHAN")
    orphan.extends = "NOT_IN_THIS_LIBRARY"
    lib.symbols.append(orphan)
    assert library_bboxes(lib, include_fields=False)["ORPHAN"] is None


def test_free_text_in_a_unit_reaches_the_symbol_box() -> None:
    symbol = Symbol(name="U")
    symbol.units = [
        SymbolUnit.for_symbol("U", items=[SymText(content="NOTE", position=(20.0, 0.0))])
    ]
    box = symbol_bbox(symbol, include_fields=False)
    assert box is not None
    assert box.max_x > 20.0


# ----------------------------------------------------------------------
# Command line
# ----------------------------------------------------------------------


def test_cli_prints_a_box_per_symbol(
    golden_nmos: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(golden_nmos)]) == 0
    out = capsys.readouterr().out
    assert golden_nmos.name in out
    assert "_Q_NMOS_SYMGEN_TEMPLATE__1786580778623:" in out
    assert "mm]" in out


def test_cli_reports_a_bad_file_and_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken.kicad_sym"
    broken.write_text("(not_a_symbol_lib", encoding="utf-8")
    assert main([str(broken)]) == 1
    assert "ERROR" in capsys.readouterr().err
