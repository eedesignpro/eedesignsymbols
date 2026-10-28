"""Config schema for the single op-amp generator.

One YAML file, one ``parts`` list entry per row. A librarian edits this
file directly. The generator makes no decision of its own: every pin's
fate, and the generated symbol's own name, are read from here, not
inferred.

Each row lists what to do with every pin slot on
``_OPAMP_SINGLE_SYMGEN_TEMPLATE``, keyed by that template's own pin name.
Omitting an optional slot deletes it. A core slot cannot be omitted or
deleted::

    parts:
      - code: 5p
        description: Single op-amp.
        pins:
          "+": {number: "3"}
          "-": {number: "2"}
          OUT: {name: OUT, number: "6"}
          "V+": {name: "+VS", number: "5"}
          "V-": {name: "-VS", number: "4"}

Two rows never share a symbol name, because ``code`` is not derived: many
manufacturer part numbers can share one exact pinout, and none of them
gets to be the symbol's name. See ``single.py``'s module docstring for the
naming rule ``code`` is expected to follow.

The template slots remain ``+`` and ``-``. Single outputs name these pins
``IN+`` and ``IN-``. Dual rows use ``channels: 2`` and ``CHA.+``, ``CHA.-``,
``CHA.OUT``, ``CHB.+``, ``CHB.-``, and ``CHB.OUT``. Dual input names are
``INA+``, ``INA-``, ``INB+``, and ``INB-``. Single outputs use ``OUT``.
Dual outputs use ``OUTA`` and ``OUTB``.
Shared supply, pad, NC, and optional global control slots have no channel prefix.

A pin's ``name_text_size`` is optional and, when omitted, the generated
symbol keeps the template's own size for that pin. Setting it overrides
the size for that one pin on that one output row only; it never changes
the template, and it never changes any other row.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from eedesignsymbols.generators.common import validate_previous_names

CORE_PINS = ("+", "-", "OUT", "V+", "V-")
"""Template pin names every part keeps. Deleting one is a config error."""

OPTIONAL_PINS = ("EN", "~{EN}", "FB_OUT", "PAD", "NC")
"""Template pin names a part may keep or delete. Omitted means deleted."""

ALL_TEMPLATE_PINS = CORE_PINS + OPTIONAL_PINS

DUAL_CORE_PINS = tuple(
    f"{channel}.{slot}" for channel in ("CHA", "CHB") for slot in ("+", "-", "OUT")
) + ("V+", "V-")
DUAL_OPTIONAL_PINS = ("PAD", "NC", "EN", "~{EN}") + tuple(
    f"{channel}.{slot}" for channel in ("CHA", "CHB") for slot in ("EN", "~{EN}")
)
DUAL_PINS = DUAL_CORE_PINS + DUAL_OPTIONAL_PINS

FIXED_PIN_NAMES = {"+": "IN+", "-": "IN-", "OUT": "OUT"}
"""Slots whose generated name is fixed and cannot come from the config.

Single symbols use ``IN+``, ``IN-``, and ``OUT`` for these three pins.
Dual inputs use ``INA+``, ``INA-``, ``INB+``, and ``INB-``. Every other pin name
must match the manufacturer, including case and any overbar.
"""

_ELECTRICAL_TYPES = frozenset(
    {
        "input",
        "output",
        "bidirectional",
        "tri_state",
        "passive",
        "free",
        "unspecified",
        "power_in",
        "power_out",
        "open_collector",
        "open_emitter",
        "no_connect",
    }
)


class ConfigError(ValueError):
    """A config file, or one row in it, cannot be used to build a symbol."""


@dataclass(frozen=True)
class PinSpec:
    """One kept pin: its manufacturer name, pin number(s), and electrical type.

    ``numbers`` holds more than one entry when the same logical pin carries
    more than one physical pin number (a stacked, parallel pin).
    """

    name: str
    numbers: tuple[str, ...]
    electrical_type: str | None = None
    """``None`` means keep the template's own electrical type for this pin."""

    name_text_size: float | None = None
    """``None`` means keep the template's own pin name text size for this
    pin. A row sets this only to override that one output; every other row,
    and every other pin on this row, still gets the template's value."""


@dataclass(frozen=True)
class PartSpec:
    """One row: one pinout shape, and what to do to every template pin slot."""

    code: str
    """The generated symbol's own naming fragment, written verbatim into
    ``OPAMP_SINGLE_<code>_SYMGEN``. Never a manufacturer part number: many
    part numbers can share one row, since a row is a pinout shape, not a
    part."""

    pins: dict[str, PinSpec | None]
    """Keyed by the template's own pin name. ``None`` means delete that pin."""

    description: str
    """One sentence stating what this shape adds over the bare five pins.
    The generator appends the exact kept-pin list after it, so this need
    not, and should not, repeat that list itself."""

    channels: int = 1
    """One amplifier, or two amplifiers with shared supply pins."""

    previous_names: tuple[str, ...] = ()
    """Old output names of this form. The plain route does not read them."""

    def kept(self, slot: str) -> PinSpec | None:
        """Return the spec for ``slot``, or ``None`` when it is deleted."""
        return self.pins.get(slot)


