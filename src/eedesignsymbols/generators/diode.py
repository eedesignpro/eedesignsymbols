"""Diode pin assignments: one drawing per diode type, one symbol per pinout.

Every single diode is the same two-terminal drawing, so what
separates one generated symbol from another is only which package pin carries
the anode and which carries the cathode. The mechanics live in
:mod:`eedesignsymbols.generators.pinout`; this module is the configuration.

    ``_D_SI_SYMGEN_TEMPLATE``  ->  ``D_SI_AK``  (pin 1 = A, 2 = K)

TWO FAMILIES

A unidirectional part has an anode and a cathode. A bidirectional one, a TVS or
an ESD clamp, is symmetric: both terminals are anodes, named ``A1`` and ``A2``.
The terminal sets differ, so they cannot be one :class:`~pinout.Family`, but they
are one part family to a librarian and share one command.

PIN ORDERS

Every unidirectional drawing gives two symbols: ``AK`` (pin 1 = A, 2 = K) and
``KA`` (pin 1 = K, 2 = A). Every bidirectional drawing gives two as well:
``A1A2`` (pin 1 = A1, 2 = A2) and ``KA`` (pin 1 = A2, 2 = A1). The bidirectional
``KA`` form keeps the symmetric terminal names and swaps their pin numbers.

A template stores no ordering of its own. It carries pin *names*, this module
says which name gets which number, and ``kicad-file-io`` writes the result in
KiCad's own save order. Operator ruling 2026-08-17, ADR-038.

PARALLEL PINS

Real parts put the same terminal on several package pins: ``AAK`` (1=A 2=A 3=K)
on a power package, ``AKA`` (1=A 2=K 3=A) on a DPAK where the tab is the cathode.
Both are drawn on this same two-pin drawing. A :class:`~pinout.PinOrder` with
``numbers`` gives one terminal a group of package pins, as the grouped-drain
MOSFET does. No diode declares such an ordering yet. A :class:`~pinout.Family`
refuses a repeated terminal rather than mis-numbering it.

RERUN THIS GENERATOR
--------------------
Every declared template is generated. A file that already holds the same content
is left alone, and any other is overwritten. Safe to paste as often as you like::

    .venv\\Scripts\\python.exe -m eedesignsymbols.generators.diode --dir "<output dir>"

Add ``--leds`` to generate the five color LEDs instead: amber, blue, green, red
and yellow, see :mod:`eedesignsymbols.generators.led`. Add ``--part KA_RED`` to
select one color. Without ``--leds`` the command generates the diodes only.

Add ``--dry-run`` to see what it would do without writing.

A run that writes also builds an HTML preview gallery of the symbols it wrote,
under ``./.preview`` by default and never inside ``--dir``. Add
``--no-preview`` to skip it, or ``--preview-dir`` to move it.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import replace

from eedesignsymbols.generators import led
from eedesignsymbols.generators.pinout import Family, GeneratorError, PinOrder, pins_of, run_many

ANODE_FIRST = PinOrder(("A", "K"))
"""Pin 1 = anode, pin 2 = cathode."""

CATHODE_FIRST = PinOrder(("K", "A"))
"""Pin 1 = cathode, pin 2 = anode."""

BIDIRECTIONAL_REVERSE = PinOrder(("A2", "A1"), name_code="KA")
"""Pin 1 = A2, pin 2 = A1, named ``KA`` to match the unidirectional form."""

BIDIRECTIONAL_ORDER = PinOrder(("A1", "A2"))
"""Pin 1 = A1, pin 2 = A2."""

UNIDIRECTIONAL = Family(
    name="diode_pinout",
    terminals=("A", "K"),
    templates=(
        "_D_ESD_UNI_SYMGEN_TEMPLATE",
        "_D_SCHOTTKY_SYMGEN_TEMPLATE",
        "_D_SI_SYMGEN_TEMPLATE",
        "_D_SIC_SYMGEN_TEMPLATE",
        "_D_TVS_UNI_SYMGEN_TEMPLATE",
        "_D_ZENER_SYMGEN_TEMPLATE",
    ),
    orders=(ANODE_FIRST, CATHODE_FIRST),
)
"""Anode and cathode. Six drawings, two pin orders each."""

BIDIRECTIONAL = Family(
    name="diode_pinout",
    terminals=("A1", "A2"),
    templates=(
        "_D_ESD_BIDIR_SYMGEN_TEMPLATE",
        "_D_TVS_BIDIR_SYMGEN_TEMPLATE",
    ),
    orders=(BIDIRECTIONAL_ORDER, BIDIRECTIONAL_REVERSE),
)
"""Two anodes. Two drawings, two pin orders each."""

LEDS = replace(led.FAMILY, orders=led.COLOR_ORDERS)
"""The five color LEDs, for ``--leds``. The LED family owns the LED template, so
this is that family with only its color orderings. The registry does not list it,
because the LED family already declares the template."""

FAMILIES = (UNIDIRECTIONAL, BIDIRECTIONAL)

GENERATOR = UNIDIRECTIONAL.name


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point. See the rerun line at the top of this file."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--leds", action="store_true")
    selection, remaining = parser.parse_known_args(argv)
    families = (LEDS,) if selection.leds else (UNIDIRECTIONAL, BIDIRECTIONAL)
    return run_many(families, "eedesignsymbols.generators.diode", remaining)


__all__ = [
    "ANODE_FIRST",
    "BIDIRECTIONAL",
    "BIDIRECTIONAL_ORDER",
    "BIDIRECTIONAL_REVERSE",
    "CATHODE_FIRST",
    "FAMILIES",
    "GENERATOR",
    "LEDS",
    "UNIDIRECTIONAL",
    "GeneratorError",
    "PinOrder",
    "main",
    "pins_of",
]


if __name__ == "__main__":
    sys.exit(main())
