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

ANODE FIRST

Only ``AK`` is generated. A survey of 20 two-pin single diodes in the previous
library found 19 with the anode on pin 1, and the single exception was named
``DIODE_ZENER_Kp1_Ap2``: K-first was the case worth spelling out. Operator
ruling, 2026-08-14: a ``KA`` symbol is more likely a mistake than a part, so it
is not generated at all.

A template stores no ordering of its own. It carries pin *names*, this module
says which name gets which number, and ``kicad-file-io`` writes the result in
KiCad's own save order. Operator ruling 2026-08-17, ADR-038.

PARALLEL PINS

Real parts put the same terminal on several package pins: ``AAK`` (1=A 2=A 3=K)
on a power package, ``AKA`` (1=A 2=K 3=A) on a DPAK where the tab is the cathode.
Both are drawn on this same two-pin drawing, by stacking the extra pin on the
terminal it shares. That needs the pinout pattern of ADR-011, which maps a
terminal to a list of pin numbers rather than to one. Not implemented: a
:class:`~pinout.Family` refuses a repeated terminal rather than mis-numbering it.

RERUN THIS GENERATOR
--------------------
Every declared template is generated. A file that already holds the same content
is left alone, and any other is overwritten. Safe to paste as often as you like::

    .venv\\Scripts\\python.exe -m eedesignsymbols.generators.diode --dir "<output dir>"

Add ``--dry-run`` to see what it would do without writing.

A run that writes also builds an HTML preview gallery of the symbols it wrote,
under ``./.preview`` by default and never inside ``--dir``. Add
``--no-preview`` to skip it, or ``--preview-dir`` to move it.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from eedesignsymbols.generators.pinout import Family, GeneratorError, PinOrder, pins_of, run_many

ANODE_FIRST = PinOrder(("A", "K"))
"""Pin 1 = anode, pin 2 = cathode. The only ordering generated."""

BIDIRECTIONAL_ORDER = PinOrder(("A1", "A2"))
"""Pin 1 = A1, pin 2 = A2. Symmetric, so there is only one arrangement."""

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
    orders=(ANODE_FIRST,),
)
"""Anode and cathode. Six drawings, one symbol each."""

BIDIRECTIONAL = Family(
    name="diode_pinout",
    terminals=("A1", "A2"),
    templates=(
        "_D_ESD_BIDIR_SYMGEN_TEMPLATE",
        "_D_TVS_BIDIR_SYMGEN_TEMPLATE",
    ),
    orders=(BIDIRECTIONAL_ORDER,),
)
"""Two anodes. Two drawings, one symbol each."""

FAMILIES = (UNIDIRECTIONAL, BIDIRECTIONAL)

GENERATOR = UNIDIRECTIONAL.name


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point. See the rerun line at the top of this file."""
    return run_many(FAMILIES, "eedesignsymbols.generators.diode", argv)


__all__ = [
    "ANODE_FIRST",
    "BIDIRECTIONAL",
    "BIDIRECTIONAL_ORDER",
    "FAMILIES",
    "GENERATOR",
    "UNIDIRECTIONAL",
    "GeneratorError",
    "PinOrder",
    "main",
    "pins_of",
]


if __name__ == "__main__":
    sys.exit(main())
