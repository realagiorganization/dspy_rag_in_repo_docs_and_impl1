# 2026-04-29 Retrieval Rerank And Relative Root Normalization

## Summary

This audit records the retrieval-generalization pass that completed the next open item in the
repo-hardening plan: a stronger retrieval option beyond the lexical-only baseline. The repository
now supports a profile-selected `idf-rerank` second stage, keeps retrieval scoring stable across
arbitrary repo roots and nested fixture repos, and normalizes corpus paths relative to the
selected root so worker-style temporary clones do not inherit penalties from a parent monorepo
path like `tests/`.

## Code Changes

- Added optional `idf-rerank` retrieval mode and profile plumbing across:
  - `src/repo_rag_lab/retrieval.py`
  - `src/repo_rag_lab/retrieval_profile.py`
  - `config/retrieval-profile.json`
  - `src/repo_rag_lab/workflow.py`
  - `src/repo_rag_lab/dspy_workflow.py`
  - `src/repo_rag_lab/dspy_training.py`
  - `src/repo_rag_lab/benchmarks.py`
  - `src/repo_rag_lab/utilities.py`
  - `src/repo_rag_lab/cli.py`
- Added intent-gated penalties so `AGENTS.md`, `docs/audit/*`, `tests/*`, and
  `samples/training/*` do not dominate unrelated repository questions.
- Normalized loaded corpus paths relative to the selected repository root in
  `src/repo_rag_lab/corpus.py`, which fixed retrieval regressions for:
  - nested temporary repo roots in benchmark scaffolds
  - the large `tests/fixtures/hushwheel_lexiconarium` fixture repo
  - lookup-first narrowing against arbitrary git roots
- Updated tests and mocks to reflect the new retrieval-mode parameter and the relative source-path
  contract.

## Verification

Commands run locally on `2026-04-29`:

- `uv run python -m compileall src tests`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `uv run pytest tests/test_retrieval.py tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run pytest tests/test_benchmarks_and_notebook_scaffolding.py tests/test_dspy_training.py tests/test_hushwheel_fixture.py tests/test_lookup_first.py tests/test_workflow_live.py`
- `uv run pytest tests/test_rust_lookup.py`
- `uv run repo-rag retrieval-eval --output json --top-k-sweep 1,4`
- `uv run repo-rag smoke-test`
- `make quality`

Observed results:

- `cargo build` passed.
- `retrieval-eval --output json --top-k-sweep 1,4` passed with:
  - `retrieval_mode: "idf-rerank"`
  - `default_summary.pass_rate: 1.0`
  - `default_summary.average_source_recall: 1.0`
- `smoke-test` passed with `command_status: "success"` and one generated Azure manifest path.
- `make quality` passed with:
  - `168 passed`
  - `3 skipped`
  - total coverage `85.38%`

## Status Impact

- The open retrieval-generalization item in `docs/planning/repo-hardening-plan.md` is now closed.
- The runtime contract used for future `dataset` integration now includes:
  - arbitrary `--root` support
  - optional `--retrieval-mode lexical|idf-rerank`
  - repo-relative source paths for retrieved evidence
- Remaining hardening work is now concentrated on:
  - bundle and overlay artifact formats
  - trace capture
  - async optimization and promotion surfaces