def _parse_pin_spec(code: str, slot: str, raw: Any) -> PinSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ConfigError(
            f"{code}: pin {slot!r}: expected a mapping or null, got {type(raw).__name__}"
        )

    fixed_name = FIXED_PIN_NAMES.get(slot.rsplit(".", 1)[-1])
    if slot in ("CHA.+", "CHA.-", "CHB.+", "CHB.-"):
        fixed_name = f"IN{slot[2]}{slot[-1]}"
    elif slot in ("CHA.OUT", "CHB.OUT"):
        fixed_name = f"OUT{slot[2]}"
    raw_name = raw.get("name")
    if fixed_name is not None:
        if raw_name is not None and raw_name != fixed_name:
            raise ConfigError(
                f"{code}: pin {slot!r} must be named {fixed_name!r}. The op-amp "
                f"naming convention applies here; omit 'name' "
                f"or set it to {fixed_name!r}."
            )
        name = fixed_name
    elif not raw_name or not isinstance(raw_name, str):
        raise ConfigError(f"{code}: pin {slot!r}: 'name' is required and must be a string")
    else:
        name = raw_name

    number = raw.get("number")
    if number is None:
        raise ConfigError(f"{code}: pin {slot!r}: 'number' is required")
    numbers = tuple(str(n) for n in number) if isinstance(number, list) else (str(number),)
    if not numbers:
        raise ConfigError(f"{code}: pin {slot!r}: 'number' is empty")
    if any(not n or n.strip() != n or any(c.isspace() for c in n) for n in numbers):
        raise ConfigError(f"{code}: pin {slot!r}: each number must be a nonempty token")

    etype = raw.get("electrical_type")
    if etype is not None and etype not in _ELECTRICAL_TYPES:
        raise ConfigError(f"{code}: pin {slot!r}: unknown electrical_type {etype!r}")

    name_text_size = raw.get("name_text_size")
    if name_text_size is not None:
        if isinstance(name_text_size, bool) or not isinstance(name_text_size, int | float):
            raise ConfigError(f"{code}: pin {slot!r}: 'name_text_size' must be a number")
        if name_text_size <= 0:
            raise ConfigError(f"{code}: pin {slot!r}: 'name_text_size' must be positive")
        name_text_size = float(name_text_size)

    return PinSpec(
        name=name, numbers=numbers, electrical_type=etype, name_text_size=name_text_size
    )


def _parse_part(row: dict[str, Any]) -> PartSpec:
    if not isinstance(row, dict):
        raise ConfigError("each part must be a mapping")
    code = row.get("code")
    if not code or not isinstance(code, str):
        raise ConfigError("a row is missing a string 'code'")

    description = row.get("description")
    if not description or not isinstance(description, str):
        raise ConfigError(f"{code}: 'description' is required and must be a string")

    channels = row.get("channels", 1)
    if type(channels) is not int or channels not in (1, 2):
        raise ConfigError(f"{code}: 'channels' must be 1 or 2")
    core_pins = CORE_PINS if channels == 1 else DUAL_CORE_PINS
    all_pins = ALL_TEMPLATE_PINS if channels == 1 else DUAL_PINS

    raw_pins = row.get("pins", {})
    if not isinstance(raw_pins, dict):
        raise ConfigError(f"{code}: 'pins' must be a mapping")

    unknown = set(raw_pins) - set(all_pins)
    if unknown:
        raise ConfigError(f"{code}: unknown template pin slot(s) {sorted(unknown)}")

    missing_core = set(core_pins) - set(raw_pins)
    if missing_core:
        raise ConfigError(f"{code}: missing required pin(s) {sorted(missing_core)}")

    pins: dict[str, PinSpec | None] = {}
    for slot in all_pins:
        if slot not in raw_pins:
            pins[slot] = None  # an omitted optional pin is a deleted pin
            continue
        spec = _parse_pin_spec(code, slot, raw_pins[slot])
        if slot in core_pins and spec is None:
            raise ConfigError(f"{code}: core pin {slot!r} cannot be deleted")
        pins[slot] = spec

    if pins.get("EN") and pins.get("~{EN}"):
        raise ConfigError(f"{code}: select only one control direction")
    for channel in ("CHA", "CHB"):
        if pins.get(f"{channel}.EN") and pins.get(f"{channel}.~{{EN}}"):
            raise ConfigError(f"{code}: select only one control direction for {channel}")
    used: dict[str, str] = {}
    for slot, spec in pins.items():
        if spec is not None:
            for number in spec.numbers:
                if number in used:
                    raise ConfigError(
                        f"{code}: pin number {number!r} repeats in {used[number]} and {slot}"
                    )
                used[number] = slot

    previous_names = row.get("previous_names", [])
    if not isinstance(previous_names, list) or any(not isinstance(n, str) for n in previous_names):
        raise ConfigError(f"{code}: previous_names must be a list of base names")
    try:
        validate_previous_names(previous_names)
    except ValueError as exc:
        raise ConfigError(f"{code}: {exc}") from exc
    return PartSpec(
        code=code,
        pins=pins,
        description=description,
        channels=channels,
        previous_names=tuple(previous_names),
    )


def load_config(path: Path | str) -> list[PartSpec]:
    """Read the YAML config and return one :class:`PartSpec` per row.

    Raises:
        ConfigError: A row is missing a required field, names an unknown pin
            slot, tries to delete a core pin, or repeats a ``code``.
    """
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a mapping with a 'parts' list")

    rows = data.get("parts")
    if not isinstance(rows, list) or not rows:
        raise ConfigError(f"{path}: 'parts' must be a non-empty list")

    specs = [_parse_part(row) for row in rows]

    seen: set[str] = set()
    dupes: set[str] = set()
    for spec in specs:
        if spec.code in seen:
            dupes.add(spec.code)
        seen.add(spec.code)
    if dupes:
        raise ConfigError(f"{path}: duplicate code(s) {sorted(dupes)}")

    return specs


__all__ = [
    "ALL_TEMPLATE_PINS",
    "CORE_PINS",
    "FIXED_PIN_NAMES",
    "OPTIONAL_PINS",
    "ConfigError",
    "PartSpec",
    "PinSpec",
    "load_config",
]
