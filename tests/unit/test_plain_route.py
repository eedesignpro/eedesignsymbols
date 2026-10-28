"""The plain route: plain template files in, plain KiCad symbol files out.

This is the default route. It reads ``<folder>/<name>.kicad_sym``, adds no field of
its own, and writes ``<out>/<name>.kicad_sym`` through the ``kicad-file-io`` writer.
Nothing in this module needs a library rules package.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from eedesigncore import SymbolLib

from eedesignsymbols import version
from eedesignsymbols.format_version import FormatVersionError
from eedesignsymbols.generators import bjt, diode, igbt, jfet, led, mosfet, registry
from eedesignsymbols.generators.common import (
    TEMPLATE_DIR,
    generated_name,
    is_output_name,
    is_template_name,
    template_file,
    without_version_tail,
)
from eedesignsymbols.generators.opamp import single
from eedesignsymbols.generators.pinout import Family, GeneratorError, PinOrder
from eedesignsymbols.symbol_fields import get_field
from eedesignsymbols.writing import PLAIN, Outcome, default_route

pytestmark = pytest.mark.usefixtures("a_clean_tool_tree")

KICAD_FIELDS = ["Reference", "Value", "Footprint", "Datasheet", "Description"]


def load(path: Path) -> SymbolLib:
    lib = SymbolLib.from_file(path)
    assert len(lib.symbols) == 1
    return lib


def drawing(lib: SymbolLib) -> list[list[dict[str, Any]]]:
    return [[item.model_dump() for item in unit.items] for unit in lib.symbols[0].units]


class TestTheDefault:
    def test_the_plain_route_is_the_default(self):
        assert default_route() is PLAIN

    def test_its_template_folder_is_the_shipped_one(self):
        assert PLAIN.template_dir() == TEMPLATE_DIR


class TestTheLookup:
    def test_a_family_finds_its_templates_in_the_shipped_folder(self):
        found = mosfet.FAMILY.declared_templates()

        assert found == [
            TEMPLATE_DIR / "_Q_NMOS_SYMGEN_TEMPLATE.kicad_sym",
            TEMPLATE_DIR / "_Q_PMOS_SYMGEN_TEMPLATE.kicad_sym",
        ]

    def test_a_versioned_file_is_not_read(self, tmp_path):
        """The lookup is the plain name. A version number is not parsed."""
        source = template_file("_Q_NMOS_SYMGEN_TEMPLATE")
        (tmp_path / "_Q_NMOS_SYMGEN_TEMPLATE__1786580770001.kicad_sym").write_bytes(
            source.read_bytes()
        )

        with pytest.raises(GeneratorError, match="no template file for"):
            mosfet.FAMILY.declared_templates(tmp_path)

    def test_the_message_names_every_missing_template_and_the_folder(self, tmp_path):
        with pytest.raises(GeneratorError) as caught:
            mosfet.FAMILY.declared_templates(tmp_path)

        message = str(caught.value)
        assert "_Q_NMOS_SYMGEN_TEMPLATE" in message
        assert "_Q_PMOS_SYMGEN_TEMPLATE" in message
        assert str(tmp_path) in message

    def test_a_template_with_the_wrong_pins_is_refused(self, tmp_path):
        (tmp_path / "_Q_NMOS_SYMGEN_TEMPLATE.kicad_sym").write_bytes(
            template_file("_Q_NPN_SYMGEN_TEMPLATE").read_bytes()
        )
        family = Family(
            name="t",
            terminals=("G", "S", "D"),
            templates=("_Q_NMOS_SYMGEN_TEMPLATE",),
            orders=(PinOrder(("G", "S", "D")),),
        )

        with pytest.raises(GeneratorError, match="its pins are"):
            family.declared_templates(tmp_path)

    def test_an_old_format_template_is_refused(self, tmp_path):
        text = template_file("_D_SI_SYMGEN_TEMPLATE").read_text(encoding="utf-8")
        old = tmp_path / "_D_SI_SYMGEN_TEMPLATE.kicad_sym"
        old.write_text(text.replace("(version 20251024)", "(version 20231120)", 1), "utf-8")

        with pytest.raises(FormatVersionError, match="kicad-cli sym upgrade"):
            diode.UNIDIRECTIONAL.generate_all(old, tmp_path)


class TestTheOutput:
    @pytest.mark.parametrize(
        "family",
        [
            bjt.FAMILY,
            diode.UNIDIRECTIONAL,
            diode.BIDIRECTIONAL,
            igbt.FAMILY,
            jfet.FAMILY,
            led.FAMILY,
            led.WITH_MOUNTING_PAD,
            mosfet.FAMILY,
        ],
        ids=lambda f: f"{f.name}-{'/'.join(f.terminals)}",
    )
    def test_every_family_writes_plain_files(self, tmp_path, family):
        for template in family.declared_templates():
            results = family.generate_all(template, tmp_path)

            name = load(template).symbols[0].name
            assert len(results) == sum(order.applies_to(name) for order in family.orders)
            for result in results:
                assert result.outcome is Outcome.CREATED
                assert result.path.name == f"{load(result.path).symbols[0].name}.kicad_sym"

    def test_the_output_carries_only_kicad_fields(self, tmp_path):
        template = template_file("_Q_NMOS_SYMGEN_TEMPLATE")
        result = mosfet.FAMILY.generate_all(template, tmp_path)[0]
        symbol = load(result.path).symbols[0]

        assert [f.name for f in symbol.fields] == KICAD_FIELDS
        assert symbol.name == "Q_NMOS_GSD_SYMGEN"
        assert get_field(symbol, "Value") == "Q_NMOS_GSD_SYMGEN"
        assert get_field(symbol, "Description") == "N-MOSFET transistor (pins 1=G 2=S 3=D)"
        assert symbol.keywords == "NMOS N-MOS"

    def test_every_unit_name_starts_with_the_symbol_name(self, tmp_path):
        """KiCad refuses to load a library whose unit names do not match their parent."""
        template = template_file("_Q_NPN_SYMGEN_TEMPLATE")
        for result in bjt.FAMILY.generate_all(template, tmp_path):
            symbol = load(result.path).symbols[0]
            assert [u.name for u in symbol.units] == [
                f"{symbol.name}_{u.unit_index}_{u.body_style_index}" for u in symbol.units
            ]

    def test_the_header_names_the_tool_and_the_generator(self, tmp_path):
        template = template_file("_Q_NPN_SYMGEN_TEMPLATE")
        lib = load(bjt.FAMILY.generate_all(template, tmp_path)[0].path)

        assert lib.generator == "eedesignsymbols:bjt_pinout"
        assert version.names_a_commit(lib.generator_version)

    def test_the_drawing_is_the_template_drawing_with_new_pin_numbers(self, tmp_path):
        template_path = template_file("_Q_NPN_SYMGEN_TEMPLATE")
        template = load(template_path)
        result = bjt.FAMILY.generate_all(template_path, tmp_path)[0]
        output = load(result.path)

        old, new = drawing(template), drawing(output)
        for unit_old, unit_new in zip(old, new, strict=True):
            for item_old, item_new in zip(unit_old, unit_new, strict=True):
                if "number" in item_old:
                    item_old = {**item_old, "number": None}
                    item_new = {**item_new, "number": None}
                assert item_old == item_new
        numbers = {
            str(p.name): str(p.number)
            for u in output.symbols[0].units
            for p in u.items
            if hasattr(p, "number")
        }
        assert numbers == {"B": "1", "C": "2", "E": "3"}

    def test_the_single_op_amp_generator_writes_plain_files(self, tmp_path):
        config = Path(single.__file__).with_name("single_opamp_parts.yaml")

        results = single.generate_all(config, None, tmp_path)

        assert len(results) == 15
        for result in results:
            symbol = load(result.path).symbols[0]
            assert [f.name for f in symbol.fields] == KICAD_FIELDS
            assert result.path.name == f"{symbol.name}.kicad_sym"


class TestRerunning:
    def test_a_rerun_writes_nothing(self, tmp_path):
        template = template_file("_Q_NMOS_SYMGEN_TEMPLATE")
        mosfet.FAMILY.generate_all(template, tmp_path)
        before = {p: p.read_bytes() for p in tmp_path.iterdir()}

        again = mosfet.FAMILY.generate_all(template, tmp_path)

        assert {r.outcome for r in again} == {Outcome.UNCHANGED}
        assert {p: p.read_bytes() for p in tmp_path.iterdir()} == before

    def test_a_changed_file_is_overwritten(self, tmp_path):
        template = template_file("_Q_NMOS_SYMGEN_TEMPLATE")
        first = mosfet.FAMILY.generate_all(template, tmp_path)[0]
        first.path.write_text("edited", encoding="utf-8")

        again = mosfet.FAMILY.generate_all(template, tmp_path)[0]

        assert again.outcome is Outcome.UPDATED
        assert load(again.path).symbols[0].name == "Q_NMOS_GSD_SYMGEN"

    def test_a_dry_run_writes_nothing_and_reports_what_it_would_do(self, tmp_path):
        template = template_file("_Q_NMOS_SYMGEN_TEMPLATE")

        planned = mosfet.FAMILY.generate_all(template, tmp_path, dry_run=True)

        assert {r.outcome for r in planned} == {Outcome.CREATED}
        assert list(tmp_path.iterdir()) == []


class TestTheCommand:
    def test_it_writes_into_dir_from_the_shipped_templates(self, tmp_path):
        assert mosfet.main(["--dir", str(tmp_path)]) == 0

        # Six orderings of each template, and the grouped-drain form of the NMOS one.
        assert len(list(tmp_path.glob("Q_*MOS_*_SYMGEN.kicad_sym"))) == 13

    def test_templates_names_another_folder(self, tmp_path, capsys):
        empty = tmp_path / "empty"
        empty.mkdir()

        assert mosfet.main(["--dir", str(tmp_path), "--templates", str(empty)]) == 1
        assert "no template file for" in capsys.readouterr().out
        assert list(tmp_path.glob("*.kicad_sym")) == []

    def test_a_second_run_reports_unchanged(self, tmp_path, capsys):
        mosfet.main(["--dir", str(tmp_path)])
        capsys.readouterr()

        assert mosfet.main(["--dir", str(tmp_path)]) == 0
        assert "13 unchanged" in capsys.readouterr().out

    def test_the_op_amp_command_writes_from_the_shipped_template(self, tmp_path):
        config = Path(single.__file__).with_name("single_opamp_parts.yaml")

        code = single.main(["--config", str(config), "--dir", str(tmp_path), "--no-preview"])

        assert code == 0
        assert len(list(tmp_path.glob("OPAMP_SINGLE_*_SYMGEN.kicad_sym"))) == 15

    def test_every_family_runs_from_the_command(self, tmp_path):
        for module in (bjt, diode, igbt, jfet, led, mosfet):
            assert module.main(["--dir", str(tmp_path), "--no-preview"]) == 0

        expected = set(registry.expected_outputs())
        written = {p.stem for p in tmp_path.glob("*.kicad_sym")}
        assert written == expected


class TestNames:
    def test_a_version_tail_is_ignored(self):
        assert without_version_tail("_Q_NMOS_SYMGEN_TEMPLATE__1786580778623") == (
            "_Q_NMOS_SYMGEN_TEMPLATE"
        )
        assert generated_name("_Q_NMOS_SYMGEN_TEMPLATE__1786580778623", "GSD") == (
            "Q_NMOS_GSD_SYMGEN"
        )

    def test_a_template_is_not_an_output(self):
        assert is_template_name("_Q_NMOS_SYMGEN_TEMPLATE")
        assert not is_output_name("_Q_NMOS_SYMGEN_TEMPLATE")
        assert is_output_name("Q_NMOS_GSD_SYMGEN")


class TestTheStampPredicates:
    @pytest.mark.parametrize(
        ("stamp", "dirty", "commit"),
        [
            ("0.1.0", False, False),
            ("0.1.0+g4f2a1c9", False, True),
            ("0.1.0+g4f2a1c9.dirty", True, True),
        ],
    )
    def test_the_two_predicates(self, stamp, dirty, commit):
        assert version.is_dirty(stamp) is dirty
        assert version.names_a_commit(stamp) is commit
