"""BJT pin-order permutations: base, collector, emitter across pins 1 to 3.

Six symbols per template. The mechanics live in
:mod:`eedesignsymbols.generators.pinout`; this module is the configuration.

    ``_Q_NPN_SYMGEN_TEMPLATE``  ->  ``Q_NPN_BCE``  (pin 1 = B, 2 = C, 3 = E)

WHAT THIS GENERATES

Two declared templates, six declared orderings each, so twelve symbols:

==========================  =========================================
``_Q_NPN_SYMGEN_TEMPLATE``  ``Q_NPN_`` + BCE BEC CBE CEB EBC ECB
``_Q_PNP_SYMGEN_TEMPLATE``  ``Q_PNP_`` + BCE BEC CBE CEB EBC ECB
==========================  =========================================

Nothing else. A template outside that list is not generated here even if its
pins are B, C, E, which is what ADR-010 requires: the configuration decides what
is generated, and the pin names are checked as validation rather than used as
selection. A declared template that resolves to no file stops the run.

RERUN THIS GENERATOR
--------------------
Every declared template is generated. A file that already holds the same content
is left alone, and any other is overwritten. Safe to paste as often as you like::

    .venv\\Scripts\\python.exe -m eedesignsymbols.generators.bjt --dir "<output dir>"

Add ``--dry-run`` to see what it would do without writing.

A run that writes also builds an HTML preview gallery of the symbols it wrote,
under ``./.preview`` by default and never inside ``--dir``. Add
``--no-preview`` to skip it, or ``--preview-dir`` to move it.
"""  # noqa: E501

from __future__ import annotations

import sys
from collections.abc import Sequence

from eedesignsymbols.generators.pinout import Family, GeneratorError, PinOrder, pins_of, run

TERMINALS = ("B", "C", "E")
"""Base, collector, emitter."""

TEMPLATES = (
    "_Q_NPN_SYMGEN_TEMPLATE",
    "_Q_PNP_SYMGEN_TEMPLATE",
)
"""The templates this family consumes, by base name. See ADR-010."""

ORDERS = (
    PinOrder(("B", "C", "E")),
    PinOrder(("B", "E", "C")),
    PinOrder(("C", "B", "E")),
    PinOrder(("C", "E", "B")),
    PinOrder(("E", "B", "C")),
    PinOrder(("E", "C", "B")),
)
"""All six permutations, written out. See ADR-034 for why the list is complete."""

FAMILY = Family(name="bjt_pinout", terminals=TERMINALS, templates=TEMPLATES, orders=ORDERS)

GENERATOR = FAMILY.name

pin_orders = FAMILY.pin_orders
target_name = FAMILY.target_name
build = FAMILY.build
declared_templates = FAMILY.declared_templates
generate_all = FAMILY.generate_all


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point. See the rerun line at the top of this file."""
    return run(FAMILY, "eedesignsymbols.generators.bjt", argv)


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
