# Changelog

All notable changes to this project are documented in this file. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- The generators no longer need a library rules package. A *route* now finds the
  templates and writes the outputs, in `eedesignsymbols.writing`. The default route,
  the plain route, reads `<folder>/<name>.kicad_sym` and writes
  `<out>/<name>.kicad_sym` with the KiCad fields only, through the `kicad-file-io`
  writer. A rerun that would write the same bytes writes nothing.
- The package ships its 22 template drawings in `src/eedesignsymbols/templates/`. Each file
  is named for its template with no version number. The plain route reads them by
  default. Ten of them are adapted from KiCad stock symbols and carry CC BY-SA 4.0.
  `templates/NOTICE` names them.
- `--dir` names the output folder. The new `--templates` option names another template
  folder.
- The output name, the `Value` field, and the unit names now change together in the
  generator, through `rename_symbol`. Before, the library write step renamed the units.
- The tool name, the name markers, the format version check, and the two stamp checks
  are now this package's own code.
- The library dependency is removed from `pyproject.toml`.
- The generators read and write through `eedesigncore` 0.38.0, the published name
  of `kicad-file-io`, in place of `kicad-file-io` 0.11.2. The plain outputs are
  byte-identical to the 0.11.2 outputs, after the tool stamp is masked.
- A generator command run from an installed package accepts the installed release
  number as its stamp. In a source tree the command still needs a clean git commit,
  as before.

### Unchanged

- The in-house library route, a separate module that the public copy does not carry,
  writes exactly what the generators wrote before. All 60 outputs are byte-identical
  after the version number and the tool stamp are masked.

## [0.1.0] - 2026-08-14

First release of `eedesignsymbols`. This is a first release with known,
accepted gaps, recorded below. It is not presented as clean.

### Added

- Library asset rules, in a rules package that this tool imported. A version suffix in four
  places, lock and lifecycle governance, required `_SYM.` fields, required
  keywords, the part-lifecycle warning flag, and generator provenance in the
  KiCad header tokens.
- `sync`, the compare-then-decide write path (ADR-001). A rerun always
  lands. Matching content writes nothing. An unlocked version is
  overwritten in place. A locked version is superseded, and the old version
  is marked deprecated.
- Pin-order generators for three families: MOSFET (gate, source, drain),
  BJT (base, collector, emitter), and IGBT (gate, collector, emitter). Each
  generator is configuration over a shared `pinout.Family` (ADR-005,
  ADR-006).
- An adoption helper for hand-maintained symbols. `conventions.apply_to_file`
  mints a version suffix and renames the file, so a hand-drawn symbol
  carries the same version identity as a generated one (ADR-009).
- The `_SYM.REVIEW` field. It tracks an evolving review stage (`draft`,
  `reviewed`, `released`) apart from lock and lifecycle, so a symbol moves
  through review without a lock or lifecycle change.
- `bbox.py`, a symbol bounding-box measurement helper.
- `fields.py` and `keywords.py`, shared helpers for KiCad symbol fields and
  the `ki_keywords` convention.

### Known limitations

- The three generators are not idempotent against the live in-house transistor
  library today. A dry run against `Diodes_Transistors_FETs_SCRs` reports
  35 of 42 pin-order symbols as `updated`, not `unchanged`. Traced cause:
  KiCad sorts pins by number on save. This tool's writer preserves template
  order instead. This is a library-level gap, logged as `UF-002` (`DRAFT`),
  not a defect local to this project. Confirm the fix has landed upstream,
  or move the `kicad-file-io` pin, before a generator writes for real
  against the production library.
- A generator claims every template it finds in the target directory, not a
  declared list (ADR-010, accepted, not yet implemented). Two JFET templates
  already produced 12 unplanned symbols this way. Non-destructive, and
  tracked for a future iteration.
- The documented install command uses `--extra-index-url`. This makes the
  GitLab registry an additional index, not the authoritative one, and
  exposes the install to dependency confusion from a same-named,
  same-version package on public PyPI. Fix before the install command runs
  unattended in CI.
- `.claude/settings.json` pre-approves `Bash(git:*)`. This is wider than the
  documented approval boundary for `git push`, `git tag`, and any command
  against the read-only `../kicad-file-io` checkout.
- Five further low-severity findings are recorded in
  `context/security-findings-iter-1.md`. None blocks this release.

### QA

- 306 of 306 tests pass. `ruff check`, `ruff format --check`, and
  `mypy --strict` all report clean. Coverage: 97 percent. Overall verdict:
  PASS_WITH_NOTES. Full detail: `context/qa-report-iter-1.md`.

### Security

- 0 critical findings, 0 high findings, 3 medium findings, 5 low findings.
  No finding blocks this release. Overall verdict: FINDINGS_PRESENT. Full
  detail: `context/security-findings-iter-1.md`.

### Upstream

Three items raised against `kicad-file-io` v0.9.0, all status `DRAFT` in
`context/upstream-feedback.md`.

- `UF-001`: `kicad-file-io` ships no `py.typed` marker. A consumer cannot
  type-check against it under `mypy --strict`.
- `UF-002`: the `kicad-file-io` writer preserves stored pin order. KiCad sorts
  pins by number on save instead. This is the root cause of the
  idempotence gap listed above.
- `UF-003`: `extract_symbol` returns unit index 0 for every unit of a
  schematic-extracted symbol, when the parent name is long enough to make
  the index recovery fail silently.

### Note on `generator_version`

This tool stamps `generator_version` into every generated symbol, and this
release bumps that value from none to `0.1.0`. Provenance is excluded from
the content comparison (ADR-002), so the version bump on its own does not
rewrite the in-house library.

[Unreleased]: https://github.com/eedesignpro/eedesignsymbols/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/eedesignpro/eedesignsymbols/releases/tag/v0.1.0
