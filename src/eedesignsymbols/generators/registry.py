"""Every family in the package, in one place, and the checks that need all of them.

A generator module is configuration for one part family and knows nothing about
the others. Two questions cannot be answered inside one module:

1. **Is any template claimed twice?** ADR-010 moved template selection into the
   configuration, which removes the accidental claiming that pin matching allowed
   and replaces it with a new way to be wrong: two families can now name the same
   template. That would generate two sets of symbols from one drawing, each
   stamped with a different generator, and each rerun would fight the other.
   A JFET template carries the same G/S/D pins as a MOSFET template, so this is
   not a hypothetical.
2. **Which family owns a given template?** Needed to report a template that no
   family declares, which is the quiet failure in the direction ADR-010 did not
   guard. See BS-27.

The table below is written by hand, deliberately, exactly as a family's template
list is. Nothing sweeps the package: a sweep is the mechanism this iteration
removed. What stops a new generator from escaping the table is a test, which
walks every module under :mod:`eedesignsymbols.generators` and fails when one
declares a family that is not listed here.

:func:`check_no_shared_template` runs on import, so a collision is a hard failure
in every process that touches a generator rather than something a caller has to
remember to ask for. It compares a hand-written table against itself, so it
cannot fail for an environmental reason.

:func:`unowned_templates` answers the second question against a real directory, and
:func:`main` prints the answer. It is informational and exits zero: three templates
in the live library are declared by nothing today and all three wait on ADR-011, so
failing on one would fail a pipeline over a known and accepted state.

THE OUTPUT SIDE OF THE SAME TWO QUESTIONS

:func:`expected_outputs` names every output base name the package produces, and
:func:`unclaimed_outputs` names every marked asset in a directory that no family
produces. Together they are the producer-side report ADR-073 part 2 asks for.

This report is a cross-check for a librarian, not an input to a rename.

A file name may carry a trailing ``__<digits>`` version number, as in a library that
versions every symbol. The report ignores it when it compares names.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

from eedesignsymbols.generators import bjt, diode, igbt, jfet, led, mosfet
from eedesignsymbols.generators.common import is_output_name, without_version_tail
from eedesignsymbols.generators.pinout import TEMPLATE_FILE_GLOB, Family, GeneratorError

SYMBOL_EXTENSION = ".kicad_sym"
"""The file extension of a symbol library file."""


def base_name(stem: str) -> str:
    """Return a file stem without a trailing ``__<digits>`` version number."""
    return without_version_tail(stem)


def stem_of(path: Path) -> str:
    """Return the file name without its extension."""
    return path.stem


FamilyEntry = tuple[str, Family]
"""A family and the short name of the module that declares it."""

FAMILIES: tuple[FamilyEntry, ...] = (
    ("bjt", bjt.FAMILY),
    ("diode", diode.UNIDIRECTIONAL),
    ("diode", diode.BIDIRECTIONAL),
    ("igbt", igbt.FAMILY),
    ("jfet", jfet.FAMILY),
    ("led", led.FAMILY),
    ("led", led.WITH_MOUNTING_PAD),
    ("mosfet", mosfet.FAMILY),
)
"""Every family this package declares. Add a new generator's families here."""

GENERATOR_MODULES: tuple[str, ...] = tuple(sorted({module for module, _ in FAMILIES}))
"""The modules that declare a family, derived from :data:`FAMILIES`."""


def describe(module: str, family: Family) -> str:
    """Name one family well enough to tell it from its siblings in a message.

    One module may declare several families that share a generator name, per
    ADR-029, so the name alone does not identify one. The terminals do.
    """
    return f"{module}.{family.name} ({'/'.join(family.terminals)})"


def check_no_shared_template(entries: Iterable[FamilyEntry] = FAMILIES) -> None:
    """Raise when one template base name is declared by two families.

    Args:
        entries: The families to check. Defaults to every family in the package.

    Raises:
        GeneratorError: A template is declared twice. The message names the
            template and every family that declares it.
    """
    owners: dict[str, list[str]] = {}
    for module, family in entries:
        for template in family.templates:
            owners.setdefault(template, []).append(describe(module, family))

    shared = {template: names for template, names in owners.items() if len(names) > 1}
    if shared:
        detail = "; ".join(
            f"{template} is declared by {' and '.join(names)}"
            for template, names in sorted(shared.items())
        )
        raise GeneratorError(
            f"a template may be declared by one family only: {detail}. "
            f"Two families generating from one drawing would each overwrite the other."
        )


