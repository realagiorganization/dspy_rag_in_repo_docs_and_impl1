# Hushwheel Quality Instrumentation

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Repository root: `/home/standard/dspy_rag_in_repo_docs_and_impl1`
- Working branch during verification: `codex/hushwheel-quality-instrumentation-20260318`

## Scope

This audit captures the hushwheel follow-up work that expands the fixture-local verification stack
with harder build flags, sanitizer reruns, profiling logs, richer persisted reports, and the
matching repository/CI surface updates.

The scope includes:

- new hushwheel `Makefile` targets for static analysis, complexity, coverage, reports, and a
  combined `quality` gate
- new hushwheel `Makefile` targets for `hardening`, `sanitizers`, and `profiling`
- ELF hardening audits that persist `file`, `size`, `readelf`, and `nm` output for the hardened
  hushwheel binary
- AddressSanitizer plus UndefinedBehaviorSanitizer reruns with persisted unit, integration, and
  BDD logs
- repeated CLI workload profiling with raw timing tables, Markdown summaries, and sample command
  logs
- report-aware integration and BDD entrypoints that accept `HUSHWHEEL_BIN`
- stronger CLI coverage assertions for spoke entries, no-match cases, missing arguments, and
  unknown commands
- a dedicated `.github/workflows/hushwheel-quality.yml` workflow that runs only when hushwheel
  surfaces change, now with explicit `binutils` installation for the binary-audit commands
- updated hushwheel README and testing docs plus repository workflow tests that pin the new CI
  surface

## Executed Commands

Executed successfully in this turn:

- `make -C tests/fixtures/hushwheel_lexiconarium hardening`
- `make -C tests/fixtures/hushwheel_lexiconarium sanitizers`
- `make -C tests/fixtures/hushwheel_lexiconarium profiling`
- `make -C tests/fixtures/hushwheel_lexiconarium quality`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make verify-surfaces`
- `uv run pytest tests/test_hushwheel_fixture.py tests/test_hushwheel_program_surface.py tests/test_project_surfaces.py`
- `uv run ruff format tests/test_hushwheel_program_surface.py tests/test_project_surfaces.py tests/fixtures/hushwheel_lexiconarium/tools/lint_hushwheel.py`
- `uv run ruff format tests/test_hushwheel_fixture.py`
- `make quality`
- `make hooks-install`

## Results

- `make -C tests/fixtures/hushwheel_lexiconarium hardening`: passed
  - hardened build flags now include `_FORTIFY_SOURCE=3`, stack protector, stack-clash
    protection, PIE, RELRO, `BIND_NOW`, non-executable stack, frame pointers, and
    `-Werror=format-security`
  - persisted ELF audit under `tests/fixtures/hushwheel_lexiconarium/build/reports/hardening/`
    reports:
    - `PIE`: `pass`
    - `RELRO segment`: `pass`
    - `BIND_NOW`: `pass`
    - `Non-executable stack`: `pass`
    - `Stack protector symbol`: `not-detected`
- `make -C tests/fixtures/hushwheel_lexiconarium sanitizers`: passed
  - AddressSanitizer plus UndefinedBehaviorSanitizer reran the unit, integration, and BDD
    surfaces without findings
  - persisted logs under `tests/fixtures/hushwheel_lexiconarium/build/reports/sanitizers/`
- `make -C tests/fixtures/hushwheel_lexiconarium profiling`: passed
  - persisted raw timing data at
    `tests/fixtures/hushwheel_lexiconarium/build/reports/profiling/runtime-profile.tsv`
  - profiled `25` iterations each of `about`, `stats`, canonical and generated `lookup`, canonical
    and generated `prefix`, and `category storm-index`
  - measured means from the current run:
    - `stats`: `10.137 ms`
    - `about`: `11.021 ms`
    - `prefix-canonical`: `11.065 ms`
    - `lookup-generated`: `12.657 ms`
    - `prefix-generated`: `12.914 ms`
    - `category-storm`: `13.314 ms`
    - `lookup-canonical`: `16.907 ms`
- `make -C tests/fixtures/hushwheel_lexiconarium quality`: passed
  - `cppcheck`: passed with XML plus GCC-style text reports under
    `tests/fixtures/hushwheel_lexiconarium/build/reports/cppcheck/`
  - `lizard`: passed with text, CSV, and checkstyle XML reports under
    `tests/fixtures/hushwheel_lexiconarium/build/reports/complexity/`
  - hardened binary audit, sanitizer logs, and runtime profile reports were added under:
    - `tests/fixtures/hushwheel_lexiconarium/build/reports/hardening/`
    - `tests/fixtures/hushwheel_lexiconarium/build/reports/sanitizers/`
    - `tests/fixtures/hushwheel_lexiconarium/build/reports/profiling/`
  - `gcovr`: passed with persisted text, Cobertura XML, HTML, JSON, and Markdown summary outputs
    under `tests/fixtures/hushwheel_lexiconarium/build/reports/coverage/`
  - executable coordinator coverage reached:
    - `line_percent: 100.0`
    - `function_percent: 100.0`
    - `branch_percent: 98.6`
- `uv run python -m compileall src tests`: passed
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`: passed, `13 passed`
- `uv run repo-rag smoke-test`: passed with:
  - `answer_contains_repository: true`
  - `mcp_candidate_count: 1`
  - `manifest_path: artifacts/azure/repo-rag-smoke.json`
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `make verify-surfaces`: passed with `issue_count: 0`
- changed-surface pytest slice: passed, `26 passed`
- `make quality`: passed, `121 passed` and repository coverage `87.56%`
  - the first repo-wide `make quality` rerun exposed two real blockers in hushwheel-adjacent
    Python surfaces:
    - `tests/test_hushwheel_fixture.py` needed repository-standard `ruff format`
    - `tests/fixtures/hushwheel_lexiconarium/tools/regenerate_hushwheel_fixture.py` carried a
      stale `F541` suppression
  - both were fixed in this turn and the subsequent `make quality` pass succeeded
