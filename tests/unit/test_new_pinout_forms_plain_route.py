"""The dual op-amp, the diode KA forms, the grouped-drain MOSFET, and the color LEDs.

Every test runs on the plain route from the templates this package ships.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from eedesigncore import Pin, SchPolyline, SymbolLib

from eedesignsymbols.generators import diode, led, mosfet
from eedesignsymbols.generators.common import pins_of, template_file
from eedesignsymbols.generators.opamp import dual, single
from eedesignsymbols.generators.opamp.config import ConfigError, PinSpec, load_config
from eedesignsymbols.generators.pinout import GeneratorError, PinOrder
from eedesignsymbols.symbol_fields import DESCRIPTION_FIELD, get_field
from eedesignsymbols.writing import Outcome

pytestmark = pytest.mark.usefixtures("a_clean_tool_tree")

KICAD_FIELDS = ["Reference", "Value", "Footprint", "Datasheet", "Description"]
OPAMP_DIR = Path(single.__file__).parent
SINGLE_CONFIG = OPAMP_DIR / "single_opamp_parts.yaml"
DUAL_CONFIG = OPAMP_DIR / "dual_opamp_parts.yaml"
STAMP = "0.2.0+g1234567"


def opamp_template() -> SymbolLib:
    return SymbolLib.from_file(template_file(single.TEMPLATE_NAME))


def unit_pins(unit) -> list[Pin]:
    return [item for item in unit.items if isinstance(item, Pin)]


def numbers(symbol) -> dict[str, str]:
    return {str(pin.name): str(pin.number) for pin in pins_of(symbol)}


class TestTheDualOpAmp:
    def test_it_has_two_channel_units_and_one_supply_unit(self):
        template = opamp_template()
        original = template.model_dump()

        symbol = dual.build(template, load_config(DUAL_CONFIG)[0], tool_version=STAMP).symbols[0]

        assert template.model_dump() == original
        assert symbol.name == "OPAMP_DUAL_8P_PINOUT01_SYMGEN"
        assert get_field(symbol, "Value") == symbol.name
        assert [f.name for f in symbol.fields] == KICAD_FIELDS
        assert [u.unit_display_name for u in symbol.units] == ["A", "B", "PWR"]
        assert all(u.name.startswith(f"{symbol.name}_") for u in symbol.units)
        assert [{str(p.name) for p in unit_pins(u)} for u in symbol.units] == [
            {"INA+", "INA-", "OUTA"},
            {"INB+", "INB-", "OUTB"},
            {"V+", "V-"},
        ]
        description = get_field(symbol, DESCRIPTION_FIELD) or ""
        assert "1=CHA.OUTA 2=CHA.INA- 3=CHA.INA+ 4=V-" in description
        assert "5=CHB.INB+ 6=CHB.INB- 7=CHB.OUTB 8=V+" in description

    @pytest.mark.parametrize(("slot", "y"), [("EN", -1.27), ("~{EN}", 1.27)])
    def test_a_global_control_goes_on_the_left_of_the_supply_unit(self, slot, y):
        spec = load_config(DUAL_CONFIG)[0]
        spec = replace(spec, pins={**spec.pins, slot: PinSpec("SHDN", ("9",))})

        units = dual.build(opamp_template(), spec, tool_version=STAMP).symbols[0].units

        control = next(p for p in unit_pins(units[2]) if p.number == "9")
        assert control.name == "SHDN"
        assert control.position[1] == y
        assert control.angle == 0.0

    def test_every_configured_form_builds_once(self):
        specs = load_config(DUAL_CONFIG)
        built = [dual.build(opamp_template(), s, tool_version=STAMP) for s in specs]
        names = {lib.symbols[0].name for lib in built}
        assert len(names) == len(specs) == 8

    def test_a_selected_form_is_written_once_and_a_rerun_is_unchanged(self, tmp_path):
        first = single.generate_all(DUAL_CONFIG, None, tmp_path, channels=2, only=["8P_PINOUT02"])
        again = single.generate_all(DUAL_CONFIG, None, tmp_path, channels=2, only=["8P_PINOUT02"])

        assert [r.outcome for r in first] == [Outcome.CREATED]
        assert [r.outcome for r in again] == [Outcome.UNCHANGED]
        assert [p.name for p in tmp_path.iterdir()] == ["OPAMP_DUAL_8P_PINOUT02_SYMGEN.kicad_sym"]

    def test_an_unknown_code_writes_nothing(self, tmp_path):
        with pytest.raises(single.GeneratorError, match="Unknown part"):
            single.generate_all(DUAL_CONFIG, None, tmp_path, channels=2, only=["typo"])
        assert list(tmp_path.iterdir()) == []

    def test_the_wrong_command_for_the_channel_count_writes_nothing(self, tmp_path):
        with pytest.raises(single.GeneratorError, match="channel count"):
            single.generate_all(DUAL_CONFIG, None, tmp_path)
        with pytest.raises(single.GeneratorError, match="channel count"):
            single.generate_all(SINGLE_CONFIG, None, tmp_path, channels=2)
        assert list(tmp_path.iterdir()) == []

    def test_the_command_writes_every_form(self, tmp_path):
        args = ["--config", str(DUAL_CONFIG), "--dir", str(tmp_path), "--no-preview"]

        assert dual.main(args) == 0
        assert len(list(tmp_path.glob("OPAMP_DUAL_*_SYMGEN.kicad_sym"))) == 8

    def test_a_dual_row_refuses_a_shared_pin_number(self, tmp_path):
        row = yaml.safe_load(DUAL_CONFIG.read_text(encoding="utf-8"))["parts"][0]
        row["pins"]["CHB.OUT"]["number"] = "1"
        path = tmp_path / "bad.yaml"
        path.write_text(yaml.safe_dump({"parts": [row]}), encoding="utf-8")

        with pytest.raises(ConfigError, match="repeats"):
            load_config(path)


class TestTheSingleOpAmp:
    def test_a_longer_control_name_gets_smaller_text(self):
        spec = next(s for s in load_config(SINGLE_CONFIG) if s.code == "6P_PINOUT03")
        sizes = []
        for name in ("EN", "ENABLE", "ENABLE_CHANNEL"):
            pins = {**spec.pins, "EN": PinSpec(name, ("5",))}
            built = single.build(opamp_template(), replace(spec, pins=pins), tool_version=STAMP)
            pin = next(p for p in pins_of(built.symbols[0]) if p.name == name)
            sizes.append(pin.name_text_size)

        assert sizes[0] > sizes[1] > sizes[2] > 0

    def test_a_dual_row_is_refused(self):
        with pytest.raises(single.GeneratorError, match="dual generator"):
            single.build(opamp_template(), load_config(DUAL_CONFIG)[0])

    def test_previous_names_must_be_plain_base_names(self, tmp_path):
        row = yaml.safe_load(SINGLE_CONFIG.read_text(encoding="utf-8"))["parts"][0]
        row["previous_names"] = ["OPAMP_SINGLE_5p_SYMGEN__1786580779999"]
        path = tmp_path / "bad.yaml"
        path.write_text(yaml.safe_dump({"parts": [row]}), encoding="utf-8")

        with pytest.raises(ConfigError, match="previous output name"):
            load_config(path)


class TestTheDiodeForms:
    def test_a_unidirectional_template_gives_ak_and_ka(self, tmp_path):
        template = template_file("_D_SI_SYMGEN_TEMPLATE")
        results = diode.UNIDIRECTIONAL.generate_all(template, tmp_path)

        built = {r.path.stem: numbers(SymbolLib.from_file(r.path).symbols[0]) for r in results}
        assert built == {
            "D_SI_AK_SYMGEN": {"A": "1", "K": "2"},
            "D_SI_KA_SYMGEN": {"K": "1", "A": "2"},
        }

    def test_a_bidirectional_template_gives_a1a2_and_ka(self, tmp_path):
        template = template_file("_D_TVS_BIDIR_SYMGEN_TEMPLATE")
        results = diode.BIDIRECTIONAL.generate_all(template, tmp_path)

        built = {r.path.stem: numbers(SymbolLib.from_file(r.path).symbols[0]) for r in results}
        assert built == {
            "D_TVS_BIDIR_A1A2_SYMGEN": {"A1": "1", "A2": "2"},
            "D_TVS_BIDIR_KA_SYMGEN": {"A2": "1", "A1": "2"},
        }

    def test_leds_writes_the_five_color_leds_only(self, tmp_path):
        assert diode.main(["--leds", "--dir", str(tmp_path), "--no-preview"]) == 0

        assert sorted(p.stem for p in tmp_path.glob("*.kicad_sym")) == [
            f"D_LED_{code}_SYMGEN" for code in sorted(led.LED_COLORS)
        ]

    def test_part_selects_one_color(self, tmp_path):
        args = ["--leds", "--part", "KA_RED", "--dir", str(tmp_path), "--no-preview"]

        assert diode.main(args) == 0
        assert [p.stem for p in tmp_path.glob("*.kicad_sym")] == ["D_LED_KA_RED_SYMGEN"]


class TestTheColorLeds:
    def test_each_color_form_colors_both_arrows(self):
        template = SymbolLib.from_file(template_file("_D_LED_SYMGEN_TEMPLATE"))
        for order in led.COLOR_ORDERS:
            symbol = led.FAMILY.build(template, order, tool_version=STAMP).symbols[0]
            arrows = [
                item
                for unit in symbol.units
                for item in unit.items
                if isinstance(item, SchPolyline) and tuple(item.pts) in led.LED_ARROW_PATHS
            ]
            assert len(arrows) == 2
            for arrow in arrows:
                color = arrow.stroke.color
                assert color is not None
                assert (color.r, color.g, color.b) == led.LED_COLORS[order.code]
            assert numbers(symbol) == {"K": "1", "A": "2"}
            assert (get_field(symbol, DESCRIPTION_FIELD) or "").endswith("LED (pins 1=K 2=A)")

    def test_the_led_command_writes_the_plain_and_color_forms(self, tmp_path):
        assert led.main(["--dir", str(tmp_path), "--no-preview"]) == 0

        assert len(list(tmp_path.glob("D_LED_*_SYMGEN.kicad_sym"))) == 7


class TestTheGroupedDrainMosfet:
    def test_one_drain_pin_carries_four_package_pins(self, tmp_path):
        args = ["--part", "6P_PINOUT01", "--dir", str(tmp_path), "--no-preview"]

        assert mosfet.main(args) == 0

        [path] = tmp_path.glob("*.kicad_sym")
        assert path.stem == "Q_NMOS_6P_PINOUT01_SYMGEN"
        pins = {str(p.name): p for p in pins_of(SymbolLib.from_file(path).symbols[0])}
        assert {name: str(p.number) for name, p in pins.items()} == {
            "G": "3",
            "S": "4",
            "D": "[1,2,5,6]",
        }
        assert pins["D"].number_text_size == 0

    def test_an_unknown_part_is_refused(self, tmp_path):
        with pytest.raises(SystemExit):
            mosfet.main(["--part", "typo", "--dir", str(tmp_path)])
        assert list(tmp_path.iterdir()) == []


class TestThePinOrderChecks:
    def test_a_number_group_must_cover_every_terminal(self):
        with pytest.raises(GeneratorError, match="physical pin"):
            PinOrder(("G", "S", "D"), numbers=(("1",), ("2",)))

    def test_a_package_pin_cannot_carry_two_terminals(self):
        with pytest.raises(GeneratorError, match="physical pin"):
            PinOrder(("G", "S", "D"), numbers=(("1",), ("2",), ("2", "3")))

    def test_a_pinout_code_must_be_a_plain_name(self):
        with pytest.raises(GeneratorError, match="pinout code"):
            PinOrder(("G", "S", "D"), name_code="6P PINOUT")
