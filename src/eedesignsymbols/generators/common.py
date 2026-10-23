"""Conventions shared by every generator.

A template is a drawing that a generator copies from. It is never a usable part:
its pin numbers are placeholders.

Two marks say so, and a template carries both:

- a leading underscore, which groups the templates together in the symbol
  library tree and shows "not for use" before anyone reads a description
- a trailing ``SYMGEN_TEMPLATE``, which a generator replaces with its own code

A generated symbol carries one name marker of its own, a trailing ``SYMGEN``, so
the name states that a generator owns the symbol. ``_Q_NMOS_SYMGEN_TEMPLATE``
generates ``Q_NMOS_GSD_SYMGEN``. The marker sits after the pin-order code, which
keeps the semantic part of the name in one piece. The test for an output name is
:meth:`str.endswith`, so the two markers cannot be confused.

Naming note: this is deliberately not called a "base" symbol. KiCad uses that
word for the parent of a derived symbol, the one named in an ``extends`` token.
Nothing extends a template. It is copied from.

Every generator module must carry a ``RERUN THIS GENERATOR`` block near the top
of its docstring, holding the exact command line that regenerates its output.
A test asserts the block is present.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypeGuard, TypeVar

from eedesigncore import Pin, Symbol, SymbolLib

from eedesignsymbols.symbol_fields import DESCRIPTION_FIELD, VALUE_FIELD, get_field, set_field
from eedesignsymbols.version import tree_version

TEMPLATE_PREFIX = "_"
"""Starts the name of every symbol that must not become a usable part."""

TEMPLATE_MARKER = "SYMGEN_TEMPLATE"
"""Ends a template's name. A generator replaces it with its own code."""

OUTPUT_MARKER = "SYMGEN"
"""Ends the name of every generated symbol. A generator appends it after the code."""

TEMPLATE_NOTICE = "SYMGEN TEMPLATE - not a usable part. Do not use in atomic library parts."
"""Appended to a template's description, so the warning reaches the picker."""

TOOL = "eedesignsymbols"
"""Identifies this tool in the KiCad ``generator`` header token."""

TOOL_SEPARATOR = ":"
"""Separates the tool from the specific generator: ``eedesignsymbols:mosfet_pinout``."""

GENERATOR_SEPARATOR = "@"
"""Separates a generator name from the tool version: ``mosfet_pinout@0.2.0+g4f2a1c9``."""

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
"""The template drawings this package ships, one ``.kicad_sym`` file per template.

Each file is named for its template, with no version number:
``_Q_NMOS_SYMGEN_TEMPLATE.kicad_sym`` holds the symbol ``_Q_NMOS_SYMGEN_TEMPLATE``. A
generator reads its templates from here unless the caller names another folder.
"""

TEMPLATE_EXTENSION = ".kicad_sym"
"""The file extension of a template file."""

_VERSION_TAIL = re.compile(r"__\d+$")
"""A trailing ``__<digits>``. Some libraries add one to every symbol name as a version
number. The naming helpers below ignore it, so a template from such a library names
its outputs the same way as a plain one."""


def template_file(name: str, directory: Path | str | None = None) -> Path:
    """Return the path of the template file for ``name``. The file may not exist.

    A plain lookup: the file is ``<directory>/<name>.kicad_sym``. No version number is
    read, and no lifecycle field is checked.

    Args:
        name: The template's symbol name, for example ``_Q_NMOS_SYMGEN_TEMPLATE``.
        directory: The folder that holds the template files. Defaults to
            :data:`TEMPLATE_DIR`, the templates this package ships.

    >>> template_file("_Q_NMOS_SYMGEN_TEMPLATE").name
    '_Q_NMOS_SYMGEN_TEMPLATE.kicad_sym'
    """
    folder = TEMPLATE_DIR if directory is None else Path(directory)
    return folder / f"{name}{TEMPLATE_EXTENSION}"


def without_version_tail(name: str) -> str:
    """Return ``name`` without a trailing ``__<digits>`` version number.

    >>> without_version_tail("_Q_NMOS_SYMGEN_TEMPLATE__1786580778623")
    '_Q_NMOS_SYMGEN_TEMPLATE'
    >>> without_version_tail("_Q_NMOS_SYMGEN_TEMPLATE")
    '_Q_NMOS_SYMGEN_TEMPLATE'
    """
    return _VERSION_TAIL.sub("", name)


_PINOUT_MARKER = " (pins "
_NOTICE_MARKER = "SYMGEN TEMPLATE"


# ----------------------------------------------------------------------
# Provenance: the KiCad header tokens and the generator stamp.
# ----------------------------------------------------------------------


def tool_version() -> str:
    """Return the version this tool reports in the ``generator_version`` token.

    Delegates to :func:`~eedesignsymbols.version.tree_version`, so the token
    identifies the exact tree rather than the number a possibly stale editable
    install recorded.
    """
    return tree_version()


