"""IGBT pin-order permutations: gate, collector, emitter across pins 1 to 3.

Six symbols per template. The mechanics live in
:mod:`eedesignsymbols.generators.pinout`; this module is the configuration.

    ``_Q_NIGBT_SYMGEN_TEMPLATE``  ->  ``Q_NIGBT_GCE``  (pin 1 = G, 2 = C, 3 = E)

An IGBT shares the collector and emitter of a BJT but is gate driven, so its
terminal set is ``G``/``C``/``E`` where a BJT is ``B``/``C``/``E``.

WHAT THIS GENERATES

One declared template, six declared orderings, so six symbols:

============================  ======================================
``_Q_NIGBT_SYMGEN_TEMPLATE``  ``Q_NIGBT_`` + GCE GEC CGE CEG EGC ECG
============================  ======================================

Nothing else. A template outside that list is not generated here even if its
pins are G, C, E, which is what ADR-010 requires: the configuration decides what
is generated, and the pin names are checked as validation rather than used as
selection. A declared template that resolves to no file stops the run.

There is no P-channel IGBT template. The list holds one name, and adding a
second is a deliberate code change.

RERUN THIS GENERATOR
--------------------
Every declared template is generated. A file that already holds the same content
is left alone, and any other is overwritten. Safe to paste as often as you like::

    .venv\\Scripts\\python.exe -m eedesignsymbols.generators.igbt --dir "<output dir>"

Add ``--dry-run`` to see what it would do without writing.

A run that writes also builds an HTML preview gallery of the symbols it wrote,
under ``./.preview`` by default and never inside ``--dir``. Add
``--no-preview`` to skip it, or ``--preview-dir`` to move it.
"""  # noqa: E501

from __future__ import annotations

import sys
from collections.abc import Sequence

from eedesignsymbols.generators.pinout import Family, GeneratorError, PinOrder, pins_of, run

TERMINALS = ("G", "C", "E")
"""Gate, collector, emitter."""

TEMPLATES = ("_Q_NIGBT_SYMGEN_TEMPLATE",)
"""The templates this family consumes, by base name. See ADR-010."""

ORDERS = (
    PinOrder(("G", "C", "E")),
    PinOrder(("G", "E", "C")),
    PinOrder(("C", "G", "E")),
    PinOrder(("C", "E", "G")),
    PinOrder(("E", "G", "C")),
    PinOrder(("E", "C", "G")),
)
"""All six permutations, written out. See ADR-034 for why the list is complete."""

FAMILY = Family(name="igbt_pinout", terminals=TERMINALS, templates=TEMPLATES, orders=ORDERS)

GENERATOR = FAMILY.name

pin_orders = FAMILY.pin_orders
target_name = FAMILY.target_name
build = FAMILY.build
declared_templates = FAMILY.declared_templates
generate_all = FAMILY.generate_all


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point. See the rerun line at the top of this file."""
    return run(FAMILY, "eedesignsymbols.generators.igbt", argv)


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
