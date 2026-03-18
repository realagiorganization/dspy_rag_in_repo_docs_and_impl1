# Session Consolidation Master CI Repair

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Repository root: `/tmp/repo-rag-consolidate-final`
- Repaired head under test: `master` consolidation for
  `rebase all work of this session on top of current top state integrate into commmit and push consolidate everything into master`

## Scope

This audit captures the CI repair made after the first consolidated `master` push.

The repair scope is intentionally narrow:

- make the hushwheel fixture documentation target succeed on runners without `doxygen`
- preserve the committed `docs/hushwheel-reference.pdf` as the fallback packaging surface
- verify the affected hushwheel project-harness tests locally before repushing `master`

## Root Cause

The first consolidated `master` push failed in GitHub Actions `CI` run `23230886898`.

The failing test surface was [tests/test_hushwheel_program_surface.py](../../tests/test_hushwheel_program_surface.py):

- `test_hushwheel_fixture_docs_target_builds_pdf`
- `test_hushwheel_fixture_packaging_targets_stage_install_and_dist`

The shared failure path was
[tests/fixtures/hushwheel_lexiconarium/Makefile](../../tests/fixtures/hushwheel_lexiconarium/Makefile),
where `$(DOC_PDF)` unconditionally invoked `doxygen`. The GitHub runner for the `coverage` job
does not provide `doxygen`, so `make docs` exited with status `127` before packaging could reuse
the committed reference PDF.

## Fix

The `$(DOC_PDF)` recipe now:

- creates the build parent directory before invoking `doxygen`
- runs the LaTeX steps in subshells so repeated `cd` commands do not accumulate inside the
  recipe's single-shell `if` block
- regenerates the PDF with `doxygen` plus LuaLaTeX when `doxygen` is available
- reuses the committed `docs/hushwheel-reference.pdf` when `doxygen` is unavailable
- still fails loudly when both `doxygen` and the committed PDF are missing

This keeps the local full-docs workflow intact while allowing the committed fixture artifact to
serve as the portable packaging surface in CI.

## Executed Commands

Executed successfully in this repair turn:

- `make -C tests/fixtures/hushwheel_lexiconarium clean`
- `make -C tests/fixtures/hushwheel_lexiconarium docs`
- `make -C tests/fixtures/hushwheel_lexiconarium clean`
- `make -B -C tests/fixtures/hushwheel_lexiconarium docs DOXYGEN=missing-doxygen`
- `DOXYGEN=missing-doxygen make -B -C tests/fixtures/hushwheel_lexiconarium install DESTDIR=<tmp> PREFIX=/usr`
- `DOXYGEN=missing-doxygen make -C tests/fixtures/hushwheel_lexiconarium uninstall DESTDIR=<tmp> PREFIX=/usr`
- `uv run pytest tests/test_hushwheel_program_surface.py`

## Results

- normal `docs` build: passed with the local `doxygen` toolchain
- fallback `docs` build: passed and reused the committed PDF when `DOXYGEN=missing-doxygen`
- fallback `install` plus `uninstall`: passed and staged the committed PDF into a temporary
  `DESTDIR` without a live `doxygen`
- hushwheel program-surface pytest slice: passed, `4 passed`

## Notes

- The `Publication PDF` workflow for the original consolidated head `ed340b3` had already passed as
  run `23230886879`; only the `CI` workflow needed repair.
- This note supersedes the earlier consolidation audit as the health baseline for the repaired
  `master` head.
