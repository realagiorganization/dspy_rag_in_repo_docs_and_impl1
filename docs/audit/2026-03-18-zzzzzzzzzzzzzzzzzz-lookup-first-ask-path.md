# Lookup First Ask Path

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Repository root: `/home/standard/repo-sqlite-cli-final-FZKQlB`
- Local branch: `lookup-first-ask-20260318`
- Observed `origin/master`: `a86dc7c`

## Scope

This audit covers the change that makes the default repository question-answering path use the
repository-local Rust SQLite lookup before the broader Python retrieval and DSPy synthesis paths.

The turn also aligns the agent-facing guidance with that behavior:

- `uv run repo-rag ask --question "..."` and `make ask QUESTION="..."` now narrow on Rust lookup
  hits first, then fall back to broader retrieval when the direct hits are weak
- `uv run repo-rag ask --question "..." --use-dspy` and `make ask-dspy QUESTION="..."` now reuse
  the same narrowing pass before DSPy synthesis
- repository agent guidance and generated file-summary surfaces now describe the lookup-first
  contract instead of treating Rust lookup as only a manual side path

## Executed Commands

Executed successfully in this turn:

- `uv run python -m compileall src tests`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `uv run pytest tests/test_lookup_first.py tests/test_cli_and_dspy.py tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_hushwheel_fixture.py`
- `uv run repo-rag retrieval-eval --top-k 4 --top-k-sweep 1,4 --minimum-pass-rate 1.0 --minimum-source-recall 1.0`
- `uv run repo-rag smoke-test`
- `make quality`
- `make hooks-install`
- `make rust-lookup QUERY='dspy training'`
- `uv run pytest tests/test_lookup_first.py tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_project_surfaces.py`
- `make files-sync`
- `make verify-surfaces`

## Results

- `uv run python -m compileall src tests`: passed
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `uv run pytest tests/test_lookup_first.py tests/test_cli_and_dspy.py tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_hushwheel_fixture.py`:
  passed, `35` tests
- `uv run repo-rag retrieval-eval --top-k 4 --top-k-sweep 1,4 --minimum-pass-rate 1.0 --minimum-source-recall 1.0`:
  passed with `pass_rate: 1.0`, `average_source_recall: 1.0`, and `threshold_failures: []`
- `uv run repo-rag smoke-test`: passed with:
  - `answer_contains_repository: true`
  - `mcp_candidate_count: 1`
  - `manifest_path: artifacts/azure/repo-rag-smoke.json`
- `make quality`: passed with `134` tests and `87.36%` total coverage
- `make hooks-install`: passed and refreshed the managed `pre-commit` plus `pre-push` hooks
- `make rust-lookup QUERY='dspy training'`: passed and returned ranked SQLite hits, led by
  `src/repo_rag_lab/notebook_scaffolding.py`, `README.DSPY.MD`, and
  `src/repo_rag_lab/training_samples.py`
- `uv run pytest tests/test_lookup_first.py tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_project_surfaces.py`:
  passed, `36` tests
- `make files-sync`: passed and refreshed `FILES.md`, `FILES.csv`, and `AGENTS.md.d/FILES.md`
- `make verify-surfaces`: passed with `issue_count: 0`

## Current Verification Status

Configured and exercised in this turn:

- Python compile checks
- Rust wrapper build
- lookup-first retrieval coverage in targeted pytest suites
- repository utility, BDD, project-surface, and fixture coverage in targeted pytest suites
- smoke coverage through the default `repo-rag ask` path
- retrieval regression gating
- repo-wide lint, notebook lint, type checks, repository-surface verification, retrieval quality,
  complexity reporting, pytest, and coverage through `make quality`
- hook installation and tracked-file inventory regeneration
- direct Rust SQLite lookup execution through the repo-native `make rust-lookup` surface

Not exercised in this turn:

- live Azure endpoint probes
- standalone `make coverage` beyond the coverage phase already included in `make quality`
- full notebook batch execution via `make notebook-report`
- post-push GitHub Actions evidence for this branch head

Verification categories not found as standalone repository checks:

- UI test suite
- browser or end-to-end integration suite

## Notes

- The retrieval gate initially regressed because the new `rust_lookup.py` module started surfacing
  for the benchmark question about what the repository researches. The turn corrected ranking with a
  targeted source adjustment in `src/repo_rag_lab/retrieval.py` rather than weakening thresholds.
- The Rust lookup integration is intentionally limited to the repository root so fixture repos can
  continue using the existing full-corpus path without accidental cross-repo indexing.