def set_provenance(
    lib: SymbolLib,
    *,
    generator: str | None = None,
    version: str | None = None,
) -> None:
    """Stamp ``lib`` with the tool, the generator, and the tool version.

    Args:
        lib: The symbol library to stamp.
        generator: Name of the specific generator, for example ``mosfet_pinout``.
            Omit it for an edit that no single generator owns.
        version: Overrides the tree version. Pass it in tests, so a golden file
            does not change every release.
    """
    lib.generator = TOOL if generator is None else f"{TOOL}{TOOL_SEPARATOR}{generator}"
    lib.generator_version = tool_version() if version is None else version


UNSTAMPED_GENERATOR = SymbolLib().generator
"""The ``generator`` token a library carries when nothing stamped it.

``kicad-file-io`` defaults it to ``kicad_symbol_editor``, which is also what KiCad
itself writes. Read from the model rather than written out, so the two cannot
disagree.
"""


class UnstampedLibraryError(ValueError):
    """A library about to be written carries no provenance stamp from this tool."""


def require_provenance(lib: SymbolLib) -> None:
    """Raise :class:`UnstampedLibraryError` when nothing stamped ``lib``.

    An unstamped header carries :data:`UNSTAMPED_GENERATOR`, which is what KiCad
    writes, so an unstamped output would read as hand edited. This is the runtime
    check on every write path of this package.

    Args:
        lib: The symbol library about to be written. Not modified.

    Raises:
        UnstampedLibraryError: The tool half of the ``generator`` token is not
            :data:`TOOL`.
    """
    tool, _, _ = lib.generator.partition(TOOL_SEPARATOR)
    if tool == TOOL:
        return
    raise UnstampedLibraryError(
        f"the symbol library names {lib.generator!r} in its generator token, not {TOOL!r}. "
        f"A producer stamps its own header with "
        f"eedesignsymbols.generators.common.set_provenance before writing. "
        f"{UNSTAMPED_GENERATOR!r} is the kicad-file-io default and is what KiCad writes, so "
        f"an unstamped output reads as hand edited."
    )


class GeneratorStampError(ValueError):
    """A generator name cannot be recorded in a generator stamp."""


def generator_stamp(generator: str, version: str | None = None) -> str:
    """Return the stamp ``<generator>@<tool version>`` for ``generator``.

    Args:
        generator: The generator's name, for example ``mosfet_pinout``.
        version: Overrides :func:`~eedesignsymbols.version.tree_version`. Pass it in
            tests, so a golden file does not change on every commit.

    Raises:
        GeneratorStampError: The name is empty, carries surrounding whitespace, or
            contains the separator. All three would make the split ambiguous.

    >>> generator_stamp("mosfet_pinout", "0.2.0+g4f2a1c9")
    'mosfet_pinout@0.2.0+g4f2a1c9'
    """
    if not generator or generator != generator.strip():
        raise GeneratorStampError(f"generator name {generator!r} is empty or padded")
    if GENERATOR_SEPARATOR in generator:
        raise GeneratorStampError(
            f"generator name {generator!r} may not contain {GENERATOR_SEPARATOR!r}, "
            f"which separates the name from the version"
        )
    return f"{generator}{GENERATOR_SEPARATOR}{tree_version() if version is None else version}"


# ----------------------------------------------------------------------
# Names
# ----------------------------------------------------------------------


def is_template_name(symbol_name: str) -> bool:
    """True when ``symbol_name`` names a template rather than a usable symbol.

    A template carries both marks. A trailing version number is ignored.
    """
    stem = without_version_tail(symbol_name)
    return stem.startswith(TEMPLATE_PREFIX) and stem.endswith(TEMPLATE_MARKER)


def is_output_name(symbol_name: str) -> bool:
    """True when ``symbol_name`` names generated output. A trailing version number is ignored.

    **The test is :meth:`str.endswith`, never ``in``.** ``_Q_NMOS_SYMGEN_TEMPLATE``
    contains ``SYMGEN`` and does not end with ``_SYMGEN``, so ``in`` would call every
    template an output.

    >>> is_output_name("Q_NMOS_GSD_SYMGEN__1786580778623")
    True
    >>> is_output_name("_Q_NMOS_SYMGEN_TEMPLATE__1786580778623")
    False
    """
    return without_version_tail(symbol_name).endswith(f"_{OUTPUT_MARKER}")


