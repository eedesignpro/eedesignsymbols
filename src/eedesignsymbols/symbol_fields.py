"""Read and write a field on a KiCad symbol.

A field is a KiCad ``property``: ``Reference``, ``Value``, ``Description``, or any user
field. These two helpers are the only field access the generators need.
"""

from __future__ import annotations

from eedesigncore import Property, Symbol

VALUE_FIELD = "Value"
"""The KiCad field that holds the symbol's value. A generated symbol's value is its name."""

DESCRIPTION_FIELD = "Description"
"""The KiCad field that holds the symbol's description, shown in the symbol picker."""


def get_field(symbol: Symbol, name: str) -> str | None:
    """Return the value of field ``name``, or None when the symbol has no such field."""
    for field in symbol.fields:
        if field.name == name:
            return field.value
    return None


def set_field(symbol: Symbol, name: str, value: str) -> None:
    """Set field ``name`` to ``value``, and add the field when it is absent.

    A new field copies an existing hidden field, so its text settings match the rest
    of the file. It is hidden and sits at the origin.
    """
    for field in symbol.fields:
        if field.name == name:
            field.value = value
            return

    hidden = next((f for f in symbol.fields if not f.visible), None)
    new = hidden.model_copy(deep=True) if hidden is not None else Property(name=name, value=value)
    new.name = name
    new.value = value
    new.position = (0.0, 0.0)
    new.angle = 0.0
    new.visible = False
    new.show_name = False
    symbol.fields.append(new)


__all__ = ["DESCRIPTION_FIELD", "VALUE_FIELD", "get_field", "set_field"]
