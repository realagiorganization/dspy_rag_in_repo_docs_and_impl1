# 2026-04-29 Dataset Local `repo_rag_cli` Backend

## Summary

This audit records the first real downstream execution integration between this repository and the
local `../dataset` pipeline.

- `../dataset` no longer treats its local `dspy` execution mode as a pure stub.
- A new local `repo_rag_cli` backend now calls `repo-rag ask --output json` from inside
  `../dataset/src/execution/prompt_executor.py`.
- The `dspy` execution flag in that local executor now routes through the same backend, first
  attempting `repo-rag ask --use-dspy` and then falling back to baseline repo-RAG when DSPy LM
  credentials are unavailable.
- Prompt artifacts in `../dataset` now persist the repo-RAG JSON envelope, runtime trace, backend
  metadata, command line, and synthesized answer text instead of only a local stub response.

This closes the first item in Phase 3 of
`docs/planning/dataset-integration-plan.md`: a local `repo_rag_cli` backend now exists before the
AKS worker path is migrated.

## Code Changes

Changes landed in `../dataset`:

- added the local repo-RAG-backed executor path:
  - `../dataset/src/execution/prompt_executor.py`
- added an explicit CLI choice for the local backend:
  - `../dataset/main_core.py`
- added direct unit coverage for the backend and the DSPy-to-baseline fallback:
  - `../dataset/tests/unit/test_prompt_executor_repo_rag_cli.py`
- updated local operator and roadmap docs:
  - `../dataset/README.md`
  - `../dataset/USAGE.md`
  - `../dataset/DESCRIPTION.md`
  - `../dataset/LEGAL_ANSWERS.md`
  - `../dataset/agents.md`
  - `../dataset/agents.md.d/roadmap.md`

Changes landed in this repository to keep the research story current:

- marked the `repo_rag_cli` backend step complete in:
  - `docs/planning/dataset-integration-plan.md`
- updated the top-level research narrative in:
  - `docs/architecture/research-narrative.md`

## Verification

Configured verification surfaces in this repository still include:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make files-sync`
- `make exploratorium-sync`
- `make exploratorium-build`
- `make paper-build`
- `make verify-surfaces`
- `make quality`

Commands executed locally on `2026-04-29` for this turn:

In `../dataset`:

- `python -m compileall /home/standard/Desktop/realagi_work/dataset/main_core.py /home/standard/Desktop/realagi_work/dataset/src/execution/prompt_executor.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_prompt_executor_repo_rag_cli.py`
- `cd /home/standard/Desktop/realagi_work/dataset && pytest tests/test_prompt_executor_integration.py tests/unit/test_prompt_executor_more.py tests/unit/test_prompt_executor_result_payloads.py tests/unit/test_prompt_executor_canonical_single_prompt.py tests/unit/test_prompt_executor_repo_rag_cli.py`
- `cd /home/standard/Desktop/realagi_work/dataset && pytest tests/bdd/test_prompt_executor.py`
- `cd /home/standard/Desktop/realagi_work/dataset && pytest tests/unit/test_data_categorizer_pipeline_more.py::test_pipeline_persistence_reporting_model_and_execution_helpers tests/unit/test_main_core_helpers_extra.py::test_main_all_action_writes_cli_and_processing_outputs`

In this repository:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make files-sync`
- `make exploratorium-sync`
- `make exploratorium-build`
- `make paper-build`
- `make verify-surfaces`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`
- `make quality`

Observed results:

`../dataset`:

- compileall command: passed
- prompt-executor unit/integration suite: passed, `15 passed`
- prompt-executor BDD suite: passed, `5 passed`
- execution-summary compatibility slice: passed, `2 passed`

This repository:

- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`: passed, `24 passed`
- `uv run repo-rag smoke-test`: passed with `command_status: "success"` and
  `answer_contains_repository: true`
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `make files-sync`: passed
- `make exploratorium-sync`: passed
- `make exploratorium-build`: passed
- `make paper-build`: passed
- `make verify-surfaces`: passed with `issue_count: 0`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`:
  passed, `28 passed`
- `make quality`: passed with:
  - `182 passed`
  - `3 skipped`
  - total coverage `85.22%`

## Status Impact

- Phase 3 of `docs/planning/dataset-integration-plan.md` is now partially closed:
  - local `repo_rag_cli` backend: done
  - worker-preparation auto-detection: pending
  - post-run trace upload hooks: pending
  - worker artifact promotion and upload semantics: pending
- The downstream local pipeline can now consume the existing repo-RAG JSON command envelope instead
  of a placeholder stub path.
- The AKS worker path under `../dataset/docker/prompt-executor/` is still not migrated to this
  backend, so cluster execution remains a separate follow-up phase.