def template_owners(entries: Iterable[FamilyEntry] = FAMILIES) -> dict[str, str]:
    """Map every declared template base name to the family that owns it.

    Raises:
        GeneratorError: A template is declared twice, so ownership is ambiguous.
    """
    entries = tuple(entries)
    check_no_shared_template(entries)
    return {
        template: describe(module, family)
        for module, family in entries
        for template in family.templates
    }


def owner_of(template_base: str, entries: Iterable[FamilyEntry] = FAMILIES) -> str | None:
    """Return the family that declares ``template_base``, or None when nothing does.

    ``template_base`` carries no version suffix. A template that nothing declares
    is legitimate today: three in the live library wait for ADR-011. See BS-27.
    """
    return template_owners(entries).get(template_base)


def declared_templates(entries: Iterable[FamilyEntry] = FAMILIES) -> tuple[str, ...]:
    """Every template base name any family declares, sorted and without duplicates."""
    return tuple(sorted(template_owners(entries)))


def unowned_templates(
    directory: Path | str,
    entries: Iterable[FamilyEntry] = FAMILIES,
) -> list[Path]:
    """Return every template file in ``directory`` that no family declares, sorted.

    BS-27, and the quiet failure in the direction ADR-010 did not guard.
    :func:`check_no_shared_template` catches a template two families claim; this
    catches one no family claims. A template nobody declares generates nothing, and
    without a report it looks exactly like a template that is working.

    **An unowned template is not an error.** Three in the live library are legitimate
    today and all three wait on ADR-011, so this reports and the command line exits
    zero. See :func:`main`.

    Matching is by base name, so every version of an unowned lineage is listed. That is
    deliberate: a librarian deciding what to do with the lineage wants to see how many
    files it has.

    **An empty result means one thing only.** Until iteration 4's correction pass a
    missing directory and a fully declared one both returned an empty list, because
    :meth:`pathlib.Path.glob` finds nothing in a directory that is not there. A
    caller could not tell "every template is declared" from "I looked in the wrong
    place", and the second reading is the shape that later becomes a silent gate
    pass. So a path that is not a directory raises. Low 3 of the iteration 4
    security review. :func:`main` already made the same check for itself.

    Args:
        directory: The directory to scan. Not written to.
        entries: The families to check. Defaults to every family in the package.

    Returns:
        Every matching path, sorted by name. An empty list means every template in
        ``directory`` is declared. A file whose name does not split into a base and a
        suffix is still reported, because its base name is the whole stem and no
        family declares that either.

    Raises:
        NotADirectoryError: ``directory`` does not exist, or names a file.
        GeneratorError: A template is declared twice, so ownership is ambiguous.
    """
    if not Path(directory).is_dir():
        raise NotADirectoryError(
            f"{directory} is not a directory, so no template can be found there. "
            f"An empty result means every template is declared, so this cannot be "
            f"reported as one."
        )
    owners = template_owners(entries)
    return sorted(
        (
            path
            for path in Path(directory).glob(TEMPLATE_FILE_GLOB)
            if base_name(stem_of(path)) not in owners
        ),
        key=lambda path: path.name,
    )


def expected_outputs(entries: Iterable[FamilyEntry] = FAMILIES) -> dict[str, str]:
    """Map every output base name the package produces to the family that produces it.

    ADR-073 part 2, producer side. One entry per declared template and declared
    ordering, so the count is the sum over families of templates times orders: 52
    today, being 12 mosfet, 12 bjt, 6 igbt, 12 jfet, 6 unidirectional diode, 2
    bidirectional diode, 1 LED and 1 mounting-pad LED.

    The name comes from :meth:`~eedesignsymbols.generators.pinout.Family.target_name`,
    which is the method the generator itself calls, so the report cannot disagree with
    what a run writes. Calling ``generated_name`` directly was the earlier reading, and
    it went wrong the moment a family set ``output_base``: the report kept naming
    ``D_LED_MP_KAMP_SYMGEN`` while a run wrote ``D_LED_KAMP_SYMGEN``.

    Args:
        entries: The families to report. Defaults to every family in the package.

    Returns:
        Base names without a version suffix, mapped to the value
        :func:`describe` gives for the producing family.

    Raises:
        GeneratorError: Two families produce one output name, so a run of each would
            overwrite the other. The output-side twin of
            :func:`check_no_shared_template`, which cannot catch it: two families
            declaring two different templates can still name one output.
    """
    entries = tuple(entries)
    check_no_shared_template(entries)

    producers: dict[str, list[str]] = {}
    for module, family in entries:
        for template in family.templates:
            for order in family.pin_orders():
                name = family.target_name(template, order)
                producers.setdefault(name, []).append(describe(module, family))

    shared = {name: owners for name, owners in producers.items() if len(set(owners)) > 1}
    if shared:
        detail = "; ".join(
            f"{name} is produced by {' and '.join(sorted(set(owners)))}"
            for name, owners in sorted(shared.items())
        )
        raise GeneratorError(
            f"an output name may be produced by one family only: {detail}. "
            f"Each run would overwrite the other's asset."
        )
    return {name: owners[0] for name, owners in producers.items()}


