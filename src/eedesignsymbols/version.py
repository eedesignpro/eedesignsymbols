"""What version of this tool is running, precise enough to rebuild an asset from.

A generated asset records the pipeline that produced it, and a release tag alone
does not identify it. The normal development case is a generator run from a source
checkout with no install, which reports no release version at all. So the version
this module returns carries a commit identifier: ``0.1.0+g4f2a1c9``.

**A modified working tree is marked.** An asset built from one is not
reconstructable, so the stamp reads ``0.1.0+g4f2a1c9.dirty``. Such a stamp is
acceptable for local iteration and must not enter a shared library. Operator decision,
2026-08-17: the token is ``.dirty``, appended inside the local version segment,
which keeps the whole string a valid PEP 440 local version.

**A stamp that names no commit is refused by the same guards.** Every git failure
collapses into "no git information", and the stamp then carries neither a commit nor
the dirty marker, so :func:`is_dirty` answers False for a tree whose state nothing
determined. A write guard therefore asks :func:`identifies_the_tree`, which is a
positive question. ADR-109.

Two callers want it: the ``generator_version`` header token, and the
``_SYM.GENERATOR`` field.

WHERE THE TWO PREDICATES WENT

:func:`is_dirty` and :func:`names_a_commit` read the shape of a stamp. They are
defined here, beside the code that mints the stamp.

RESOLUTION ORDER

1. A git checkout of this project answers, and the base number comes from the
   ``VERSION`` file. This is the case that closes BS-29: an editable install whose
   recorded metadata has gone stale used to stamp ``0.0.0``, and the file cannot go
   stale because hatchling reads the same file to build the wheel.
2. No git information, so the installed package metadata answers. This is the
   installed-wheel case, where there is no checkout to describe.
3. No metadata either, so the ``VERSION`` file answers on its own.
4. Nothing is available, so :data:`UNKNOWN_VERSION`.

SAFETY OF THE GIT PROBE

Security Rules 6 and 7 apply, and this is the only subprocess in the package:

- The argument list is fixed. No caller supplies any part of it, and nothing from
  a file or an environment variable reaches it.
- ``git`` is resolved to an absolute path found on ``PATH``, and a resolution that
  comes from the process working directory is refused. See :func:`_resolve_git`,
  which records the measurement behind that.
- ``shell`` is False, stated explicitly rather than left to the default.
- A timeout is set, so a hung or network-backed git cannot stall a generator.
- Every failure is one outcome, "no git information". A missing binary, a
  directory that is not a work tree, a non-zero exit, a timeout, and unreadable
  output are not distinguished, because none of them changes what the caller does.
- The probe runs only when this project's own ``VERSION`` file sits beside the
  package. Without that guard an installed copy inside somebody else's repository
  would report that repository's commit, which would be a false provenance record
  rather than a missing one.
- Nothing read here is logged, echoed, or interpolated into a command.
"""

from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_metadata_version
from pathlib import Path

DISTRIBUTION = "eedesignsymbols"
"""The installed distribution name, as ``pyproject.toml`` declares it."""

UNKNOWN_VERSION = "0.0.0"
"""Returned only when neither git, the metadata, nor the file answers."""

COMMIT_PREFIX = "+g"
"""Opens the PEP 440 local version segment that carries the commit.

A library rules package may hold a copy of this constant.
"""

DIRTY_MARKER = ".dirty"
"""Marks a stamp built from a working tree with uncommitted changes.

A library rules package may hold a copy, the same as :data:`COMMIT_PREFIX`.
"""


def is_dirty(version: str) -> bool:
    """True when ``version`` was stamped from a modified working tree.

    >>> is_dirty("0.1.0+g4f2a1c9.dirty")
    True
    """
    return version.endswith(DIRTY_MARKER)


def names_a_commit(version: str) -> bool:
    """True when ``version`` carries the commit segment that identifies its tree.

    A stamp that names no commit is no more reconstructable than a dirty one, so a
    write guard refuses both. ADR-109.

    >>> names_a_commit("0.1.0+g4f2a1c9")
    True
    >>> names_a_commit("0.1.0")
    False
    """
    return COMMIT_PREFIX in version


SHORT_SHA_LENGTH = 7

GIT_TIMEOUT_SECONDS = 10.0
"""Ceiling on the git probe. A generator must not hang on a provenance stamp."""

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent
"""The tool directory, which holds ``VERSION``, ``pyproject.toml`` and ``src``."""

