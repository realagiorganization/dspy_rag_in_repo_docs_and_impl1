# 2026-04-29 Trainer Recompile From Candidates

## Summary

This audit records the next trainer-side step after `trainer-service`: imported worker traces no
longer stop at cumulative candidate accumulation. The repository now exposes an explicit
`trainer-recompile` surface that merges the base repository training set with trainer-side
candidate examples, writes a generated training corpus under `artifacts/trainer/`, and compiles a
fresh DSPy run from that merged corpus.

- `repo-rag trainer-recompile` now gives the trainer path a concrete bridge from imported
  trace/outcome records to a generated DSPy compile input.
- `repo-rag trainer-cycle` and `repo-rag trainer-service` can reuse that same recompilation path
  after queue drain and candidate materialization instead of stopping at ingestion summaries.
- The generated trainer-side corpus is now persisted explicitly as:
  - `artifacts/trainer/generated-training.yaml`
  - `artifacts/trainer/generated-training-summary.json`
- The local shell used for this turn still did not have a full LM runtime contract for live
  recompilation; only an API key was present, so bounded local verification stayed at compile/test
  coverage instead of a live Azure/OpenAI recompile run.

## Code And Documentation Changes

Changes landed in this repository:

- added trainer-generated training artifact constants in:
  - `src/repo_rag_lab/runtime_artifacts.py`
- added generated merged-training materialization in:
  - `src/repo_rag_lab/training_samples.py`
- added trainer-side recompilation helpers, cycle/service integration, and aggregate counters in:
  - `src/repo_rag_lab/utilities.py`
- exposed the new CLI surface plus cycle/service recompile flags in:
  - `src/repo_rag_lab/cli.py`
- exposed the new Make target and trainer recompile variables in:
  - `Makefile`
- kept the new utility in the verified surface contract via:
  - `src/repo_rag_lab/verification.py`
- added and expanded coverage for generated-training materialization, trainer-recompile payloads,
  and CLI wiring in:
  - `tests/test_training_samples.py`
  - `tests/test_utilities.py`
  - `tests/test_cli_and_dspy.py`
- updated operator, API, narrative, DSPy, planning, and audit-index docs in:
  - `README.md`
  - `docs/architecture/package-api.md`
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
  - `docs/planning/repo-hardening-plan.md`
  - `docs/planning/dataset-integration-plan.md`
  - `docs/audit/README.md`

No `../dataset` runtime code changed in this turn. The new capability is still trainer-side and
extends the repo-RAG repository itself.

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
- `uv run pytest tests/test_training_samples.py tests/test_utilities.py tests/test_cli_and_dspy.py`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- after doc/audit updates:
  - `uv run repo-rag smoke-test`
  - `cargo build --manifest-path rust-cli/Cargo.toml`
  - `make files-sync`
  - `make exploratorium-sync`
  - `make verify-surfaces`
  - `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

Observed results:

- `env | rg '^(DSPY_|AZURE_OPENAI_|OPENAI_API_KEY)'`:
  showed only `AZURE_OPENAI_API_KEY`; no local endpoint, deployment-name, or API-version
  variables were present for a bounded live recompilation run
- `uv run repo-rag smoke-test`:
  passed with `command_status: "success"` and `answer_contains_repository: true`
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `uv run python -m compileall src tests`: passed
- `uv run pytest tests/test_training_samples.py tests/test_utilities.py tests/test_cli_and_dspy.py`:
  passed, `63 passed`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`:
  passed, `31 passed`
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

- Phase 5 of `docs/planning/repo-hardening-plan.md` is further closed:
  - trace export/import: done
  - queued trace handoff: done
  - trainer-cycle: done
  - trainer-service loop: done
  - trainer-side candidate materialization: done
  - generated merged trainer corpus: done
  - explicit trainer-side recompilation surface: done
  - boundary docs for model-level tuning: still pending
- Phase 4 of `docs/planning/dataset-integration-plan.md` is further closed:
  - worker queue handoff: done
  - single-pass trainer cycle: done
  - asynchronous trainer/publisher service: done
  - trainer-side candidate materialization from worker traces: done
  - asynchronous recompilation path from imported traces to fresh DSPy runs: done
  - publish/promote gating hardening: still pending
- The next practical work items are now:
  - tighten publish/promote gates so trainer-side recompilation does not publish merely on a
    minimal retrieval gate
  - package the trainer service plus recompile loop for AKS or another long-lived deployment
    target
  - add bounded live validation once the local shell exposes full Azure/OpenAI DSPy runtime
    metadata, not only an API key
