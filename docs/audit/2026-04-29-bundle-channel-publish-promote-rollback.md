# 2026-04-29 Bundle Channel Publish Promote Rollback

## Summary

This audit records the next worker-runtime hardening step after bundle, overlay, and trace
contracts: the repository now has explicit published-bundle and channel lifecycle semantics.

- Compiled DSPy bundles can now be published into `artifacts/dspy/published/`.
- The CLI can promote those published bundles into persisted `stable` and `canary` channels.
- The CLI can roll those channels back without deleting published bundle records.
- `bundle-inspect` can now resolve either the latest raw bundle manifest or the current promoted
  channel state, which gives future workers a real startup target instead of a best-effort
  “latest run” guess.

## Code Changes

- Added published-bundle and bundle-channel helpers:
  - `src/repo_rag_lab/runtime_artifacts.py`
- Added user-facing utility surfaces for publish, promote, rollback, and channel-aware inspect:
  - `src/repo_rag_lab/utilities.py`
  - `src/repo_rag_lab/cli.py`
  - `Makefile`
- Added user-visible tests for the new lifecycle:
  - `tests/test_utilities.py`
  - `tests/test_cli_and_dspy.py`
- Updated authored runtime and operator docs:
  - `README.md`
  - `AGENTS.md`
  - `docs/architecture/package-api.md`
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
  - `docs/planning/repo-hardening-plan.md`
  - `docs/planning/dataset-integration-plan.md`

## Verification

Configured verification surfaces in this repository still include:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make quality`
- `make files-sync`
- `make exploratorium-sync`
- `make paper-build`
- `make verify-surfaces`

Commands executed locally on `2026-04-29` for this turn:

- `uv run ruff format src/repo_rag_lab/runtime_artifacts.py src/repo_rag_lab/utilities.py src/repo_rag_lab/cli.py tests/test_utilities.py tests/test_cli_and_dspy.py`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_cli_and_dspy.py`
- `uv run basedpyright src/repo_rag_lab/runtime_artifacts.py src/repo_rag_lab/utilities.py src/repo_rag_lab/cli.py`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make files-sync`
- `make exploratorium-sync`
- `make paper-build`
- `make verify-surfaces`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`
- `make quality`

Observed results:

- `pytest tests/test_utilities.py tests/test_cli_and_dspy.py`: passed, `44 passed`
- `basedpyright ...`: passed, `0 errors, 0 warnings, 0 notes`
- `pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`: passed, `24 passed`
- `repo-rag smoke-test`: passed with `command_status: "success"` and `mcp_candidate_count: 1`
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `make files-sync`: passed
- `make exploratorium-sync`: passed
- `make paper-build`: passed
- `make verify-surfaces`: passed with `issue_count: 0`
- `pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`:
  passed, `28 passed`
- `make quality`: passed with:
  - `182 passed`
  - `3 skipped`
  - total coverage `85.22%`

## Live CLI Scenario

The new lifecycle was also exercised outside pytest against a temporary git repository root:

- temporary root: `/tmp/tmp.S2wLb8pl50`
- two bundle manifests were created there manually:
  - `alpha-run`
  - `beta-run`
- the following CLI flow completed successfully:
  - `uv run repo-rag bundle-publish --root /tmp/tmp.S2wLb8pl50 --run-name alpha-run --output json`
  - `uv run repo-rag bundle-promote --root /tmp/tmp.S2wLb8pl50 --channel stable --run-name alpha-run --output json`
  - `uv run repo-rag bundle-publish --root /tmp/tmp.S2wLb8pl50 --run-name beta-run --output json`
  - `uv run repo-rag bundle-promote --root /tmp/tmp.S2wLb8pl50 --channel stable --run-name beta-run --output json`
  - `uv run repo-rag bundle-inspect --root /tmp/tmp.S2wLb8pl50 --channel stable --output json`
  - `uv run repo-rag bundle-rollback --root /tmp/tmp.S2wLb8pl50 --channel stable --output json`
  - `uv run repo-rag bundle-inspect --root /tmp/tmp.S2wLb8pl50 --channel stable --output json`

The observed state transitions were:

- `bundle-publish` created `artifacts/dspy/published/alpha-run.json` and
  `artifacts/dspy/published/beta-run.json`
- `bundle-promote --channel stable` first pointed the channel at `alpha-run`, then at `beta-run`
- `bundle-inspect --channel stable` reported the promoted channel state instead of a raw latest-run
  guess
- `bundle-rollback --channel stable` moved the channel back from `beta-run` to `alpha-run`
- the stable channel history recorded both promotions plus the rollback event

## Status Impact

- Phase 5 of `docs/planning/repo-hardening-plan.md` is now partially closed:
  - trace export/import: done
  - bundle publish/promote/rollback semantics: done
- The repository now exposes the worker-start surfaces needed before `../dataset` gets its own
  backend:
  - `bundle-inspect --channel stable`
  - `bundle-publish`
  - `bundle-promote`
  - `bundle-rollback`
- The next remaining integration-heavy steps are:
  - document the boundary between DSPy program optimization and future model-level tuning
  - add the actual `repo_rag_cli` backend inside `../dataset`
  - wire bundle fetch/upload behavior into the downstream worker lifecycle