VERSION_FILE = PROJECT_ROOT / "VERSION"

_VERSION_TEXT = re.compile(r"\A[0-9][0-9A-Za-z.+!-]{0,63}\Z")
"""What the ``VERSION`` file may hold. Validated because it is read input."""

_SHORT_SHA = re.compile(r"\A[0-9a-f]{4,40}\Z")
"""What ``git rev-parse --short`` may return. Validated for the same reason."""


def declared_version() -> str | None:
    """Return the number in the ``VERSION`` file, or None when it does not answer.

    Hatchling builds the wheel version from this same file, so it is the number
    this tree would release as. Validated rather than trusted: it becomes part of
    a field value written into a library asset.
    """
    try:
        text = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text if _VERSION_TEXT.match(text) else None


def installed_version() -> str | None:
    """Return the installed distribution version, or None when it is not installed."""
    try:
        return installed_metadata_version(DISTRIBUTION)
    except PackageNotFoundError:
        return None


def _resolve_git() -> str | None:
    """Return an absolute path to ``git`` found on ``PATH``, or None.

    **A resolution that comes from the process working directory is refused.**
    Iteration 3's finding Low 1 was that ``subprocess.run`` received the bare name
    ``"git"``, so Windows ``CreateProcess`` searched the working directory before
    ``PATH``. Resolving with :func:`shutil.which` alone did not close it, because
    ``shutil.which`` mirrors ``cmd.exe`` and inserts :data:`os.curdir` at the front
    of the search path on Windows. Passing ``path=`` does not remove that entry.
    Iteration 4 finding Low 4.

    **Measured, not reasoned.** On CPython 3.14.2 on Windows, in a directory holding
    a planted ``git.exe``, ``shutil.which("git")`` returned ``.\\git.EXE`` and
    ``shutil.which("git", path=os.environ["PATH"])`` returned the same. The insert is
    guarded by ``shutil._win_path_needs_curdir``, which honours the
    ``NoDefaultCurrentDirectoryInExePath`` environment variable, so the planted
    executable is found whenever that variable is unset. It is unset in a plain
    PowerShell session.

    Two checks, because either alone leaves a gap. The result must be absolute,
    which rejects the ``.\\git.EXE`` form directly. And its directory must not be
    the process working directory, which rejects an absolute resolution built from a
    ``PATH`` that holds the working directory itself. A git that genuinely lives in
    the working directory is refused too, and the caller then reports no git
    information rather than a stamp it cannot vouch for.
    """
    search_path = os.environ.get("PATH")
    if not search_path:
        # Only PATH is trusted. shutil.which would otherwise fall back to
        # os.defpath, which this project has no reason to search.
        return None
    resolved = shutil.which("git", path=search_path)
    if resolved is None:
        return None

    candidate = Path(resolved)
    if not candidate.is_absolute():
        return None
    try:
        if candidate.parent.resolve() == Path.cwd().resolve():
            return None
    except OSError:
        return None
    return str(candidate)


