# 2026-04-29 Bundle Overlay And Runtime Trace Contract

## Summary

This audit records the next hardening step after retrieval generalization: the repository now has
an explicit first-pass artifact model for worker-side reuse.

- DSPy runs now materialize a versioned `bundle.json` beside `program.json` and `metadata.json`.
- The CLI exposes `bundle-inspect` so downstream workers can inspect bundle version, provenance,
  benchmark status, and related artifact paths without parsing free-form notes.
- The CLI exposes `overlay-init` so workers can create a repo-local `artifacts/overlays/<name>/`
  manifest that records retrieval-mode, lookup-index, and trace-directory state.
- Ask-family JSON output now includes a stable `trace` payload and reserved `bundle_version` /
  `overlay_path` fields for later asynchronous optimization and `dataset` handoff.

## Code Changes

- Added the new artifact-contract module:
  - `src/repo_rag_lab/runtime_artifacts.py`
- Extended DSPy training and artifact inventory to write and expose bundle manifests:
  - `src/repo_rag_lab/dspy_training.py`
- Added bundle and overlay utility surfaces:
  - `src/repo_rag_lab/utilities.py`
  - `src/repo_rag_lab/cli.py`
  - `Makefile`
- Threaded stable runtime traces into ask-family JSON output:
  - `src/repo_rag_lab/cli.py`
- Strengthened broad narrative retrieval so `README.md` remains the lead source for the canonical
  repository-research benchmark question after the corpus and artifact surfaces expanded:
  - `src/repo_rag_lab/retrieval.py`
- Updated tests, plans, authored docs, and agent/operator guidance to reflect the new worker-side
  contract.

## Verification

Commands run locally on `2026-04-29`:

- `uv run ruff format src tests`
- `uv run python -m compileall src tests`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `uv run pytest tests/test_dspy_training.py tests/test_utilities.py tests/test_cli_and_dspy.py`
- `uv run pytest tests/test_retrieval.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag dspy-artifacts --output json`
- `uv run repo-rag bundle-inspect --output json`
- `uv run repo-rag overlay-init --output json --overlay-name worker-default --bundle-version latest-stable`
- `uv run repo-rag ask --question "What does this repository research?" --output json`
- `make quality`
- `make files-sync`
- `make exploratorium-sync`
- `make verify-surfaces`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

Observed results:

- `pytest tests/test_dspy_training.py tests/test_utilities.py tests/test_cli_and_dspy.py`: passed,
  `54 passed`
- `pytest tests/test_retrieval.py tests/test_repository_rag_bdd.py`: passed, `14 passed`
- `repo-rag dspy-artifacts --output json`: passed and now reports:
  - `latest_bundle_path`
  - `latest_bundle_version`
- `repo-rag bundle-inspect --output json`: passed and returns a success envelope with
  `bundle_found: false` plus a warning when no compiled bundles exist yet
- `repo-rag overlay-init --output json ...`: passed and wrote a worker-local overlay manifest with
  `retrieval_mode: "idf-rerank"`, `lookup_index_path`, `trace_dir`, and
  `worker_adaptation_scope.model_weights: false`
- `repo-rag ask --output json`: passed and now includes:
  - `bundle_version`
  - `overlay_path`
  - `trace.trace_kind: "repo-rag-runtime"`
- `make quality`: passed with:
  - `172 passed`
  - `3 skipped`
  - total coverage `85.15%`
- `make files-sync`: passed
- `make exploratorium-sync`: passed
- `make verify-surfaces`: passed
- `pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`:
  passed, `28 passed`

## Status Impact

- Phase 4 of `docs/planning/repo-hardening-plan.md` is now closed:
  - versioned global bundle format
  - local overlay format
  - stable runtime trace schema
  - artifact inspection commands
- The repository now exposes the worker-side surfaces that `../dataset` will need before any
  backend adapter exists:
  - `ask ... --output json`
  - `bundle-inspect --output json`
  - `overlay-init --output json`
- Remaining integration work is now concentrated on:
  - trace export/import for asynchronous optimization
  - bundle promotion semantics such as `stable` / `canary`
  - the actual `repo_rag_cli` backend inside `../dataset`
