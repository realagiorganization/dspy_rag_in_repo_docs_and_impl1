# Hushwheel PDF Side-Effect Fix

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Repository root: `/home/standard/dspy_rag_in_repo_docs_and_impl1`
- Working branch during verification: `detached HEAD from origin/master`

## Scope

This audit records the follow-up fix that makes the hushwheel program-surface tests restore the
committed fixture PDF after docs and packaging runs. The repository already contains the Rust
SQLite lookup path and the later DSPy/Azure proof surfaces; this note captures the verification
needed to keep the pre-push coverage hook side-effect free on top of that newer remote baseline.

## Executed Commands

Run after implementation in this turn:

- `make hooks-install`
- `make files-sync`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_project_surfaces.py tests/test_cli_and_dspy.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `make rust-quality`
- `uv run pytest tests/test_hushwheel_program_surface.py`
- `make coverage`
- `make verify-surfaces`

## Results

- `make hooks-install`: passed and refreshed the managed `pre-commit` plus `pre-push` hooks
- `make files-sync`: passed and refreshed `FILES.md` plus `FILES.csv` for `214` tracked files
- `uv run python -m compileall src tests`: passed
- `uv run pytest tests/test_utilities.py tests/test_project_surfaces.py tests/test_cli_and_dspy.py tests/test_repository_rag_bdd.py`:
  passed, `39 passed in 14.93s`
- `uv run repo-rag smoke-test`: passed with `answer_contains_repository: true`,
  `mcp_candidate_count: 1`, and `manifest_path: artifacts/azure/repo-rag-smoke.json`
- `make rust-quality`: passed with `cargo fmt`, `cargo clippy`, `cargo build`, the native `index`
  and `lookup` smoke runs, and the delegated `ask` smoke run
- `uv run pytest tests/test_hushwheel_program_surface.py`: passed, `4 passed in 3.04s`
- `make coverage`: passed with `120 passed in 112.73s` and total coverage `87.98%`
- `cargo run --manifest-path rust-cli/Cargo.toml -- index`: passed with
  `indexed=204 skipped_binary=3 skipped_large=2`
- `cargo run --manifest-path rust-cli/Cargo.toml -- lookup "dspy training"`: passed and returned
  ranked hits led by:
  - `src/repo_rag_lab/notebook_scaffolding.py`
  - `README.DSPY.MD`
  - `src/repo_rag_lab/training_samples.py`
- `make verify-surfaces`: passed with `issue_count: 0`
- The Rust wrapper keeps delegating non-native commands to `uv run repo-rag`.
- The native `index` subcommand writes the ignored SQLite index to
  `artifacts/sqlite/repo-file-index.sqlite3`.
- The native `lookup` subcommand returns ranked file-path plus snippet hits from tracked UTF-8
  text files.
- `tests/test_hushwheel_program_surface.py` now restores the committed
  `tests/fixtures/hushwheel_lexiconarium/docs/hushwheel-reference.pdf` after docs/dist runs, so
  the pre-push coverage hook no longer dirties the working tree.
- `Makefile`, `README.md`, `README.AGENTS.md`, `AGENTS.md`, `AGENTS.md.d/RUST_LOOKUP.md`, and the
  repo-local `rust-sqlite-lookup` skill now agree on the “lookup first, DSPy second” workflow.

## Verification Status

Configured in the repository:

- Python compile checks
- targeted pytest suites
- repository surface verification
- smoke test
- Rust formatting, clippy, build, index, lookup, and wrapper ask smoke runs

Not configured in this audit:

- dedicated Rust unit/integration test execution in CI beyond `cargo fmt`, `cargo clippy`, and the
  smoke runs above
- live Azure endpoint probes
- notebook batch execution
