"""How a generator finds its templates and writes what it builds.

A *route* is the part of a run that is not drawing. It finds a template file, adds
any fields a library needs on each output, and writes the output file. The drawing
step, the pin numbering, and the output name are the same on every route.

:data:`PLAIN` is the route this package uses unless a caller names another. It reads
``<folder>/<name>.kicad_sym``, adds no field, and writes ``<out>/<name>.kicad_sym``
through the ``kicad-file-io`` writer. A rerun that would write the same bytes writes
nothing.

A library with its own naming and governance rules supplies its own route object
with the same five members. :func:`set_default_route` makes it the default for
every command in this process.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from eedesigncore import Symbol, SymbolLib

from eedesignsymbols.format_version import FormatVersionError

SYMBOL_EXTENSION = ".kicad_sym"
"""The file extension of a symbol library file."""


class Outcome(str, Enum):
    """What a write did, or what a dry run would do."""

    CREATED = "created"
    """No file existed. One was written."""

    UNCHANGED = "unchanged"
    """The file already held these bytes. Nothing was written."""

    UPDATED = "updated"
    """The file held other content. It was overwritten."""

    SUPERSEDED = "superseded"
    """A route that keeps old versions wrote a new one and retired the old one."""


@dataclass(frozen=True)
class WriteResult:
    """Where an output now lives, and how it got there."""

    outcome: Outcome
    path: Path
    superseded: Path | None = None


class ResultLike(Protocol):
    """What a command reads from the result of a write. A route may return its own type."""

    @property
    def outcome(self) -> Enum: ...

    @property
    def path(self) -> Path: ...

    @property
    def superseded(self) -> Path | None: ...


class Route(Protocol):
    """The five things a generator asks of a route."""

    refusals: tuple[type[Exception], ...]
    """Error types that mean "the templates or the output folder are wrong". A command
    prints one of these as one line and exits 1, rather than showing a traceback."""

    def template_dir(self) -> Path | None:
        """The folder to read templates from when the caller names none. None means
        the caller must name one."""

    def find_template(self, directory: Path, name: str) -> Path | None:
        """Return the file for template ``name`` in ``directory``, or None."""

    def missing_message(self, family: str, missing: Sequence[str], directory: Path) -> str:
        """The error text for templates that :meth:`find_template` did not find."""

    def stamp(self, symbol: Symbol, *, generator: str, template: str, version: str | None) -> None:
        """Add the fields a library needs on one output. ``template`` is the name of the
        template symbol as its file holds it."""

    def write(self, lib: SymbolLib, out_dir: Path) -> ResultLike:
        """Write one output into ``out_dir``."""

    def plan(self, lib: SymbolLib, out_dir: Path) -> ResultLike:
        """Report what :meth:`write` would do, and write nothing."""


def output_path(lib: SymbolLib, out_dir: Path) -> Path:
    """Return ``<out_dir>/<symbol name>.kicad_sym`` for a library of one symbol."""
    return out_dir / f"{lib.symbols[0].name}{SYMBOL_EXTENSION}"


def write_symbol(lib: SymbolLib, out_dir: Path) -> WriteResult:
    """Write ``lib`` to ``<out_dir>/<symbol name>.kicad_sym``.

    The file is written only when its bytes would change, so a rerun leaves the file
    and its time stamp alone.
    """
    path = output_path(lib, out_dir)
    text = lib.to_string()
    if path.is_file():
        if path.read_text(encoding="utf-8") == text:
            return WriteResult(Outcome.UNCHANGED, path)
        lib.to_file(path)
        return WriteResult(Outcome.UPDATED, path)
    lib.to_file(path)
    return WriteResult(Outcome.CREATED, path)


def plan_symbol(lib: SymbolLib, out_dir: Path) -> WriteResult:
    """Return what :func:`write_symbol` would do, and write nothing."""
    path = output_path(lib, out_dir)
    if not path.is_file():
        return WriteResult(Outcome.CREATED, path)
    if path.read_text(encoding="utf-8") == lib.to_string():
        return WriteResult(Outcome.UNCHANGED, path)
    return WriteResult(Outcome.UPDATED, path)


class PlainRoute:
    """Plain template files in, plain symbol files out. See the module docstring."""

    refusals: tuple[type[Exception], ...] = (FormatVersionError,)

    def template_dir(self) -> Path | None:
        from eedesignsymbols.generators.common import TEMPLATE_DIR

        return TEMPLATE_DIR

    def find_template(self, directory: Path, name: str) -> Path | None:
        path = directory / f"{name}{SYMBOL_EXTENSION}"
        return path if path.is_file() else None

    def missing_message(self, family: str, missing: Sequence[str], directory: Path) -> str:
        return (
            f"{family}: no template file for {list(missing)} in {directory}. A declared "
            f"template must exist. Correct the name in the generator config, or restore "
            f"the file."
        )

    def stamp(self, symbol: Symbol, *, generator: str, template: str, version: str | None) -> None:
        """Add nothing. A plain output carries only the KiCad fields."""

    def write(self, lib: SymbolLib, out_dir: Path) -> WriteResult:
        return write_symbol(lib, out_dir)

    def plan(self, lib: SymbolLib, out_dir: Path) -> WriteResult:
        return plan_symbol(lib, out_dir)


PLAIN = PlainRoute()
"""The default route."""

_default: list[Route] = [PLAIN]


def default_route() -> Route:
    """The route a generator uses when the caller names none."""
    return _default[0]


def set_default_route(route: Route) -> Route:
    """Make ``route`` the default for this process. Returns the previous default."""
    previous = _default[0]
    _default[0] = route
    return previous


__all__ = [
    "PLAIN",
    "SYMBOL_EXTENSION",
    "Outcome",
    "PlainRoute",
    "ResultLike",
    "Route",
    "WriteResult",
    "default_route",
    "output_path",
    "plan_symbol",
    "set_default_route",
    "write_symbol",
]
