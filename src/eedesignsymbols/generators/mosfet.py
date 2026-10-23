"""MOSFET pin-order permutations: gate, source, drain across pins 1 to 3.

Six symbols per template. The mechanics live in
:mod:`eedesignsymbols.generators.pinout`; this module is the configuration.

    ``_Q_NMOS_SYMGEN_TEMPLATE``  ->  ``Q_NMOS_GSD``  (pin 1 = G, 2 = S, 3 = D)

WHAT THIS GENERATES

Two declared templates, six declared orderings each, so twelve symbols:

===========================  ==========================================
``_Q_NMOS_SYMGEN_TEMPLATE``  ``Q_NMOS_`` + GSD GDS SGD SDG DGS DSG
``_Q_PMOS_SYMGEN_TEMPLATE``  ``Q_PMOS_`` + GSD GDS SGD SDG DGS DSG
===========================  ==========================================

Nothing else. A template outside that list is not generated here even if its
pins are G, S, D, which is what ADR-010 requires: the configuration decides
what is generated, and the pin names are checked as validation rather than used
as selection. A declared template that resolves to no file stops the run.

The two JFET templates carry the same G/S/D pins and belong to
:mod:`eedesignsymbols.generators.jfet`, not here. Before ADR-010 landed this family
claimed them and stamped twelve JFET assets ``mosfet_pinout``.

RERUN THIS GENERATOR
--------------------
Every declared template is generated. A file that already holds the same content
is left alone, and any other is overwritten. Safe to paste as often as you like::

    .venv\\Scripts\\python.exe -m eedesignsymbols.generators.mosfet --dir "<output dir>"

Add ``--dry-run`` to see what it would do without writing.

A run that writes also builds an HTML preview gallery of the symbols it wrote,
under ``./.preview`` by default and never inside ``--dir``. Add
``--no-preview`` to skip it, or ``--preview-dir`` to move it.
"""  # noqa: E501

from __future__ import annotations

import sys
from collections.abc import Sequence

from eedesignsymbols.generators.pinout import Family, GeneratorError, PinOrder, pins_of, run

TERMINALS = ("G", "S", "D")
"""Gate, source, drain."""

TEMPLATES = (
    "_Q_NMOS_SYMGEN_TEMPLATE",
    "_Q_PMOS_SYMGEN_TEMPLATE",
)
"""The templates this family consumes, by base name. See ADR-010."""

ORDERS = (
    PinOrder(("G", "S", "D")),
    PinOrder(("G", "D", "S")),
    PinOrder(("S", "G", "D")),
    PinOrder(("S", "D", "G")),
    PinOrder(("D", "G", "S")),
    PinOrder(("D", "S", "G")),
)
"""All six permutations, written out. See ADR-034 for why the list is complete."""

FAMILY = Family(name="mosfet_pinout", terminals=TERMINALS, templates=TEMPLATES, orders=ORDERS)

GENERATOR = FAMILY.name

pin_orders = FAMILY.pin_orders
target_name = FAMILY.target_name
build = FAMILY.build
declared_templates = FAMILY.declared_templates
generate_all = FAMILY.generate_all


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point. See the rerun line at the top of this file."""
    return run(FAMILY, "eedesignsymbols.generators.mosfet", argv)


__all__ = [
    "FAMILY",
    "GENERATOR",
    "ORDERS",
    "TEMPLATES",
    "TERMINALS",
    "GeneratorError",
    "PinOrder",
    "build",
    "declared_templates",
    "generate_all",
    "main",
    "pin_orders",
    "pins_of",
    "target_name",
]


if __name__ == "__main__":
    sys.exit(main())