def generated_name(template_symbol_name: str, code: str) -> str:
    """Return the name of a symbol generated from ``template_symbol_name``.

    Drops the template prefix, because a generated symbol is meant for use,
    replaces the trailing template name marker with ``code``, and appends the output
    marker so the name states that a generator owns the symbol. A trailing version
    number on the template name is ignored.

    >>> generated_name("_Q_NMOS_SYMGEN_TEMPLATE", "GSD")
    'Q_NMOS_GSD_SYMGEN'
    >>> generated_name("_Q_NMOS_SYMGEN_TEMPLATE__1786580778623", "GSD")
    'Q_NMOS_GSD_SYMGEN'
    """
    stem = without_version_tail(template_symbol_name)
    if not is_template_name(stem):
        raise ValueError(
            f"{stem!r} is not a template name: expected {TEMPLATE_PREFIX!r}...{TEMPLATE_MARKER!r}"
        )
    core = stem.removeprefix(TEMPLATE_PREFIX)
    return f"{core[: -len(TEMPLATE_MARKER)]}{code}_{OUTPUT_MARKER}"


def rename_symbol(symbol: Symbol, new_name: str) -> str:
    """Rename ``symbol``, every unit name, and the ``Value`` field together. Returns the name.

    KiCad binds a unit to its parent symbol only through the unit name
    ``<parent name>_<unit>_<body style>``. A unit name that does not start with the
    parent name makes the whole library file fail to load in KiCad. So the three
    places change in one step.
    """
    symbol.name = new_name
    for unit in symbol.units:
        unit.name = f"{new_name}_{unit.unit_index}_{unit.body_style_index}"
    set_field(symbol, VALUE_FIELD, new_name)
    return new_name


def template_name(base: str) -> str:
    """Return the template symbol name for a part base name.

    The inverse of :func:`generated_name`, which strips these two marks again.

    >>> template_name("D_SI")
    '_D_SI_SYMGEN_TEMPLATE'
    """
    if not base:
        raise ValueError("base name is empty")
    return f"{TEMPLATE_PREFIX}{base}_{TEMPLATE_MARKER}"


# ----------------------------------------------------------------------
# Description and output fields
# ----------------------------------------------------------------------


def core_description(text: str) -> str:
    """Strip any generated annotation, leaving the part description.

    Both the template notice and a pinout note are generated, so neither may be
    inherited by the next generation. Without this, building a permutation from
    an annotated template would carry "not a usable part" onto a usable symbol.

    >>> core_description("N-MOSFET transistor. SYMGEN TEMPLATE - not a usable part.")
    'N-MOSFET transistor'
    >>> core_description("N-MOSFET transistor (pins 1=G 2=S 3=D)")
    'N-MOSFET transistor'
    """
    text = text.split(_PINOUT_MARKER)[0]
    text = text.split(_NOTICE_MARKER)[0]
    return text.rstrip(" .")


def annotate(symbol: Symbol, note: str) -> str:
    """Set the symbol's ``Description`` to its core text plus ``note``.

    Replaces any previous annotation rather than stacking onto it, so regenerating
    is idempotent. Returns the text written.

    A parenthetical note joins with a space, a sentence with a period::

        "N-MOSFET transistor (pins 1=G 2=S 3=D)"
        "N-MOSFET transistor. SYMGEN TEMPLATE - not a usable part. ..."
    """
    core = core_description(get_field(symbol, DESCRIPTION_FIELD) or "")
    if not core:
        text = note
    elif note.startswith("("):
        text = f"{core} {note}"
    else:
        text = f"{core}. {note}"
    set_field(symbol, DESCRIPTION_FIELD, text)
    return text


_Model = TypeVar("_Model")


def same_kind(item: object, model: type[_Model]) -> TypeGuard[_Model]:
    """True when ``item`` is an instance of ``model``, or of a model class of the same name.

    ``eedesigncore`` is the published name of ``kicad-file-io``, and the two packages
    hold the same model classes under two import names. A library route that reads
    with the older package hands the generators objects of its classes. The test by
    class name accepts both, so the drawing step works on either.
    """
    return isinstance(item, model) or type(item).__name__ == model.__name__


def pins_of(symbol: Symbol) -> list[Pin]:
    """Return the pins of a symbol, across all of its units.

    A unit holds shapes, text, and pins in one ``items`` list, which ``eedesigncore``
    types as ``list[Any]``, so the pins are selected by type.
    """
    return [item for unit in symbol.units for item in unit.items if same_kind(item, Pin)]


__all__ = [
    "GENERATOR_SEPARATOR",
    "OUTPUT_MARKER",
    "TEMPLATE_DIR",
    "TEMPLATE_EXTENSION",
    "TEMPLATE_MARKER",
    "TEMPLATE_NOTICE",
    "TEMPLATE_PREFIX",
    "TOOL",
    "TOOL_SEPARATOR",
    "UNSTAMPED_GENERATOR",
    "GeneratorStampError",
    "UnstampedLibraryError",
    "annotate",
    "core_description",
    "generated_name",
    "generator_stamp",
    "is_output_name",
    "is_template_name",
    "pins_of",
    "rename_symbol",
    "same_kind",
    "require_provenance",
    "set_provenance",
    "template_file",
    "template_name",
    "tool_version",
    "without_version_tail",
]
