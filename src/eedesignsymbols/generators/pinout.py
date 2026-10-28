"""Generating one symbol per pin ordering, for a family of N-terminal parts.

A three-terminal part is drawn once. What changes between real parts is which
package pin carries which terminal, so rather than draw six symbols a generator
takes one template and stamps the pin numbers.

The template carries terminal *names* as its pin numbers, which is what makes it
unusable and therefore a template. Each generated symbol assigns ``1``, ``2``,
``3`` to those names in one of the orderings, and is named for it::

    _Q_NMOS_SYMGEN_TEMPLATE  ->  Q_NMOS_GSD_SYMGEN   (pin 1 = G, 2 = S, 3 = D)
    _Q_NPN_SYMGEN_TEMPLATE   ->  Q_NPN_BCE_SYMGEN    (pin 1 = B, 2 = C, 3 = E)

Only the pin numbers change. Geometry, pin positions, pin names, and electrical
types are carried over untouched, so the siblings stay visually identical.

A family is configuration, not code: see :class:`Family`. It declares the
templates it consumes and the orderings it generates, and both are required, so
the config decides what exists rather than the contents of a directory
(ADR-010, ADR-036). A template's pin names are still checked, but as validation:
a declared template that does not carry the family's terminals is a configuration
error. That matters because pin names cannot separate every family - a JFET
template carries the same G/S/D pins as a MOSFET template - and
:mod:`eedesignsymbols.generators.registry` proves no template is declared twice.

Finding a template and writing an output belong to a *route*, see
:mod:`eedesignsymbols.writing`. The drawing step here is the same on every route.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from eedesigncore import SymbolLib

from eedesignsymbols import version
from eedesignsymbols.format_version import FormatVersionError, require_current_format
from eedesignsymbols.generators import common
from eedesignsymbols.generators.common import (
    annotate,
    generated_name,
    pins_of,
    rename_symbol,
    require_provenance,
    set_provenance,
    template_name,
    without_version_tail,
)
from eedesignsymbols.preview_tools import (
    DEFAULT_OUTPUT_DIRNAME,
    GalleryEntry,
    build_gallery,
    export_svgs,
)
from eedesignsymbols.writing import Outcome, ResultLike, Route, default_route

TEMPLATE_FILE_GLOB = "_*_SYMGEN_TEMPLATE*.kicad_sym"
"""Matches every template file, whatever family declares it.

