"""Verify real Git source identity without changing the working project."""

import subprocess

from eedesignsymbols import version


def test_source_commit_and_dirty_marker_follow_only_the_generator(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-b", "main")
    project = tmp_path / "generator"
    project.mkdir()
    version_file = project / "VERSION"
    version_file.write_text("0.1.0\n", encoding="utf-8")
    source = project / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    git("add", "generator/VERSION", "generator/source.py")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "test: create source identity fixture",
    )
    monkeypatch.setattr(version, "PROJECT_ROOT", project)
    monkeypatch.setattr(version, "VERSION_FILE", version_file)
    expected = "0.1.0+g" + git("rev-parse", "--short=7", "HEAD")
    assert version.tree_version() == expected

    (tmp_path / "unrelated.txt").write_text("Sibling change\n", encoding="utf-8")
    version.tree_version.cache_clear()
    assert version.tree_version() == expected

    source.write_text("value = 2\n", encoding="utf-8")
    version.tree_version.cache_clear()
    assert version.tree_version() == expected + ".dirty"
