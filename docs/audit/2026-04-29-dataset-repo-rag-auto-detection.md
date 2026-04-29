# 2026-04-29 Dataset Repo-RAG Auto-Detection

## Summary

This audit records the next `../dataset` integration step after bundle fetch and trace-import
hooks: both downstream runtime paths now auto-detect repo-RAG-capable target repositories and
switch the default `codex` path to `repo_rag_cli` when the prepared repository itself exposes
repo-RAG-native markers.

- The local `PromptExecutor` no longer requires a manual `repo_rag_cli` override when the target
  repository already looks like a repo-RAG-native project.
- The container worker path now applies the same auto-detection against the prepared repository
  checkout before it would otherwise run the default `codex` path.
- Explicit execution-method choices still win: `repo_rag_cli`, `dspy`, `simple_llm`, and explicit
  prompt-level overrides bypass auto-detection.
- The auto-detect path reuses the same bundle lookup, overlay initialization, trace export, and
  best-effort trace import hooks that were already added to the explicit repo-RAG backend.

This closes the plan item about teaching the worker/runtime flow to recognize repositories that
expose repo-RAG and moves the remaining `dataset` integration work toward accepted-outcome
ingestion and asynchronous trainer orchestration.

## Code And Documentation Changes

Changes landed in `../dataset`:

- added repo-RAG-native auto-detection in:
  - `../dataset/src/execution/prompt_executor.py`
  - `../dataset/docker/prompt-executor/worker_execution_prompt.py`
- added focused auto-detection coverage in:
  - `../dataset/tests/unit/test_prompt_executor_repo_rag_cli.py`
  - `../dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py`
- documented the new behavior and env toggles in:
  - `../dataset/README.md`
  - `../dataset/USAGE.md`
  - `../dataset/agents.md`
  - `../dataset/agents.md.d/roadmap.md`

Changes landed in this repository:

- marked the auto-detection plan item complete in:
  - `docs/planning/dataset-integration-plan.md`
- updated the top-level narrative in:
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
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

Commands executed locally on `2026-04-29` for this turn:

In `../dataset`:

- `python -m compileall /home/standard/Desktop/realagi_work/dataset/src/execution/prompt_executor.py /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_execution_prompt.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_prompt_executor_repo_rag_cli.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py`
- `cd /home/standard/Desktop/realagi_work/dataset && pytest tests/unit/test_prompt_executor_repo_rag_cli.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py`
- `cd /home/standard/Desktop/realagi_work/dataset && pytest tests/unit/test_prompt_executor_repo_rag_cli.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/test_worker_execution_prompt_fallback_integration.py tests/test_worker_execution_prompt_integration.py::test_dynamic_worker_execute_prompt_uses_primary_repo_when_selection_fails tests/test_worker_execution_prompt_integration.py::test_dynamic_worker_execute_prompt_prepares_repository_from_direct_hint tests/test_worker_execution_prompt_integration.py::test_dynamic_worker_execute_prompt_non_discord_dry_run_uses_fallback_metadata`

In this repository:

- earlier in the same turn, before the auto-detection patch:
  - `uv run python -m compileall src tests`
  - `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
  - `uv run repo-rag smoke-test`
  - `cargo build --manifest-path rust-cli/Cargo.toml`
- after the plan/audit/doc updates:
  - `make files-sync`
  - `make paper-build`
  - `make verify-surfaces`
  - `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

Observed results:

`../dataset`:

- compileall command: passed
- focused repo-RAG backend plus auto-detect suite: passed, `6 passed`
- broader targeted worker integration slice: passed, `10 passed`
- no full AKS deployment workflow, no trainer queue, and no end-to-end Kubernetes validation ran in
  this turn

This repository:

- earlier repo-native verification loop remained green:
  - `uv run python -m compileall src tests`: passed
  - `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`: passed, `24 passed`
  - `uv run repo-rag smoke-test`: passed with `command_status: "success"`
  - `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- documentation/surface sync loop after the new audit and plan updates:
  - `make files-sync`: passed
  - `make paper-build`: passed
  - `make verify-surfaces`: passed with `issue_count: 0`
  - `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`:
    passed, `28 passed`

Verification categories not executed in this turn:

- no `make quality` or `make coverage`
- no live Azure/OpenAI integration suite
- no MCP runtime validation
- no full `../dataset` AKS pipeline run

## Status Impact

- Phase 3 of `docs/planning/dataset-integration-plan.md` is now further closed:
  - local `repo_rag_cli` backend: done
  - worker-side `repo_rag_cli` / `dspy` backend: done
  - worker/runtime auto-detection for repo-RAG-capable repositories: done
  - post-run trace upload hooks that do not block the main result: done
- Remaining `dataset` integration work is now centered on:
  - accepted-outcome ingestion
  - queued/asynchronous trace handoff
  - global trainer/publisher orchestration
