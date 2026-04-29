# 2026-04-29 Trainer Bundle Benchmark Gates

## Summary

This audit records the next trainer-side hardening step after `trainer-recompile`: automatic
publish/promotion is no longer allowed to advance a freshly recompiled DSPy bundle on retrieval
signal alone. The background trainer path now enforces an explicit DSPy benchmark gate before
publish/promotion.

- `repo-rag trainer-cycle` now emits a `bundle_gate` payload plus `bundle_gate_passed`.
- When a cycle recompiles a bundle from `artifacts/trainer/generated-training.yaml`, the cycle now
  blocks bundle publish/promotion unless the resulting DSPy benchmark pass-rate clears the
  configured threshold.
- `repo-rag trainer-service` now aggregates `bundle_gate_failure_count`, so long-lived trainer
  runs surface how often candidate bundles were stopped by DSPy benchmark quality rather than by
  retrieval quality alone.
- The current local shell still only exposed an API key, not the full LM endpoint/deployment/API
  version contract, so live trainer-side recompilation remained unvalidated locally in this turn.

## Code And Documentation Changes

Changes landed in this repository:

- added trainer-side bundle benchmark gating in:
  - `src/repo_rag_lab/utilities.py`
- exposed the new `--minimum-bundle-pass-rate` trainer-cycle/service CLI flag in:
  - `src/repo_rag_lab/cli.py`
- exposed the same gate through Make variables in:
  - `Makefile`
- expanded utility and CLI coverage for bundle-gate behavior in:
  - `tests/test_utilities.py`
  - `tests/test_cli_and_dspy.py`
- updated operator, API, DSPy, narrative, planning, and audit-index docs in:
  - `README.md`
  - `docs/architecture/package-api.md`
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
  - `docs/planning/dataset-integration-plan.md`
  - `docs/audit/README.md`

No `../dataset` runtime code changed in this turn. The work stayed inside the trainer-side
repo-RAG lifecycle.

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

- `env | rg '^(DSPY_|AZURE_OPENAI_|OPENAI_API_KEY)'`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_cli_and_dspy.py`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make files-sync`
- `make exploratorium-sync`
- `make verify-surfaces`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

Observed results:

- `env | rg '^(DSPY_|AZURE_OPENAI_|OPENAI_API_KEY)'`:
  showed only `AZURE_OPENAI_API_KEY`; no local endpoint, deployment-name, or API-version
  variables were present for a bounded live trainer-side recompilation run
- `uv run python -m compileall src tests`: passed
- `uv run pytest tests/test_utilities.py tests/test_cli_and_dspy.py`:
  passed, `58 passed`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`:
  passed, `32 passed`
- `uv run repo-rag smoke-test`:
  passed with `command_status: "success"` and `answer_contains_repository: true`
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `make files-sync`:
  passed and refreshed `FILES.md`, `FILES.csv`, and `AGENTS.md.d/FILES.md`
- `make exploratorium-sync`:
  passed and refreshed the exploratorium translation TeX, manifest, and PDF surfaces
- `make verify-surfaces`:
  passed with `issue_count: 0`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`:
  passed, `28 passed`

Verification categories not executed in this turn:

- no live `repo-rag trainer-recompile` run because the local LM environment remained incomplete
- no `make quality` or `make coverage`
- no `../dataset` worker or AKS deployment run

## Status Impact

- Phase 4 of `docs/planning/dataset-integration-plan.md` is now closed through the selected gates:
  - worker queue handoff: done
  - single-pass trainer cycle: done
  - asynchronous trainer/publisher service: done
  - candidate-to-bundle recompilation: done
  - publish/promote behind selected retrieval and DSPy benchmark gates: done
- The remaining integration work is now mostly deployment-oriented:
  - package the trainer service plus recompile loop for AKS or another long-lived deployment
    target
  - add bounded live validation once the local shell exposes full Azure/OpenAI DSPy runtime
    metadata, not only an API key
