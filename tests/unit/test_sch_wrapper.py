"""Which units the preview renders, and how many files that produces.

The subject is `preview_tools.sch_wrapper`, not a generator, so this module reads
symbols rather than running a command.
"""

from pathlib import Path

import pytest
from eedesigncore import SymbolLib
from eedesigncore.sym import Symbol

from eedesignsymbols.generators.common import template_file
from eedesignsymbols.preview_tools import renderable_units


def units_of(path: Path) -> Symbol:
    """The one symbol in a `.kicad_sym` file."""
    return SymbolLib.from_file(path).symbols[0]


def with_unit_indices(golden: Path, indices: list[int]) -> Symbol:
    """Return a real symbol carrying one unit per entry in `indices`.

    Every golden asset here is a single-unit part, because ADR-008 keeps fixtures
    real and no multi-unit part has been adopted yet. Restamping the unit index on
    copies of a real unit covers the shapes no fixture provides, and keeps the
    argument a genuine `Symbol` rather than a stand-in.
    """
    symbol = units_of(golden)
    prototype = symbol.units[0]
    symbol.units = [prototype.model_copy(deep=True) for _ in indices]
    for unit, index in zip(symbol.units, indices, strict=True):
        unit.unit_index = index
    return symbol


class TestRenderableUnits:
    """One entry per real unit. Unit index 0 is the common-to-all-units layer."""

    def test_a_single_unit_part_renders_once(self):
        """A generated diode stores unit 0 (the body) and unit 1 (the pins).

        Both render the same drawing, because KiCad merges the common layer into
        whichever unit is placed. Rendering both produced two SVGs that differed
        only in the file name embedded in the SVG title.
        """
        symbol = units_of(template_file("_D_SI_SYMGEN_TEMPLATE"))
        stored = sorted({unit.unit_index for unit in symbol.units})

        assert 0 in stored
        assert renderable_units(symbol) == [1]

    def test_the_bidirectional_diode_renders_once_too(self):
        assert renderable_units(units_of(template_file("_D_TVS_BIDIR_SYMGEN_TEMPLATE"))) == [1]

    def test_a_transistor_template_renders_once(self, golden_nmos):
        assert renderable_units(units_of(golden_nmos)) == [1]


class TestItAdaptsToTheInput:
    """The count follows the symbol. It is not fixed at one."""

    @pytest.mark.parametrize(
        ("stored", "expected"),
        [
            ([0, 1], [1]),
            ([1], [1]),
            ([0, 1, 2], [1, 2]),
            ([1, 2, 3, 4], [1, 2, 3, 4]),
            ([0], [0]),
        ],
        ids=["common+one", "one-only", "common+two", "four-units", "common-only"],
    )
    def test_zero_drops_out_unless_it_is_the_only_one(self, golden_nmos, stored, expected):
        assert renderable_units(with_unit_indices(golden_nmos, stored)) == expected

    def test_a_repeated_index_is_counted_once(self, golden_nmos):
        """A symbol stores one entry per (unit, body style), so an index repeats."""
        symbol = with_unit_indices(golden_nmos, [0, 0, 1, 1, 2, 2])

        assert renderable_units(symbol) == [1, 2]

    def test_the_result_is_sorted(self, golden_nmos):
        assert renderable_units(with_unit_indices(golden_nmos, [3, 1, 2])) == [1, 2, 3]