- `make hooks-install`: passed and refreshed managed `pre-commit` plus `pre-push` hooks
- post-push GitHub Actions evidence:
  - run `23238384378` (`Hushwheel Quality`, head `108754e5d1a05e76d15e94e7efa0d1ee15925daa`)
    failed in `47s`
    - fixture quality suite, report snapshot, quality-summary publish, and artifact upload passed
    - repository surface step failed because the local hushwheel generator/corpus sync in
      `docs/catalog.md` plus the eight `src/hushwheel_spoke_*.c` files had not been included in the
      first scoped commit
  - follow-up run `23238475251` (`Hushwheel Quality`, head
    `bfe74cb96bcfb79f8076eabcaaac53af1c16ecc3`) succeeded in `44s`
    - every workflow step passed, including artifact upload
    - the workflow still emits the existing Node.js 20 deprecation annotation for
      `actions/checkout@v4`, `actions/upload-artifact@v4`, and `astral-sh/setup-uv@v6`

## Current Verification Status

Configured and exercised in this turn:

- hushwheel fixture lint, unit, integration, BDD, static analysis, complexity, and coverage gates
- hushwheel hardened-build verification with persisted binary-analysis artifacts
- hushwheel sanitizer reruns with persisted command logs
- hushwheel runtime profiling with raw timing tables and sample CLI logs
- persisted hushwheel report generation for local and CI artifact upload
- hushwheel workflow parsing and path-filter coverage in repository tests
- compile checks
- repository surface verification
- focused repository pytest verification for hushwheel fixture, hushwheel program surfaces, and
  project workflow surfaces
- full repository quality gate with lint, type checks, tests, and coverage
- Rust wrapper build

Not exercised in this turn:

- live Azure endpoint probes against remote services
- a clean-tree file-summary regeneration, because no new tracked files were added during this pass

## Notes

- The hushwheel coverage report intentionally excludes `src/hushwheel_spoke_*.c` and
  `src/hushwheel_spokes.c`, because those generated tables are data-heavy catalog surfaces rather
  than executable control-flow logic.
- The repository-wide `make quality` run now passes, but getting there required one formatted test
  refresh and removal of one stale hushwheel-generator lint suppression that the tighter pass
  surfaced.
- The first post-push hushwheel workflow run failed for a repository-surface consistency reason:
  the generated hushwheel catalog and spoke files were already updated in the local worktree, but
  they were omitted from the initial scoped commit. The follow-up commit synced those generated
  surfaces and the rerun passed.
- The fixture-local report tree is intentionally regenerated after the repository pytest slice,
  because the existing packaging/docs tests clean the hushwheel build directory as part of their
  normal fixture contract.
- The repository worktree contained unrelated pending changes before this task continued. Those
  changes were not reverted during this audit.