def unclaimed_outputs(
    directory: Path | str,
    entries: Iterable[FamilyEntry] = FAMILIES,
) -> list[Path]:
    """Return every marked asset in ``directory`` that no family produces, sorted.

    The output-side twin of :func:`unowned_templates`. A marked asset nobody produces
    is either an output whose family was deleted or an asset a human named as though a
    generator owned it, and both are stale: no rerun maintains it, and its name claims
    otherwise.

    **Not an error.** The live library holds none today, and the report exits zero for
    the same reason :func:`unowned_templates` does.

    Args:
        directory: The directory to scan. Not written to.
        entries: The families to report. Defaults to every family in the package.

    Returns:
        Every matching path, sorted by name. An empty list means every marked asset in
        ``directory`` is produced by a declared family.

    Raises:
        NotADirectoryError: ``directory`` does not exist, or names a file. An empty
            result must mean one thing only, exactly as in
            :func:`unowned_templates`.
        GeneratorError: Two families produce one output name.
    """
    if not Path(directory).is_dir():
        raise NotADirectoryError(
            f"{directory} is not a directory, so no generated asset can be found there. "
            f"An empty result means every marked asset is produced by a declared "
            f"family, so this cannot be reported as one."
        )
    produced = expected_outputs(entries)
    return sorted(
        (
            path
            for path in Path(directory).glob(f"*{SYMBOL_EXTENSION}")
            if is_output_name(stem_of(path)) and base_name(stem_of(path)) not in produced
        ),
        key=lambda path: path.name,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Report what a directory and the declared families disagree about. Always exits zero.

    RERUN THIS REPORT::

        python -m eedesignsymbols.generators.registry --dir <library directory>

    Three sections. The templates no family declares, the output names every family
    produces, and the marked assets no family produces. Informational by design: an
    unowned template is legitimate today, so a non-zero exit would fail a pipeline over
    a known and accepted state. AC8 of iteration 4, and AC4 of iteration 7.
    """
    parser = argparse.ArgumentParser(
        prog="python -m eedesignsymbols.generators.registry",
        description=(
            "Report the SYMGEN templates in a directory that no generator family "
            "declares, and the marked assets no family produces. Informational: "
            "always exits 0."
        ),
    )
    parser.add_argument(
        "--dir",
        required=True,
        type=Path,
        help="Directory holding the SYMGEN templates. Read only.",
    )
    args = parser.parse_args(argv)

    directory: Path = args.dir
    if not directory.is_dir():
        parser.error(f"--dir is not a directory: {directory}")

    unowned = unowned_templates(directory)
    declared = declared_templates()
    if not unowned:
        print(f"every template in {directory} is declared by a family ({len(declared)} declared)")
    else:
        print(f"{len(unowned)} template file(s) in {directory} that no family declares:")
        for path in unowned:
            print(f"    {base_name(stem_of(path)):40} {path.name}")
        print(
            "This is informational. An unowned template is legitimate today, and the "
            "ones in the live library wait on ADR-011."
        )

    produced = expected_outputs()
    print(f"\n{len(produced)} output name(s) the declared families produce:")
    for name, owner in sorted(produced.items()):
        print(f"    {name:40} {owner}")

    unclaimed = unclaimed_outputs(directory)
    if not unclaimed:
        print(f"\nevery marked asset in {directory} is produced by a declared family")
        return 0

    print(f"\n{len(unclaimed)} marked asset(s) in {directory} that no family produces:")
    for path in unclaimed:
        print(f"    {base_name(stem_of(path)):40} {path.name}")
    print(
        "This is informational. No rerun maintains such an asset, and its name claims "
        "that one does."
    )
    return 0


check_no_shared_template()

__all__ = [
    "FAMILIES",
    "GENERATOR_MODULES",
    "FamilyEntry",
    "check_no_shared_template",
    "declared_templates",
    "describe",
    "expected_outputs",
    "main",
    "owner_of",
    "template_owners",
    "unclaimed_outputs",
    "unowned_templates",
]


if __name__ == "__main__":
    sys.exit(main())
