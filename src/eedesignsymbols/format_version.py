"""The lowest symbol library format version a generator reads.

A generated symbol copies the format version of its template, and the writer emits
that number. So a template below KiCad 10.0 would give an output below KiCad 10.0.
The generators refuse such a template when they read it.

KiCad itself reads an older file and upgrades it in memory without a warning. This is
the tool's own requirement, not a KiCad one.
"""

from __future__ import annotations

from pathlib import Path

from eedesigncore import SymbolLib

MINIMUM_FORMAT_VERSION = 20251024
"""The ``(version ...)`` number that KiCad 10.0 writes into a symbol library."""


class FormatVersionError(ValueError):
    """A symbol library declares a format version below :data:`MINIMUM_FORMAT_VERSION`."""


def require_current_format(lib: SymbolLib, source: Path | str) -> None:
    """Raise :class:`FormatVersionError` when ``lib`` is older than KiCad 10.0.

    Args:
        lib: The loaded library. Not modified.
        source: The path or name to put in the message.
    """
    if lib.version >= MINIMUM_FORMAT_VERSION:
        return
    raise FormatVersionError(
        f"{Path(source).name}: symbol library format version {lib.version} is below "
        f"{MINIMUM_FORMAT_VERSION}, the KiCad 10.0 format. "
        f"Run: kicad-cli sym upgrade {Path(source)!s} . "
        f"That command prints 'Symbol library was not updated' at error severity and "
        f"still exits zero on a file already at the current version."
    )


__all__ = ["MINIMUM_FORMAT_VERSION", "FormatVersionError", "require_current_format"]
