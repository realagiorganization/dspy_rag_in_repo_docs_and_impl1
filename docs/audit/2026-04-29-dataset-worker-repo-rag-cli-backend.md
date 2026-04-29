# 2026-04-29 Dataset Worker `repo_rag_cli` Backend

## Summary

This audit records the next downstream integration step after the local `../dataset`
`PromptExecutor` backend: the container worker path under `../dataset/docker/prompt-executor/`
now supports the same `repo_rag_cli` and `dspy` execution modes.

- `../dataset` no longer limits repo-RAG execution to the local `PromptExecutor`.
- The worker execution path now branches into `repo-rag` when `execution_method` is
  `repo_rag_cli` or `dspy`.
- The worker backend auto-initializes a repo-local overlay through `repo-rag overlay-init` when
  no explicit overlay is supplied.
- The worker backend persists `repo_rag_*.json` artifacts plus a compatibility
  `codex_response.txt` so existing artifact publishers still work.
- The worker backend exports a normalized trace through `repo-rag trace-export`.
- The worker image now installs `uv`, so the container can execute `uv run repo-rag ...` when the
  repo-RAG checkout is mounted or otherwise reachable through `DATASET_REPO_RAG_PROJECT_ROOT` or
  `DATASET_REPO_RAG_COMMAND`.

This moves the `dataset` integration story from “local backend only” to “local plus container
worker runtime available,” while leaving bundle fetch/promotion, trace upload, and the global
trainer loop as the main remaining work.

## Code Changes

Changes landed in `../dataset`:

- added worker-side repo-RAG execution to:
  - `../dataset/docker/prompt-executor/worker_execution_prompt.py`
- added focused worker coverage for success and DSPy-fallback flows:
  - `../dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py`
- documented the container-path backend and runtime contract in:
  - `../dataset/README.md`
  - `../dataset/USAGE.md`
  - `../dataset/agents.md`
  - `../dataset/agents.md.d/roadmap.md`
- installed `uv` in the worker image:
  - `../dataset/docker/prompt-executor/Dockerfile`

Changes landed in this repository to keep the research story current:

- updated the integration plan in:
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
- `make paper-build`
- `make verify-surfaces`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

Commands executed locally on `2026-04-29` for this turn:

In `../dataset`:

- `python -m compileall /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_execution_prompt.py /home/standard/Desktop/realagi_work/dataset/src/execution/prompt_executor.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_prompt_executor_repo_rag_cli.py`
- `cd /home/standard/Desktop/realagi_work/dataset && pytest tests/unit/test_prompt_executor_repo_rag_cli.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/test_worker_execution_prompt_fallback_integration.py tests/test_worker_execution_prompt_integration.py::test_dynamic_worker_execute_prompt_uses_primary_repo_when_selection_fails tests/test_worker_execution_prompt_integration.py::test_dynamic_worker_execute_prompt_prepares_repository_from_direct_hint tests/test_worker_execution_prompt_integration.py::test_dynamic_worker_execute_prompt_non_discord_dry_run_uses_fallback_metadata`

Additional non-gating exploration run during implementation:

- `cd /home/standard/Desktop/realagi_work/dataset && pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/test_worker_execution_prompt_integration.py tests/test_worker_execution_prompt_fallback_integration.py`

In this repository:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make files-sync`
- `make exploratorium-sync`
- `make paper-build`
- `make verify-surfaces`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

Observed results:

`../dataset`:

- compileall command: passed
- targeted local/worker repo-RAG suite: passed, `8 passed`
- broader worker integration exploration run: failed, `15 passed` and `2 failed`
  - failing nodes:
    - `tests/test_worker_execution_prompt_integration.py::test_dynamic_worker_execute_prompt_applies_azure_model_hint`
    - `tests/test_worker_execution_prompt_integration.py::test_dynamic_worker_execute_prompt_applies_azure_model_hint_from_content_marker`
  - reason observed in the assertions:
    - those tests expect `worker.codex_config_payload` to remain mutated after `execute_prompt()`
    - current worker code restores the original Azure config in the `finally` block, so those
      assertions do not describe the current runtime behavior
  - this mismatch is outside the new `repo_rag_cli` path and was not changed in this turn

This repository:

- `uv run python -m compileall src tests`: passed
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`: passed, `24 passed`
- `uv run repo-rag smoke-test`: passed with `command_status: "success"` and
  `answer_contains_repository: true`
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `make files-sync`: passed
- `make exploratorium-sync`: passed
- `make paper-build`: passed
- `make verify-surfaces`: passed with `issue_count: 0`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`:
  passed, `28 passed`

## Status Impact

- Phase 2 of `docs/planning/dataset-integration-plan.md` is now partially closed:
  - worker-side local overlay initialization before answering: done
  - stable bundle fetch: pending
  - trace persistence plus accepted-outcome handling: still partial
- Phase 3 is now further closed:
  - local `repo_rag_cli` backend: done
  - worker-side `repo_rag_cli` / `dspy` backend in container execution: done
  - retrieval and DSPy worker artifacts: done
  - worker-preparation auto-detection and asynchronous trace upload: pending
- The remaining `dataset` work is now centered on bundle lifecycle, async upload/publish, and
  global trainer orchestration rather than on basic worker/backend wiring.
