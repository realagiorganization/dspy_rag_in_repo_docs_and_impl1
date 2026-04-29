# 2026-04-29 Trainer Service Loop

## Summary

This audit records the next step after `trainer-cycle`: the repository now exposes a long-lived
`trainer-service` surface that repeatedly runs the same queue-drain, retrieval-gate, and optional
publish/promote workflow while persisting trainer-side state and history artifacts.

- `repo-rag trainer-service` now provides a concrete asynchronous trainer/publisher process that
  lives outside the worker hot path.
- The service reuses the existing `trainer-cycle` contract instead of inventing a second
  orchestration path.
- Trainer-side queue drain now also emits first-pass ingestion summaries for acceptance status,
  execution status, retrieval mode, bundle version, and empty source/context cases from the
  imported trace records.
- Imported trainer-side traces now also feed a cumulative
  `artifacts/trainer/training-candidates.yaml` file plus a JSON summary, so accepted/candidate
  worker answers can become explicit DSPy review inputs instead of staying as raw trace files.
- Each bounded or long-lived run now writes:
  - `artifacts/trainer/service-state.json`
  - `artifacts/trainer/history/*.json`
- The `dataset` integration story now has an actual trainer-side poller, not only queue staging
  and one-shot drain utilities.

## Code And Documentation Changes

Changes landed in this repository:

- added trainer-service artifact constants in:
  - `src/repo_rag_lab/runtime_artifacts.py`
- added long-lived service orchestration plus state/history writing, and first-pass ingestion
  summarization in:
  - `src/repo_rag_lab/utilities.py`
- added trainer-side trace-to-training-candidate materialization in:
  - `src/repo_rag_lab/training_samples.py`
- exposed the new CLI command in:
  - `src/repo_rag_lab/cli.py`
- exposed the new Make target and runtime variables in:
  - `Makefile`
- kept the service in the verified surface contract via:
  - `src/repo_rag_lab/verification.py`
- added coverage for service state/history and CLI wiring in:
- added coverage for service state/history, trainer-candidate materialization, and CLI wiring in:
  - `tests/test_utilities.py`
  - `tests/test_cli_and_dspy.py`
- updated operator, API, narrative, and planning docs in:
  - `README.md`
  - `docs/architecture/package-api.md`
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
  - `docs/planning/repo-hardening-plan.md`
  - `docs/planning/dataset-integration-plan.md`

No `../dataset` runtime code changed in this turn. The new capability is trainer-side and lives in
the repo-RAG repository itself.

## Verification

Configured verification surfaces in this repository still include:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make files-sync`
- `make exploratorium-sync`
- `make verify-surfaces`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

Commands executed locally on `2026-04-29` for this turn:

- `uv run python -m compileall src tests`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `uv run pytest tests/test_utilities.py tests/test_cli_and_dspy.py`
- `uv run repo-rag trainer-candidates --root . --output json`
- `uv run repo-rag trainer-service --root . --queue-name dataset --max-cycles 1 --poll-interval-seconds 0 --output json`
- `uv run repo-rag smoke-test`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- after doc/audit updates:
  - `make files-sync`
  - `make exploratorium-sync`
  - `make verify-surfaces`
  - `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

Observed results:

- `uv run python -m compileall src tests`: passed
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `uv run pytest tests/test_utilities.py tests/test_cli_and_dspy.py`: passed, `55 passed`
- `uv run repo-rag trainer-candidates --root . --output json`:
  passed with `command_status: "success"` and generated
  `artifacts/trainer/training-candidates.yaml` plus
  `artifacts/trainer/training-candidates-summary.json`
- `uv run repo-rag trainer-service --root . --queue-name dataset --max-cycles 1 --poll-interval-seconds 0 --output json`:
  passed with `command_status: "success"`, `service_status: "success"`, `stop_reason: "max-cycles"`,
  and generated trainer artifacts under `artifacts/trainer/`
- `uv run repo-rag smoke-test`: passed with `command_status: "success"` and
  `answer_contains_repository: true`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`: passed, `30 passed`
- `make files-sync`: passed
- `make exploratorium-sync`: passed
- `make verify-surfaces`: passed with `issue_count: 0`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`:
  passed, `28 passed`

Verification categories not executed in this turn:

- no `make quality` or `make coverage`
- no live Azure/OpenAI integration suite
- no MCP runtime validation
- no `../dataset` worker or AKS deployment run

## Status Impact

- Phase 5 of `docs/planning/repo-hardening-plan.md` is further closed:
  - trace export/import: done
  - queued trace handoff: done
  - trainer-cycle: done
  - trainer-service loop: done
  - trainer-side candidate materialization: done
  - boundary docs for model-level tuning: still pending
- Phase 4 of `docs/planning/dataset-integration-plan.md` is further closed:
  - worker queue handoff: done
  - single-pass trainer cycle: done
  - asynchronous trainer/publisher service: done
  - first-pass trace/outcome ingestion summaries: done
  - trainer-side candidate materialization from worker traces: done
  - bundle recompilation depth and promotion policy hardening: still pending
- The next practical work items are now:
  - use the cumulative trainer candidate file as an input to real bundle recompilation
  - harden promotion policy beyond the current retrieval gate
  - package the trainer service for AKS or another long-lived deployment target