def _run_git(arguments: tuple[str, ...]) -> str | None:
    """Run one git command against :data:`PROJECT_ROOT`. None on any failure.

    See "Safety of the git probe" in the module docstring. ``arguments`` is always
    a literal from this module.
    """
    if not VERSION_FILE.is_file():
        # Not this project's source tree, so any commit found here would belong to
        # something else. A missing stamp beats a wrong one.
        return None
    # An absolute path from PATH only, never the working directory. See
    # _resolve_git for the measurement behind that.
    executable = _resolve_git()
    if executable is None:
        return None
    try:
        # The argument list is fixed and no part of it comes from a caller.
        completed = subprocess.run(
            [executable, "-C", str(PROJECT_ROOT), *arguments],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def git_description() -> tuple[str, bool] | None:
    """Return ``(short sha, dirty)`` for this checkout, or None when git is silent.

    Dirtiness is scoped to this tool's own directory. This repository is a
    monorepo, so an edit in a sibling tool says nothing about whether this
    generator is reconstructable, and counting it would mark every stamp dirty
    forever. An untracked file *is* counted, because a new unignored module can
    change what a generator produces.
    """
    raw_sha = _run_git(("rev-parse", f"--short={SHORT_SHA_LENGTH}", "HEAD"))
    if raw_sha is None:
        return None
    sha = raw_sha.strip()
    if not _SHORT_SHA.match(sha):
        return None

    status = _run_git(("status", "--porcelain", "--", "."))
    if status is None:
        # The commit is known but its cleanliness is not. Reporting a clean tree
        # here would be an assertion nothing checked, so report no git at all.
        return None
    return sha, bool(status.strip())


@functools.cache
def tree_version() -> str:
    """Return a version that identifies the exact tree this code came from.

    See "Resolution order" in the module docstring. Never raises, and never
    returns an empty string: a provenance stamp that fails is worse than a
    provenance stamp that says it does not know.

    **Resolved once per process, deliberately.** Two reasons. Every asset a single
    generator run writes then carries the same stamp, which is what a reader of the
    library expects from one run. And the git probe is two subprocesses, which a
    batch writing hundreds of symbols must not pay per symbol.

    A test that replaces one of the seams below calls ``tree_version.cache_clear()``
    first; the test suite does it for every test through an autouse fixture.

    >>> tree_version() != ""
    True
    """
    description = git_description()
    if description is not None:
        sha, dirty = description
        base = declared_version() or installed_version() or UNKNOWN_VERSION
        return f"{base}{COMMIT_PREFIX}{sha}{DIRTY_MARKER if dirty else ''}"
    return installed_version() or declared_version() or UNKNOWN_VERSION


def unidentified_tree_message(version: str) -> str:
    """Return why ``version`` must not stamp a library asset. For a command to print.

    Two causes, and the text names which one applies, because the two need different
    actions from the operator. A modified tree is committed. A stamp that names no
    commit means the git probe did not answer, and "Resolution order" in this module's
    docstring lists what makes it silent.

    One function, so the two commands that refuse a write state the same diagnosis:
    the Phase 3 migration and the four pinout generator commands. ADR-109.
    """
    if is_dirty(version):
        return (
            f"the tool tree is modified, so every stamp would read {version!r}. Such an "
            f"output is not reconstructable and must not enter a shared library. Commit the "
            f"tree, or pass --allow-dirty for a scratch copy."
        )
    return (
        f"the stamp {version!r} names no commit, so the tree this run came from is not "
        f"identified. Such an asset is not reconstructable and must not enter the "
        f"library. Run from a git checkout of this tool, or pass --allow-dirty for a "
        f"scratch copy."
    )


def identifies_the_tree(version: str) -> bool:
    """True when ``version`` names a commit and no modification. The positive guard.

    One call for the two conditions a write guard states together:
    :func:`names_a_commit` and not :func:`is_dirty`. ADR-109.

    >>> identifies_the_tree("0.1.0+g4f2a1c9")
    True
    >>> identifies_the_tree("0.1.0+g4f2a1c9.dirty")
    False
    >>> identifies_the_tree("0.1.0")
    False
    """
    return names_a_commit(version) and not is_dirty(version)


def is_installed_release(version: str) -> bool:
    """True when this code runs from an installed package and ``version`` is its release.

    The installed-wheel case. The package sits in an environment with no ``VERSION``
    file beside it, so there is no source tree and no git checkout to describe. The
    installed metadata is then the whole provenance there is, and the release number
    names the exact code: a wheel cannot be edited in place and keep its version.

    ADR-109 does not address this case. It was written for a git checkout of this
    tool. A source tree, which holds the ``VERSION`` file, never takes this path, so
    the ADR-109 refusal applies to it unchanged. Operator decision, 2026-10-22.
    """
    if VERSION_FILE.is_file():
        return False
    release = installed_version()
    return release is not None and version == release and not is_dirty(version)


def write_permitted(version: str) -> bool:
    """True when a generator command may write outputs stamped with ``version``.

    A git checkout must name a clean commit, :func:`identifies_the_tree`, ADR-109. An
    installed package may use its release number, :func:`is_installed_release`.
    """
    return identifies_the_tree(version) or is_installed_release(version)


__all__ = [
    "COMMIT_PREFIX",
    "DIRTY_MARKER",
    "DISTRIBUTION",
    "GIT_TIMEOUT_SECONDS",
    "PROJECT_ROOT",
    "SHORT_SHA_LENGTH",
    "UNKNOWN_VERSION",
    "VERSION_FILE",
    "declared_version",
    "git_description",
    "identifies_the_tree",
    "installed_version",
    "is_installed_release",
    "is_dirty",
    "names_a_commit",
    "tree_version",
    "unidentified_tree_message",
    "write_permitted",
]
