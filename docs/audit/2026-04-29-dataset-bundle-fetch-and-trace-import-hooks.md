# 2026-04-29 Dataset Bundle Fetch And Trace Import Hooks

## Summary

This audit records the next `../dataset` integration step after the worker-side `repo_rag_cli`
backend became available: both downstream runtime paths now perform a first-pass bundle/trace
lifecycle around the existing `repo-rag` calls.

- The local `PromptExecutor` path now resolves a promoted bundle version from a trainer repository
  before answering when trainer metadata is configured.
- The container worker path now does the same bundle inspection at worker start, so bundle-aware
  execution is no longer local-only.
- Both paths still auto-initialize a local overlay when practical and now also export a normalized
  trace after answering.
- Both paths can then best-effort import that trace back into a trainer repository without turning
  trace-ingest failures into main prompt failures.
- The integration plan now reflects that stable bundle fetch and repo-local trace persistence are
  complete, while accepted-outcome ingestion and asynchronous publishing are still open.

This moves the `dataset` integration story from “worker can call repo-RAG” to “worker can call
repo-RAG while attaching itself to a promoted bundle channel and returning normalized traces to a
trainer-side repository.”

## Code And Documentation Changes

Changes landed in `../dataset`:

- extended the local repo-RAG backend in:
  - `../dataset/src/execution/prompt_executor.py`
- extended the container worker repo-RAG backend in:
  - `../dataset/docker/prompt-executor/worker_execution_prompt.py`
- expanded focused backend coverage in:
  - `../dataset/tests/unit/test_prompt_executor_repo_rag_cli.py`
  - `../dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py`
- documented the bundle/trace lifecycle in:
  - `../dataset/README.md`
  - `../dataset/USAGE.md`
  - `../dataset/agents.md`
  - `../dataset/agents.md.d/roadmap.md`

Changes landed in this repository to keep the research story and plan current:

- refined checklist state in:
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

- `pytest tests/unit/test_prompt_executor_repo_rag_cli.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py`
- earlier in the same implementation turn, before the final documentation sync:
  - `python -m compileall /home/standard/Desktop/realagi_work/dataset/src/execution/prompt_executor.py /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_execution_prompt.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_prompt_executor_repo_rag_cli.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py`
  - `cd /home/standard/Desktop/realagi_work/dataset && pytest tests/unit/test_prompt_executor_repo_rag_cli.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/test_worker_execution_prompt_fallback_integration.py tests/test_worker_execution_prompt_integration.py::test_dynamic_worker_execute_prompt_uses_primary_repo_when_selection_fails tests/test_worker_execution_prompt_integration.py::test_dynamic_worker_execute_prompt_prepares_repository_from_direct_hint tests/test_worker_execution_prompt_integration.py::test_dynamic_worker_execute_prompt_non_discord_dry_run_uses_fallback_metadata`

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

Observed results:

`../dataset`:

- focused backend unit suite: passed, `4 passed`
- earlier targeted integration slice for the same code path: passed, `8 passed`
- no AKS deployment workflow, trainer queue, or end-to-end Kubernetes validation was executed in
  this turn

This repository:

- `uv run python -m compileall src tests`: passed
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

Verification categories not executed in this turn:

- no `make quality` or `make coverage`
- no live Azure/OpenAI integration suite
- no MCP runtime validation
- no full `../dataset` AKS pipeline run

## Status Impact

- Phase 2 of `docs/planning/dataset-integration-plan.md` is now more explicit:
  - stable bundle fetch at worker start: done
  - repo-local overlay creation: done
  - repo-local trace persistence: done
  - accepted-outcome ingestion: still pending
- Phase 3 is further closed:
  - local `repo_rag_cli` backend: done
  - worker-side `repo_rag_cli` / `dspy` backend: done
  - post-run trace upload hooks that do not block the main result: done
  - worker-preparation auto-detection: still pending
- The remaining integration work is now about queueing and trainer orchestration rather than about
  whether workers can speak the repo-RAG runtime at all.
