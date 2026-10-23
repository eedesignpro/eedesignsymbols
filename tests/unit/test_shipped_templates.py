"""The template files this package ships, and the plain lookup that reads them.

Each template is a static ``.kicad_sym`` file in ``src/eedesignsymbols/templates/``, named
for its symbol with no version number. It carries the drawing, the pin letters, and the
KiCad fields ``Reference``, ``Value``, ``Footprint``, ``Datasheet``, ``Description``,
``ki_keywords`` and, on some, ``ki_fp_filters``. It carries no library governance field.

The checks cover the files themselves (the count, the names, the fields) and the
plain lookup that every generator uses to read them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from eedesigncore import SymbolLib

from eedesignsymbols.generators import bjt, diode, igbt, jfet, led, mosfet, registry
from eedesignsymbols.generators.common import TEMPLATE_DIR, template_file
from eedesignsymbols.generators.opamp import single

SHIPPED = (
    "_D_ESD_BIDIR_SYMGEN_TEMPLATE",
    "_D_ESD_UNI_SYMGEN_TEMPLATE",
    "_D_LED_MP_SYMGEN_TEMPLATE",
    "_D_LED_SYMGEN_TEMPLATE",
    "_D_LED_THERM_SYMGEN_TEMPLATE",
    "_D_SCHOTTKY_SYMGEN_TEMPLATE",
    "_D_SIC_SYMGEN_TEMPLATE",
    "_D_SI_SYMGEN_TEMPLATE",
    "_D_TVS_BIDIR_SYMGEN_TEMPLATE",
    "_D_TVS_UNI_SYMGEN_TEMPLATE",
    "_D_ZENER_SYMGEN_TEMPLATE",
    "_OPAMP_SINGLE_SYMGEN_TEMPLATE",
    "_Q_NGAN_KELVIN_SYMGEN_TEMPLATE",
    "_Q_NGAN_SYMGEN_TEMPLATE",
    "_Q_NIGBT_SYMGEN_TEMPLATE",
    "_Q_NJFET_SYMGEN_TEMPLATE",
    "_Q_NMOS_KELVIN_SYMGEN_TEMPLATE",
    "_Q_NMOS_SYMGEN_TEMPLATE",
    "_Q_NPN_SYMGEN_TEMPLATE",
    "_Q_PJFET_SYMGEN_TEMPLATE",
    "_Q_PMOS_SYMGEN_TEMPLATE",
    "_Q_PNP_SYMGEN_TEMPLATE",
)
"""Written out, so a file that appears or disappears is a test failure."""

KICAD_FIELDS = {"Reference", "Value", "Footprint", "Datasheet", "Description"}


def load(path: Path) -> SymbolLib:
    lib = SymbolLib.from_file(path)
    assert len(lib.symbols) == 1, path.name
    return lib


class TestTheFiles:
    def test_the_folder_holds_exactly_the_shipped_templates(self):
        assert sorted(p.stem for p in TEMPLATE_DIR.glob("*.kicad_sym")) == sorted(SHIPPED)

    @pytest.mark.parametrize("name", SHIPPED)
    def test_the_symbol_is_named_for_its_file(self, name):
        symbol = load(template_file(name)).symbols[0]

        assert symbol.name == name
        assert {f.name: f.value for f in symbol.fields}["Value"] == name
        assert all(unit.name.startswith(f"{name}_") for unit in symbol.units)

    @pytest.mark.parametrize("name", SHIPPED)
    def test_it_carries_only_kicad_fields(self, name):
        fields = {f.name for f in load(template_file(name)).symbols[0].fields}

        assert fields == KICAD_FIELDS

    @pytest.mark.parametrize("name", SHIPPED)
    def test_its_keywords_carry_no_governance_pair(self, name):
        keywords = load(template_file(name)).symbols[0].keywords or ""

        assert keywords
        assert [token for token in keywords.split() if ":" in token] == []

    @pytest.mark.parametrize("name", SHIPPED)
    def test_it_states_that_it_is_a_template(self, name):
        fields = {f.name: f.value for f in load(template_file(name)).symbols[0].fields}

        assert "SYMGEN TEMPLATE - not a usable part." in fields["Description"]

    def test_every_declared_template_ships(self):
        declared = {*registry.declared_templates(), single.TEMPLATE_NAME}

        assert declared <= set(SHIPPED)

    def test_four_shipped_templates_have_no_generator_yet(self):
        """Drawings ready for a later family. Listed so that a new family is noticed."""
        declared = {*registry.declared_templates(), single.TEMPLATE_NAME}

        assert set(SHIPPED) - declared == {
            "_D_LED_THERM_SYMGEN_TEMPLATE",
            "_Q_NGAN_KELVIN_SYMGEN_TEMPLATE",
            "_Q_NGAN_SYMGEN_TEMPLATE",
            "_Q_NMOS_KELVIN_SYMGEN_TEMPLATE",
        }


class TestEveryFamilyReadsTheShippedTemplates:
    @pytest.mark.parametrize("module", [bjt, diode, igbt, jfet, led, mosfet])
    def test_the_default_lookup_finds_every_declared_template(self, module):
        families = getattr(module, "FAMILIES", None) or (module.FAMILY,)
        for family in families:
            found = family.declared_templates()

            assert [p.stem for p in found] == list(family.templates)
            assert all(p.parent == TEMPLATE_DIR for p in found)

    def test_the_single_op_amp_generator_reads_its_shipped_template(self, tmp_path):
        config = Path(single.__file__).with_name("single_opamp_parts.yaml")

        results = single.generate_all(config, None, tmp_path)

        assert len(results) == 8
        assert all(r.path.is_file() for r in results)


ADAPTED_FROM_KICAD = (
    "_Q_NPN",
    "_Q_PNP",
    "_Q_NIGBT",
    "_Q_NMOS",
    "_Q_NMOS_KELVIN",
    "_Q_PMOS",
    "_Q_NGAN",
    "_Q_NGAN_KELVIN",
    "_Q_NJFET",
    "_Q_PJFET",
)
"""The ten templates adapted from KiCad stock symbols, under CC BY-SA 4.0."""


class TestTheNotice:
    def test_the_notice_names_exactly_the_adapted_templates(self):
        text = (TEMPLATE_DIR / "NOTICE").read_text(encoding="utf-8")
        listed = text.split("Adapted files:")[1].split("(each")[0]
        names = [part.strip() for part in listed.replace("\n", " ").split(",")]

        assert names == list(ADAPTED_FROM_KICAD)
        assert "CC BY-SA 4.0" in text

    def test_every_adapted_template_ships(self):
        assert {f"{name}_SYMGEN_TEMPLATE" for name in ADAPTED_FROM_KICAD} <= set(SHIPPED)
