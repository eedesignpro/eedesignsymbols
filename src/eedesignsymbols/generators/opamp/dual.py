"""Build dual op-amps from two copies of the single op-amp drawing.

The single op-amp template is the source. Unit A and unit B are two copies of its
amplifier unit, one per channel. Unit PWR is its supply unit, so the supply, pad,
and NC pins occur once. A global enable pin goes on the left edge of unit PWR.
The description names each pin with its channel, for example ``CHA.INA+``.

The output name is ``OPAMP_DUAL_<code>_SYMGEN``.

RERUN THIS GENERATOR
--------------------
    .venv\\Scripts\\python.exe -m eedesignsymbols.generators.opamp.dual \\
        --config "src\\eedesignsymbols\\generators\\opamp\\dual_opamp_parts.yaml" \\
        --dir "<output dir>"

Add ``--part CODE`` to generate one form. Add ``--dry-run`` to report without
writing. The other options are those of :mod:`eedesignsymbols.generators.opamp.single`.
"""

from __future__ import annotations

from collections.abc import Sequence

from eedesigncore import Pin, PinElectricalType, SchRect, SymbolLib, SymbolUnit

from eedesignsymbols.generators.common import (
    annotate,
    check_name_part,
    rename_symbol,
    same_kind,
    set_provenance,
    without_version_tail,
)
from eedesignsymbols.generators.opamp import single
from eedesignsymbols.generators.opamp.config import ALL_TEMPLATE_PINS, PartSpec, PinSpec
from eedesignsymbols.symbol_fields import DESCRIPTION_FIELD, set_field
from eedesignsymbols.writing import Route, default_route

GENERATOR = "opamp_dual"
TEMPLATE_NAME = single.TEMPLATE_NAME


def build(
    template: SymbolLib,
    spec: PartSpec,
    *,
    tool_version: str | None = None,
    route: Route | None = None,
) -> SymbolLib:
    """Build two independent channels and one shared supply unit.

    The input is not modified. ``route`` adds its own fields to the output, and
    defaults to :func:`~eedesignsymbols.writing.default_route`.
    """
    if spec.channels != 2:
        raise single.GeneratorError(f"{spec.code}: the dual generator requires two channels")
    if len(template.symbols) != 1:
        raise single.GeneratorError("The dual generator requires one template symbol.")
    source = template.symbols[0]
    if source.extends or {unit.unit_index for unit in source.units} != {1, 2}:
        raise single.GeneratorError("The template must have amplifier unit 1 and supply unit 2.")
    for unit in source.units:
        expected = (
            {"+", "-", "OUT", "EN", "~{EN}", "FB_OUT"}
            if unit.unit_index == 1
            else {"V+", "V-", "PAD", "NC"}
        )
        if any(same_kind(item, Pin) and item.name not in expected for item in unit.items):
            raise single.GeneratorError("A template pin is in the wrong amplifier or supply unit.")

    built_channels = []
    for channel in ("CHA", "CHB"):
        pins: dict[str, PinSpec | None] = dict.fromkeys(ALL_TEMPLATE_PINS)
        for slot in ("+", "-", "OUT", "EN", "~{EN}"):
            pins[slot] = spec.kept(f"{channel}.{slot}")
        for slot in ("V+", "V-", "PAD", "NC"):
            pins[slot] = spec.kept(slot)
        channel_spec = PartSpec(spec.code, pins, spec.description)
        built_channels.append(
            single.build(template, channel_spec, tool_version=tool_version, route=route)
        )

    lib = built_channels[0]
    symbol = lib.symbols[0]
    base = without_version_tail(symbol.name)
    if not base.startswith("OPAMP_SINGLE_"):
        raise single.GeneratorError("The source template does not name a single op-amp.")
    name = "OPAMP_DUAL_" + base.removeprefix("OPAMP_SINGLE_")
    try:
        check_name_part(name, "output name")
    except ValueError as exc:
        raise single.GeneratorError(str(exc)) from exc
    units = []
    for channel_index, channel_lib in enumerate(built_channels, start=1):
        for unit in channel_lib.symbols[0].units:
            if unit.unit_index == 1:
                units.append(
                    SymbolUnit.for_symbol(
                        name,
                        unit_index=channel_index,
                        body_style_index=unit.body_style_index,
                        unit_display_name="A" if channel_index == 1 else "B",
                        items=unit.model_copy(deep=True).items,
                    )
                )
    for unit in symbol.units:
        if unit.unit_index == 2:
            items = unit.model_copy(deep=True).items
            for slot in ("EN", "~{EN}"):
                control = spec.kept(slot)
                if control is None:
                    continue
                rectangles = [item for item in items if same_kind(item, SchRect)]
                if len(rectangles) != 1:
                    raise single.GeneratorError(
                        "A global control needs one supply-unit rectangle."
                    )
                rectangle = rectangles[0]
                left = min(rectangle.start[0], rectangle.end[0])
                prototype = next(
                    item
                    for source_unit in source.units
                    for item in source_unit.items
                    if same_kind(item, Pin) and item.name == slot
                )
                pin = prototype.model_copy(deep=True)
                pin.name = control.name
                pin.number = single._pin_number_text(control.numbers)
                pin.position = (left - pin.length, -1.27 if slot == "EN" else 1.27)
                pin.angle = 0.0
                if control.electrical_type is not None:
                    pin.electrical_type = PinElectricalType(control.electrical_type)
                if control.name_text_size is not None:
                    pin.name_text_size = control.name_text_size
                single.fit_pin_name(pin, unit)
                items.append(pin)
            units.append(
                SymbolUnit.for_symbol(
                    name,
                    unit_index=3,
                    body_style_index=unit.body_style_index,
                    unit_display_name="PWR",
                    items=items,
                )
            )
    symbol.units = units
    symbol.units_locked = True
    rename_symbol(symbol, name)
    set_field(symbol, DESCRIPTION_FIELD, spec.description)
    annotate(symbol, single.pinout_description(spec))
    (route or default_route()).stamp(
        symbol, generator=GENERATOR, template=source.name, version=tool_version
    )
    set_provenance(lib, generator=GENERATOR, version=tool_version)
    return lib


def main(argv: Sequence[str] | None = None, *, route: Route | None = None) -> int:
    """Run the shared write and preview command for dual forms."""
    return single.main(argv, route=route, channels=2)


__all__ = ["GENERATOR", "TEMPLATE_NAME", "build", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
