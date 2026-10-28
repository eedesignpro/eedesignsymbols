"""LED pin assignments: one drawing, one symbol per pinout.

An LED is a two-terminal part drawn once, so what separates one generated symbol
from another is only which package pin carries the anode and which carries the
cathode. The mechanics live in :mod:`eedesignsymbols.generators.pinout`; this module
is the configuration.

    ``_D_LED_SYMGEN_TEMPLATE``     ->  ``D_LED_KA_SYMGEN``       (1=K 2=A)
    ``_D_LED_SYMGEN_TEMPLATE``     ->  ``D_LED_KA_RED_SYMGEN``   (1=K 2=A, red arrows)
    ``_D_LED_MP_SYMGEN_TEMPLATE``  ->  ``D_LED_KAMP_SYMGEN``     (1=K 2=A 3=MP)

COLOR LEDS

The plain LED drawing also gives five color forms: amber, blue, green, red and
yellow. Each is the cathode-first LED with its two light arrows drawn in that
color, and its description names the color. The arrows are found by their exact
points, so a changed template stops the run rather than recolor a body line.
The diode command makes the same five with ``--leds``, see
:mod:`eedesignsymbols.generators.diode`.

TWO FAMILIES, BECAUSE THE TERMINAL SETS DIFFER

A plain LED has an anode and a cathode. The mounting-pad part adds a third
terminal, ``MP``, which is a passive pad rather than an electrical terminal of the
diode. The terminal sets differ, so they cannot be one
:class:`~pinout.Family`, but they are one part family to a librarian and share
one command. The diode generator splits the same way, for the same reason
(ADR-029).

Both are cathode first. Operator ruling, 2026-09-01: the mounting-pad part is
``K=1 A=2 MP=3``, so the pad takes the third pin and the first two match the
plain LED.

CATHODE FIRST ONLY

:mod:`eedesignsymbols.generators.diode` generates both orderings, anode first
(``AK``) and cathode first (``KA``), for every plain diode drawing.

**An LED is generated cathode first only.** Every generated LED carries the
cathode on pin 1 and the anode on pin 2. Reusing the diode family would have
given the LED both orderings.

A separate family is also what keeps the template out of the diode generator's
reach. A family claims a template by declaring it, not by matching pin names
(ADR-010), and ``_D_LED_SYMGEN_TEMPLATE`` carries the same A and K pins as every
plain diode template. Declared here, it belongs here.

WHY THE LED LIVES WITH THE OPTOELECTRONICS PARTS

The template sits in ``Optoelectronics_LEDs_Lasers``, not with the diodes. A
generator reads whatever directory ``--dir`` names, so a family is not tied to one
folder. Operator instruction, 2026-09-01.

RERUN THIS GENERATOR
--------------------
Every declared template is generated. A file that already holds the same content
is left alone, and any other is overwritten. Safe to paste as often as you like::

    .venv\\Scripts\\python.exe -m eedesignsymbols.generators.led --dir "<output dir>"

Add ``--dry-run`` to see what it would do without writing.

A run that writes also builds an HTML preview gallery of the symbols it wrote,
under ``./.preview`` by default and never inside ``--dir``. Add
``--no-preview`` to skip it, or ``--preview-dir`` to move it.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from eedesigncore import Color, SchPolyline, SymbolLib

from eedesignsymbols.generators.common import same_kind
from eedesignsymbols.generators.pinout import Family, GeneratorError, PinOrder, run_many
from eedesignsymbols.symbol_fields import DESCRIPTION_FIELD, set_field
from eedesignsymbols.writing import Route

CATHODE_FIRST = PinOrder(("K", "A"))
"""Pin 1 = cathode, pin 2 = anode. The only ordering generated.

Named for what it puts first, so it cannot be confused with
:data:`~eedesignsymbols.generators.diode.ANODE_FIRST`, which is the plain diode's
opposite rule.
"""

CATHODE_FIRST_WITH_PAD = PinOrder(("K", "A", "MP"))
"""Pin 1 = cathode, pin 2 = anode, pin 3 = mounting pad. The only ordering generated.

