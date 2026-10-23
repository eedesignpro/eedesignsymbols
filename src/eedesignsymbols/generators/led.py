"""LED pin assignments: one drawing, one symbol per pinout.

An LED is a two-terminal part drawn once, so what separates one generated symbol
from another is only which package pin carries the anode and which carries the
cathode. The mechanics live in :mod:`eedesignsymbols.generators.pinout`; this module
is the configuration.

    ``_D_LED_SYMGEN_TEMPLATE``     ->  ``D_LED_KA_SYMGEN``       (1=K 2=A)
    ``_D_LED_MP_SYMGEN_TEMPLATE``  ->  ``D_LED_MP_KAMP_SYMGEN``  (1=K 2=A 3=MP)

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

CATHODE FIRST, WHICH IS THE OPPOSITE OF THE PLAIN DIODE

:mod:`eedesignsymbols.generators.diode` generates anode-first only, and refuses to
generate ``KA`` at all: a survey of 20 two-pin single diodes found 19 with the
anode on pin 1, so a K-first plain diode is more likely a mistake than a part.
Operator ruling 2026-08-14, ADR-028.

**An LED is the other way round, and that is why it is its own family.** Operator
ruling 2026-09-01: the first generated LED carries the cathode on pin 1 and the
anode on pin 2. The two rulings do not conflict, because they are about different
parts. Reusing the diode family would have forced one ordering on both.

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

from eedesignsymbols.generators.pinout import Family, PinOrder, run_many

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

FAMILY = Family(
    name="led_pinout",
    terminals=("A", "K"),
    templates=("_D_LED_SYMGEN_TEMPLATE",),
    orders=(CATHODE_FIRST,),
)
"""Anode and cathode. One drawing, one symbol."""

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
    "FAMILIES",
    "FAMILY",
    "GENERATOR",
    "WITH_MOUNTING_PAD",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
