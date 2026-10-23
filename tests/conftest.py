"""Fixtures every test can use. Nothing here imports a library rules package.

The golden files under ``tests/fixtures/`` are library assets in their library form.
A copy of this repository that leaves them out skips the tests that read them.
"""

from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from eedesignsymbols.version import tree_version

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN_NMOS = FIXTURES / "_Q_NMOS_SYMGEN_TEMPLATE__1786580778623.kicad_sym"
GOLDEN_NPN = FIXTURES / "_Q_NPN_SYMGEN_TEMPLATE__1786641124085.kicad_sym"
GOLDEN_NIGBT = FIXTURES / "_Q_NIGBT_SYMGEN_TEMPLATE__1786649736018.kicad_sym"
GOLDEN_DIODE = FIXTURES / "D_SI__1786725367396.kicad_sym"
GOLDEN_DIODE_BIDIR = FIXTURES / "D_TVS_BIDIR__1786725367409.kicad_sym"
GOLDEN_LED = FIXTURES / "_D_LED_SYMGEN_TEMPLATE__1788888267845.kicad_sym"
GOLDEN_LED_MP = FIXTURES / "_D_LED_MP_SYMGEN_TEMPLATE__1788889235331.kicad_sym"


def present(golden: Path) -> Path:
    """Return ``golden``, or skip the test when the file is absent."""
    if not golden.is_file():
        pytest.skip(f"the golden asset {golden.name} is absent")
    return golden


@pytest.fixture(autouse=True)
def _resolve_the_tree_version_afresh() -> Iterator[None]:
    """Clear the process-wide version cache around every test.

    :func:`~eedesignsymbols.version.tree_version` caches, so one generator run stamps
    every asset alike and pays for the git probe once. That cache would otherwise
    carry a value monkeypatched by one test into the next one.
    """
    tree_version.cache_clear()
    yield
    tree_version.cache_clear()


@pytest.fixture(autouse=True)
def preview_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[list[tuple[Path, str]], Path]]:
    """Stop every test from rendering a real gallery, and record what it asked for.

    :func:`~eedesignsymbols.generators.pinout.run_many` builds a preview after any run
    that writes, so every generator command line test would otherwise start
    ``kicad-cli`` once per generated symbol. Measured on the suite as it stood: 258
    SVG renders, a 3x slower run, and a ``.preview`` directory written into whatever
    directory pytest happened to start in, because the default output root is
    :func:`pathlib.Path.cwd`.

    Autouse, because the cost lands on every test that writes rather than on the few
    that care about the preview. A test that asserts on the preview takes
    ``preview_calls`` as an argument and reads the recorded calls. A test that needs
    the real function calls it directly.

    Each recorded call is the ``written`` pairs and the preview directory.
    """
    from eedesignsymbols.generators import pinout

    calls: list[tuple[list[tuple[Path, str]], Path]] = []

    def _record(written: Sequence[tuple[Path, str]], preview_dir: Path) -> Path:
        calls.append((list(written), preview_dir))
        return preview_dir / "gallery.html"

    monkeypatch.setattr(pinout, "build_preview", _record)
    return calls


CLEAN_TOOL_TREE_STAMP = "0.1.0+g1234567"
"""A stamp that names a commit and no modification, so a write guard permits it."""


@pytest.fixture
def a_clean_tool_tree(monkeypatch: pytest.MonkeyPatch) -> str:
    """Make a generator command see a tool tree it can name. Returns the stamp.

    :func:`~eedesignsymbols.generators.pinout.run_many` refuses to write unless
    :func:`~eedesignsymbols.version.identifies_the_tree` answers True, because that
    command writes the provenance stamp (ADR-109). Every generator command line test
    would otherwise fail whenever the developer's own tree is modified, which is every
    run during development. BS-75 predicted exactly that.

    The patch is on :func:`~eedesignsymbols.generators.common.tool_version`, which is both
    the function the guard reads and the function that writes the ``generator_version``
    header token, so the guard and the written file agree. A test that exercises the
    refusal patches the same seam with a stamp that fails it.

    Used through ``pytestmark = pytest.mark.usefixtures("a_clean_tool_tree")`` at the
    top of each generator command line test module.
    """
    from eedesignsymbols.generators import common

    monkeypatch.setattr(common, "tool_version", lambda: CLEAN_TOOL_TREE_STAMP)
    return CLEAN_TOOL_TREE_STAMP


@pytest.fixture
def golden_nmos() -> Path:
    """A real library template: G/S/D pins, versioned name, governance fields, CRLF."""
    return present(GOLDEN_NMOS)


@pytest.fixture
def golden_npn() -> Path:
    """A real library template with a different terminal set: B/C/E pins."""
    return present(GOLDEN_NPN)


@pytest.fixture
def golden_nigbt() -> Path:
    """A third terminal set, G/C/E, which overlaps both of the others."""
    return present(GOLDEN_NIGBT)


@pytest.fixture
def golden_diode() -> Path:
    """A real hand-drawn library diode, before promotion: 2 pins named K and A.

    Adopted but not generated, so it carries the governance fields and the
    ``symgen:manual`` role. This is what promotion consumes.
    """
    return present(GOLDEN_DIODE)


@pytest.fixture
def golden_diode_bidir() -> Path:
    """A bidirectional diode, also pre-promotion. Its pins become A1 and A2."""
    return present(GOLDEN_DIODE_BIDIR)


@pytest.fixture
def golden_led() -> Path:
    """The real LED template, already promoted: A and K pins carrying their own names.

    Unlike the diode goldens, which are hand-drawn parts awaiting promotion, this one
    is a finished template. It is what `led.FAMILY` consumes.
    """
    return present(GOLDEN_LED)


@pytest.fixture
def golden_led_mp() -> Path:
    """The real mounting-pad LED template: A, K and MP pins carrying their own names.

    MP is a passive pad rather than an electrical terminal of the diode, which is
    what makes this a different terminal set and therefore a different family.
    """
    return present(GOLDEN_LED_MP)