The same cathode-first rule as :data:`CATHODE_FIRST`, with the mounting pad added
as the third pin. Operator ruling, 2026-09-01.
"""

LED_COLORS: dict[str, tuple[int, int, int]] = {
    "KA_AMBER": (255, 153, 0),
    "KA_BLUE": (0, 0, 255),
    "KA_GREEN": (0, 194, 0),
    "KA_RED": (255, 0, 0),
    "KA_YELLOW": (255, 255, 0),
}
"""Pinout code to the red, green and blue values of the light arrows."""

LED_ARROW_PATHS = (
    ((-2.794, 0.508), (-4.318, 2.032), (-3.556, 2.032), (-4.318, 2.032), (-4.318, 1.27)),
    ((-1.524, 0.508), (-3.048, 2.032), (-2.286, 2.032), (-3.048, 2.032), (-3.048, 1.27)),
)
"""The points of the two light arrows in ``_D_LED_SYMGEN_TEMPLATE``. A color form
recolors each one. Each must occur exactly once, so a changed template stops the
run rather than recolor a body line."""

COLOR_ORDERS = tuple(
    PinOrder(
        ("K", "A"),
        name_code=code,
        previous_names=(f"D_LED_KA_SYMGEN_{code.removeprefix('KA_')}",),
    )
    for code in LED_COLORS
)
"""Cathode first, one ordering per color. The code names the color."""


class LedFamily(Family):
    """A pinout family that also colors the light arrows of a color form."""

    def build(
        self,
        template: SymbolLib,
        order: PinOrder,
        *,
        tool_version: str | None = None,
        route: Route | None = None,
    ) -> SymbolLib:
        lib = super().build(template, order, tool_version=tool_version, route=route)
        if order.code not in LED_COLORS:
            return lib
        symbol = lib.symbols[0]
        red, green, blue = LED_COLORS[order.code]
        for points in LED_ARROW_PATHS:
            matches = [
                item
                for unit in symbol.units
                for item in unit.items
                if same_kind(item, SchPolyline) and tuple(item.pts) == points
            ]
            if len(matches) != 1:
                raise GeneratorError(
                    "The LED template must contain each declared emission arrow once."
                )
            matches[0].stroke.color = Color(r=red, g=green, b=blue, a=1.0)
        color_name = order.code.removeprefix("KA_").lower()
        set_field(symbol, DESCRIPTION_FIELD, f"{color_name.capitalize()} LED (pins {order})")
        return lib


FAMILY = LedFamily(
    name="led_pinout",
    terminals=("A", "K"),
    templates=("_D_LED_SYMGEN_TEMPLATE",),
    orders=(CATHODE_FIRST, *COLOR_ORDERS),
)
"""Anode and cathode. One drawing: the plain LED and five color forms."""

WITH_MOUNTING_PAD = Family(
    name="led_pinout",
    terminals=("A", "K", "MP"),
    templates=("_D_LED_MP_SYMGEN_TEMPLATE",),
    orders=(CATHODE_FIRST_WITH_PAD,),
    output_base="D_LED",
)
"""Anode, cathode and mounting pad. One drawing, one symbol."""

FAMILIES = (FAMILY, WITH_MOUNTING_PAD)

GENERATOR = FAMILY.name


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point. See the rerun line at the top of this file."""
    return run_many(FAMILIES, "eedesignsymbols.generators.led", argv)


__all__ = [
    "CATHODE_FIRST",
    "CATHODE_FIRST_WITH_PAD",
    "COLOR_ORDERS",
    "FAMILIES",
    "FAMILY",
    "GENERATOR",
    "LED_ARROW_PATHS",
    "LED_COLORS",
    "LedFamily",
    "WITH_MOUNTING_PAD",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
