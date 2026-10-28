"""The write guard in a source tree and in an installed package.

In a source tree, the folder that holds the ``VERSION`` file, a generator command
writes only from a stamp that names a clean commit. ADR-109, unchanged.

In an installed package there is no ``VERSION`` file beside the code and no git tree.
The command then accepts the installed release number, and nothing else. Operator
decision, 2026-10-22.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eedesignsymbols import version
from eedesignsymbols.generators import common, mosfet


@pytest.fixture
def installed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> str:
    """Make this process look like an installed package of release 0.1.0."""
    monkeypatch.setattr(version, "VERSION_FILE", tmp_path / "no-version-file-here")
    monkeypatch.setattr(version, "installed_version", lambda: "0.1.0")
    return "0.1.0"


@pytest.fixture
def source_tree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> str:
    """Make this process look like a source tree whose git probe did not answer."""
    version_file = tmp_path / "VERSION"
    version_file.write_text("0.1.0\n", encoding="utf-8")
    monkeypatch.setattr(version, "VERSION_FILE", version_file)
    monkeypatch.setattr(version, "installed_version", lambda: "0.1.0")
    return "0.1.0"


class TestTheRule:
    def test_an_installed_release_is_permitted(self, installed):
        assert version.is_installed_release("0.1.0")
        assert version.write_permitted("0.1.0")

    def test_another_number_is_refused_in_an_installed_package(self, installed):
        assert not version.write_permitted("0.1.1")

    def test_a_dirty_stamp_is_refused_in_an_installed_package(self, installed):
        assert not version.write_permitted("0.1.0.dirty")

    def test_a_source_tree_keeps_the_strict_rule(self, source_tree):
        """ADR-109 unchanged: a stamp that names no commit is refused."""
        assert not version.is_installed_release("0.1.0")
        assert not version.write_permitted("0.1.0")

    def test_a_clean_commit_is_permitted_everywhere(self, source_tree):
        assert version.write_permitted("0.1.0+g4f2a1c9")
        assert not version.write_permitted("0.1.0+g4f2a1c9.dirty")


class TestTheCommand:
    def test_an_installed_package_writes_without_allow_dirty(
        self, installed, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(common, "tool_version", lambda: "0.1.0")
        out = tmp_path / "out"
        out.mkdir()

        assert mosfet.main(["--dir", str(out), "--no-preview"]) == 0
        assert len(list(out.glob("*.kicad_sym"))) == 13

    def test_a_source_tree_without_a_commit_is_refused(
        self, source_tree, monkeypatch, tmp_path, capsys
    ):
        monkeypatch.setattr(common, "tool_version", lambda: "0.1.0")
        out = tmp_path / "out"
        out.mkdir()

        assert mosfet.main(["--dir", str(out), "--no-preview"]) == 1
        assert "names no commit" in capsys.readouterr().out
        assert list(out.iterdir()) == []