No selection path uses this: ADR-036 deleted the directory sweep, so a family
reads each declared name through its route instead. It is kept for the opposite
question, which is listing the templates present in a directory so the ones no
family declares can be reported. See BS-27.
"""


class GeneratorError(ValueError):
    """The template cannot be used by this family."""


@dataclass(frozen=True)
class PinOrder:
    """Which terminal sits on pin 1, pin 2, and so on."""

    terminals: tuple[str, ...]
    numbers: tuple[tuple[str, ...], ...] = ()
    """Package pin numbers per terminal, in the order of ``terminals``. Empty means
    pin 1, 2, 3 in that order. A terminal with more than one number is one
    electrical pin on several package pins, such as a drain on pins 1, 2, 5 and 6."""

    name_code: str = ""
    """The name fragment for this ordering. Empty means the terminals joined."""

    templates: tuple[str, ...] = ()
    """The templates this ordering applies to. Empty means every template of the
    family."""

    previous_names: tuple[str, ...] = ()
    """Old output names of this form. The plain route does not read them."""

    def __post_init__(self) -> None:
        try:
            common.validate_previous_names(self.previous_names)
            if self.name_code:
                common.check_name_part(self.name_code, "pinout code")
        except ValueError as exc:
            raise GeneratorError(str(exc)) from exc
        if self.numbers:
            flat = [number for group in self.numbers for number in group]
            if (
                len(self.numbers) != len(self.terminals)
                or any(not group for group in self.numbers)
                or any(not n.isdecimal() or int(n) < 1 for n in flat)
                or len(set(flat)) != len(flat)
            ):
                raise GeneratorError(
                    "Each physical pin must have one positive number and terminal"
                )

    @property
    def code(self) -> str:
        """The name fragment, for example ``GSD`` or ``BCE``."""
        return self.name_code or "".join(self.terminals)

    def number_for(self, terminal: str) -> str:
        """Return the pin number carrying ``terminal``, as KiCad stores it."""
        index = self.terminals.index(terminal)
        if not self.numbers:
            return str(index + 1)
        numbers = self.numbers[index]
        return numbers[0] if len(numbers) == 1 else f"[{','.join(numbers)}]"

    def __str__(self) -> str:
        if self.numbers:
            return " ".join(
                f"{','.join(numbers)}={terminal}"
                for terminal, numbers in zip(self.terminals, self.numbers, strict=True)
            )
        return " ".join(f"{i}={t}" for i, t in enumerate(self.terminals, start=1))

    def applies_to(self, template_symbol_name: str) -> bool:
        """True when this ordering is built from the named template.

        A version number at the end of the name is ignored.
        """
        return not self.templates or without_version_tail(template_symbol_name) in self.templates


@dataclass(frozen=True)
class Family:
    """A set of parts that differ only in which pin carries which terminal.

    Args:
        name: Recorded in the KiCad ``generator`` header token, for example
            ``mosfet_pinout``.
        terminals: The terminal names, as they appear as pin *names* on a
            template. Order here is only the canonical listing order.
        templates: Names of the templates this family consumes. Required and
            non-empty: ADR-010 puts the decision about what is generated in the
            config, and pin matching demotes from selection to validation.
        orders: The orderings to generate. Required and non-empty. A family
            states its outputs rather than emitting the full factorial, most of
            which may name no real part.
        output_base: Overrides the base name the outputs carry. Defaults to None,
            which takes the base from the template, so ``_Q_NMOS_SYMGEN_TEMPLATE``
            gives ``Q_NMOS_<code>_SYMGEN``. Set it where the template's own name
            carries a distinction the output name should not repeat: the
            mounting-pad LED is drawn by ``_D_LED_MP_SYMGEN_TEMPLATE`` and its
            output is ``D_LED_KAMP_SYMGEN``, because the ``MP`` already appears in
            the pin-order code and ``D_LED_MP_KAMP_SYMGEN`` would say it twice.

    Raises:
        GeneratorError: A field is empty, a terminal is repeated, or a declared
            ordering is not a permutation of the terminals.
    """

    name: str
    terminals: tuple[str, ...]
    templates: tuple[str, ...]
    orders: tuple[PinOrder, ...]
    output_base: str | None = None

    def __post_init__(self) -> None:
        if not self.terminals:
            raise GeneratorError(f"{self.name}: terminals is empty")

        # Empty is refused rather than treated as "everything". ADR-036 deleted
        # both fallbacks, so an empty list here would silently generate nothing
        # instead of silently generating too much, which is the quieter failure of
        # the two and therefore the worse one.
        if not self.templates:
            raise GeneratorError(
                f"{self.name}: templates is empty. A family declares the templates it "
                f"consumes. See ADR-010."
            )
        if not self.orders:
            raise GeneratorError(
                f"{self.name}: orders is empty. A family declares the orderings it "
                f"generates. See ADR-034."
            )

        # A repeated terminal means two pins share a name, which is how a
        # parallel-pin part is expressed. This class cannot build one: it assigns
        # one number per terminal, and PinOrder.number_for resolves a name to the
        # first index that carries it, so both pins would be numbered alike. Such
        # a part is drawn with stacked pins instead. See ADR-011.
        repeated = sorted({t for t in self.terminals if self.terminals.count(t) > 1})
        if repeated:
            raise GeneratorError(
                f"{self.name}: terminal(s) {repeated} appear more than once. A permutation "
                f"family assigns one pin number per terminal. A part with parallel pins is "
                f"built by stacking pins on one terminal, which this class does not do yet."
            )

        wanted = sorted(self.terminals)
        for order in self.orders:
            if set(order.templates) - set(self.templates):
                raise GeneratorError(f"{self.name}: ordering names an undeclared template")
            if sorted(order.terminals) != wanted:
                raise GeneratorError(
                    f"{self.name}: declared ordering {order.code!r} is not a permutation "
                    f"of {list(self.terminals)}"
                )

    # ------------------------------------------------------------------
    # Orderings and names
    # ------------------------------------------------------------------

    def pin_orders(self) -> list[PinOrder]:
        """The orderings this family generates, in declaration order."""
        return list(self.orders)

    def target_name(self, template_symbol_name: str, order: PinOrder) -> str:
        """Return the generated symbol's name.

        The leading underscore is dropped: it marks a template that must not be
        used, and a generated symbol is meant to be used. The trailing
        ``SYMGEN_TEMPLATE`` becomes the pin-order code, then the output name marker
        ``SYMGEN`` is appended, so ``_Q_NMOS_SYMGEN_TEMPLATE`` with order ``GSD``
        gives ``Q_NMOS_GSD_SYMGEN``. See
        :func:`~eedesignsymbols.generators.common.generated_name`.
        """
        source = template_symbol_name
        if self.output_base is not None:
            source = template_name(self.output_base)
        try:
            return generated_name(source, order.code)
        except ValueError as exc:
            raise GeneratorError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    def claims(self, symbol: Any) -> bool:
        """True when ``symbol`` is a template this family can build from.

        The test is the pin names, not the file name. A template whose pins are
        exactly this family's terminals belongs to it, so adding a part family
        that shares a pinout needs no pattern kept in step.
        """
        return sorted(str(pin.name) for pin in pins_of(symbol)) == sorted(self.terminals)

    def declared_templates(
        self, directory: Path | str | None = None, *, route: Route | None = None
    ) -> list[Path]:
        """Return the file of every template named in :attr:`templates`.

        The route finds each file. The default route reads
        ``<directory>/<name>.kicad_sym`` and reads no version number and no
        lifecycle field.

        A name that resolves to nothing raises rather than dropping out of the
        list. That is the mirror risk ADR-010 calls out: a template renamed in the
        template folder would otherwise make a generator silently stop producing its
        output, and the missing symbols would only be noticed much later.

        Pin matching still runs, but as validation rather than selection: a
        declared template that does not carry this family's terminals is a
        configuration error.

        Args:
            directory: The folder that holds the template files. Defaults to the
                route's own folder. For the default route that is
                :data:`~eedesignsymbols.generators.common.TEMPLATE_DIR`.
            route: Defaults to :func:`~eedesignsymbols.writing.default_route`.

        Raises:
            GeneratorError: A declared template is missing, holds more than one
                symbol, or does not carry this family's terminals. Every template
                problem arrives as this one type, because the CLI turns it into one
                message and a non-zero exit rather than a traceback.
        """
        route = route or default_route()
        default_folder = route.template_dir()
        if directory is None and default_folder is None:
            raise GeneratorError(f"{self.name}: this route needs a template folder")
        folder = Path(directory) if directory is not None else Path(str(default_folder))
        found: list[Path] = []
        missing: list[str] = []

        for declared in self.templates:
            try:
                path = route.find_template(folder, declared)
            except route.refusals as exc:
                raise GeneratorError(f"{self.name}: {exc}") from exc
            if path is None:
                missing.append(declared)
                continue
            lib = SymbolLib.from_file(path)
            # Refused at the read, so a legacy template cannot reach a write. The
            # writer emits the model's own value and `build` copies it from the
            # template, so a template below the minimum would stamp its format
            # version onto every generated symbol. ADR-098.
            require_current_format(lib, path)
            if len(lib.symbols) != 1:
                raise GeneratorError(
                    f"{path.name}: expected exactly 1 symbol, found {len(lib.symbols)}"
                )
            if not self.claims(lib.symbols[0]):
                actual = sorted(str(pin.name) for pin in pins_of(lib.symbols[0]))
                raise GeneratorError(
                    f"{path.name}: declared by {self.name}, but its pins are {actual}, "
                    f"not {sorted(self.terminals)}"
                )
            found.append(path)

        if missing:
            raise GeneratorError(route.missing_message(self.name, missing, folder))
        return found

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def build(
        self,
        template: SymbolLib,
        order: PinOrder,
        *,
        tool_version: str | None = None,
        route: Route | None = None,
    ) -> SymbolLib:
        """Return a new library holding the template with ``order`` applied.

        The input is not modified.

        Args:
            template: A library holding exactly one template symbol.
            order: Which terminal sits on which pin number.
            tool_version: Overrides the tree version in the header token and in any
                stamp the route adds. Pass it in a test that compares against a
                fixed expected value.
            route: Adds the route's own fields to the output. Defaults to
                :func:`~eedesignsymbols.writing.default_route`.
        """
        if len(template.symbols) != 1:
            raise GeneratorError(f"expected exactly 1 symbol, found {len(template.symbols)}")

        lib = template.model_copy(deep=True)
        symbol = lib.symbols[0]
        # Captured before the rename below, because a route may record the template
        # an output was built from, and that is the name it has now.
        built_from = symbol.name
        if not order.applies_to(built_from):
            raise GeneratorError(
                f"{order.code}: not declared for {without_version_tail(built_from)}"
            )

        pins = pins_of(symbol)
        found = sorted(str(pin.name) for pin in pins)
        if found != sorted(self.terminals):
            raise GeneratorError(f"expected pins {sorted(self.terminals)}, found {found}")

        for pin in pins:
            pin.number = order.number_for(str(pin.name))
            if order.numbers and len(order.numbers[order.terminals.index(str(pin.name))]) > 1:
                pin.number_text_size = 0

        # Pin number visibility is inherited from the template, never set here.
        # Operator ruling 2026-08-26: a template that hides its pin numbers is
        # stating how the part is drawn, and a generator does not overrule the
        # drawing. The siblings are told apart by their names and their
        # descriptions, both of which carry the ordering. A pin with a group of
        # numbers gets a number text size of zero, so the group text does not
        # crowd the drawing. A pin with one number keeps the template's size.

        rename_symbol(symbol, self.target_name(symbol.name, order))

        # The siblings are visually identical, so the description is the only
        # thing that tells them apart in the symbol picker. The template's "not a
        # usable part" notice is dropped rather than inherited.
        annotate(symbol, f"(pins {order})")

        (route or default_route()).stamp(
            symbol, generator=self.name, template=built_from, version=tool_version
        )

        # The producer stamps its own header. Stamped here rather than in
        # `generate_all`, so every caller of `build` gets a stamped library.
        set_provenance(lib, generator=self.name, version=tool_version)

        return lib

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def generate_all(
        self,
        template_path: Path | str,
        out_dir: Path | str,
        *,
        dry_run: bool = False,
        route: Route | None = None,
    ) -> list[ResultLike]:
        """Bring ``out_dir`` up to date with every ordering of one template.

        The route writes each ordering. The default route writes nothing when the
        file already holds the same bytes, and overwrites it otherwise.

        Args:
            template_path: A ``_*_SYMGEN_TEMPLATE*.kicad_sym`` file.
            out_dir: Destination directory. Must exist.
            dry_run: Decide and report, but write nothing.
            route: Defaults to :func:`~eedesignsymbols.writing.default_route`.
        """
        route = route or default_route()
        template_path, out_dir = Path(template_path), Path(out_dir)
        template = SymbolLib.from_file(template_path)
        # The input gate. `build` copies `SymbolLib.version` out of the template and
        # the writer emits the model's own value, so refusing here is what keeps
        # every output at or above the minimum. Refused before the loop, so no
        # ordering is written when the template is legacy. ADR-098.
        require_current_format(template, template_path)
        results: list[ResultLike] = []

        for order in self.pin_orders():
            if not order.applies_to(template.symbols[0].name):
                continue
            lib = self.build(template, order, route=route)
            # `build` stamps, so this never fires today. It is the runtime check that
            # no write path forgets the header stamp. ADR-100.
            require_provenance(lib)
            try:
                if dry_run:
                    results.append(route.plan(lib, out_dir))
                else:
                    results.append(route.write(lib, out_dir))
            except route.refusals as exc:  # pragma: no cover - defensive
                raise GeneratorError(f"{template_path.name}, {order.code}: {exc}") from exc

        return results


def build_preview(written: Sequence[tuple[Path, str]], preview_dir: Path) -> Path:
    """Render every symbol this run wrote and build one gallery for them.

    Only the files the run actually touched, not the rest of whatever directory
    they landed in: an output folder can hold hundreds of unrelated symbols, and a
    librarian checking one generator run does not want those in the way.

    Args:
        written: Pairs of a written symbol's path and the gallery category it
            belongs to, which is its family's name. A generator with two
            families whose names differ therefore gets two categories.
        preview_dir: Root of the preview output. The gallery and its SVGs go
            under it.

    Returns:
        The written gallery's path.
    """
    paths = [path for path, _ in written]
    export_results = export_svgs(paths, preview_dir / "svgs")
    export_by_path = {result.sym_path: result for result in export_results}

    entries = [
        GalleryEntry(
            name=path.stem,
            category=category,
            svg_paths=export_by_path[path].svg_paths,
            error=export_by_path[path].error,
        )
        for path, category in written
    ]
    return build_gallery(entries, preview_dir / "gallery.html")


def run(
    family: Family,
    module: str,
    argv: Sequence[str] | None = None,
    *,
    route: Route | None = None,
) -> int:
    """Command line entry point for a generator with one family.

    Args:
        family: The family to generate.
        module: Dotted module name, used in the usage line.
        argv: Argument list. Defaults to the process arguments.
        route: Defaults to :func:`~eedesignsymbols.writing.default_route`.
    """
    return run_many([family], module, argv, route=route)


def run_many(
    families: Sequence[Family],
    module: str,
    argv: Sequence[str] | None = None,
    *,
    route: Route | None = None,
) -> int:
    """Command line entry point shared by every pinout generator.

    A generator has more than one family when its parts do not share a terminal
    set. The diode generator is the case: a unidirectional part is drawn A/K and
    a bidirectional one A1/A2, so they cannot be one family, but they are one
    part family to a librarian and belong in one module behind one command.

    THE TEMPLATE FOLDER

    ``--templates`` names it. Without it, the route's own folder is used: the
    templates this package ships, for the default route. A route with no folder of
    its own reads the templates from ``--dir``.

    THE STAMP REFUSAL LIVES HERE

    This is the command that writes the ``generator_version`` header token, so this
    is the command that refuses to write it from a tree it cannot name. In a source
    tree, a write is refused unless :func:`~eedesignsymbols.version.identifies_the_tree`
    answers True, which asks that the stamp names a commit and carries no ``.dirty``
    marker. ADR-109. An installed package has no source tree, and its release number
    is accepted instead, :func:`~eedesignsymbols.version.is_installed_release`.
    ``--allow-dirty`` overrides the refusal for a scratch copy and prints that it did.
    ``--dry-run`` needs no flag, because it writes nothing.

    THE PREVIEW GALLERY LIVES HERE TOO

    A run renders only the files it wrote and writes the gallery under
    ``./.preview`` by default, never inside ``--dir``. ``--no-preview`` skips it,
    and ``--preview-dir`` moves it. A dry run builds no gallery, because it wrote
    nothing to render.

    Args:
        families: The families to generate, in order.
        module: Dotted module name, used in the usage line.
        argv: Argument list. Defaults to the process arguments.
        route: Defaults to :func:`~eedesignsymbols.writing.default_route`.
    """
    if not families:
        raise GeneratorError("no families to generate")
    route = route or default_route()
    refused: tuple[type[Exception], ...] = (GeneratorError, FormatVersionError, *route.refusals)

    shapes = ", ".join(f"{'/'.join(f.terminals)}" for f in families)
    parser = argparse.ArgumentParser(
        prog=f"python -m {module}",
        description=f"Generate {families[0].name} symbols ({shapes}) from the SYMGEN templates.",
        # No abbreviation. This command writes by default, so `--dry-run` is the flag
        # that stops a write, and an abbreviation of it must fail rather than be
        # guessed. ADR-110.
        allow_abbrev=False,
    )
    parser.add_argument("--dir", required=True, type=Path, help="The output directory.")
    parser.add_argument("--out", type=Path, default=None, help="Write here instead of --dir.")
    parser.add_argument(
        "--templates",
        type=Path,
        default=None,
        help="Directory holding the SYMGEN template files "
        "(default: the templates this package ships).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would happen, and write nothing.",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Permit a write from a modified or unidentified tool tree. Scratch copies only.",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Skip building an HTML preview gallery of the symbols this run writes.",
    )
    parser.add_argument(
        "--preview-dir",
        type=Path,
        default=None,
        help=f"Preview gallery output directory (default: ./{DEFAULT_OUTPUT_DIRNAME}, "
        "relative to the current directory, never inside --dir).",
    )
    parser.add_argument(
        "--part",
        action="append",
        default=[],
        metavar="CODE",
        help="Generate only this declared pinout code. Repeat to select more than one.",
    )
    args = parser.parse_args(argv)
    if args.part:
        unknown = set(args.part) - {order.code for family in families for order in family.orders}
        if unknown:
            parser.error(f"Unknown pinout code(s): {', '.join(sorted(unknown))}")
        # Keep only the selected orderings, and only the templates they apply to.
        selected = []
        for family in families:
            orders = tuple(order for order in family.orders if order.code in args.part)
            if orders:
                selected_templates = tuple(
                    name
                    for name in family.templates
                    if any(order.applies_to(name) for order in orders)
                )
                selected.append(replace(family, orders=orders, templates=selected_templates))
        families = selected

    source: Path = args.templates or route.template_dir() or args.dir
    out_dir: Path = args.out or args.dir
    if not args.dir.is_dir():
        parser.error(f"--dir is not a directory: {args.dir}")
    if not out_dir.is_dir():
        parser.error(f"--out is not a directory: {out_dir}")
    if not source.is_dir():
        parser.error(f"--templates is not a directory: {source}")

    if not args.dry_run:
        stamp = common.tool_version()
        if not version.write_permitted(stamp):
            if not args.allow_dirty:
                print(f"error: {version.unidentified_tree_message(stamp)}")
                return 1
            print(f"--allow-dirty overrode a refusal: the stamp reads {stamp!r}.")

    tally: dict[str, int] = {outcome.value: 0 for outcome in Outcome}
    written: list[tuple[Path, str]] = []
    for family in families:
        try:
            templates = family.declared_templates(source, route=route)
            for template in templates:
                results = family.generate_all(template, out_dir, dry_run=args.dry_run, route=route)
                print(f"{template.name}:")
                for result in results:
                    outcome = str(result.outcome.value)
                    tally[outcome] = tally.get(outcome, 0) + 1
                    line = f"    {outcome:<11} {result.path.name}"
                    if result.superseded is not None:
                        line += f"  (deprecated {result.superseded.name})"
                    print(line)
                    # A dry run names a path it did not create, and an UNCHANGED
                    # result names one that already existed. The file test keeps
                    # the first out of the gallery and lets the second in.
                    if result.path.is_file():
                        written.append((result.path, family.name))
        except refused as exc:
            # A declared template that is missing or carries the wrong pins, or a
            # template below the format minimum. Each stops the run rather than
            # write a partial set, and each prints one message rather than a
            # traceback, because the reader is a librarian.
            print(f"error: {exc}")
            return 1

    prefix = "would be" if args.dry_run else ""
    summary = ", ".join(f"{count} {outcome}" for outcome, count in tally.items() if count)
    print(f"\n{prefix} {summary}".strip())

    if not args.dry_run and not args.no_preview and written:
        preview_dir: Path = args.preview_dir or Path.cwd() / DEFAULT_OUTPUT_DIRNAME
        gallery_path = build_preview(written, preview_dir)
        print(f"preview: {gallery_path}")

    return 0


__all__ = [
    "TEMPLATE_FILE_GLOB",
    "Family",
    "GeneratorError",
    "PinOrder",
    "build_preview",
    "pins_of",
    "run",
    "run_many",
]
