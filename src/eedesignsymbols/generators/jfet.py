"""JFET pin-order permutations: gate, source, drain across pins 1 to 3.

Six symbols per template. The mechanics live in
:mod:`eedesignsymbols.generators.pinout`; this module is the configuration.

    ``_Q_NJFET_SYMGEN_TEMPLATE``  ->  ``Q_NJFET_GSD``  (pin 1 = G, 2 = S, 3 = D)

WHY THIS MODULE EXISTS

A JFET carries the same three terminals as a MOSFET, ``G``, ``S`` and ``D``, and
is drawn differently. While a family claimed a template by matching its pin
names (ADR-005), the MOSFET family therefore claimed both JFET templates and
stamped twelve JFET assets ``mosfet_pinout``. That is a record of a pipeline
that never produced them, and ADR-024 makes such a record permanent once the
asset locks. This module gives those twelve assets the generator that describes
them, before any provenance is written. See ADR-010 for the naming precedent:
one generator name per part family, so ``jfet_pinout``.

An existing asset's ``generator`` header token is not repaired by a rerun.
ADR-002 normalises provenance out of the comparison, so the outcome is
``unchanged``. The correction belongs to the metadata pass that writes
``_SYM.GENERATOR``.

WHAT THIS GENERATES

Two declared templates, six declared orderings each, so twelve symbols:

============================  ==========================================
``_Q_NJFET_SYMGEN_TEMPLATE``  ``Q_NJFET_`` + GSD GDS SGD SDG DGS DSG
``_Q_PJFET_SYMGEN_TEMPLATE``  ``Q_PJFET_`` + GSD GDS SGD SDG DGS DSG
============================  ==========================================

Nothing else. Because the terminals are shared with the MOSFET family, the
declared list is the only thing that keeps the two apart, and the family registry
proves that no template base name appears in two families.

RERUN THIS GENERATOR
--------------------
Every declared template is generated. A file that already holds the same content
is left alone, and any other is overwritten. Safe to paste as often as you like::

    .venv\\Scripts\\python.exe -m eedesignsymbols.generators.jfet --dir "<output dir>"

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
"""Gate, source, drain. The same three a MOSFET carries."""

TEMPLATES = (
    "_Q_NJFET_SYMGEN_TEMPLATE",
    "_Q_PJFET_SYMGEN_TEMPLATE",
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

FAMILY = Family(name="jfet_pinout", terminals=TERMINALS, templates=TEMPLATES, orders=ORDERS)

GENERATOR = FAMILY.name

pin_orders = FAMILY.pin_orders
target_name = FAMILY.target_name
build = FAMILY.build
declared_templates = FAMILY.declared_templates
generate_all = FAMILY.generate_all


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point. See the rerun line at the top of this file."""
    return run(FAMILY, "eedesignsymbols.generators.jfet", argv)


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
