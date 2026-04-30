# 2026-04-30 Codex Proxy Mediation Layer

## Summary

- Added a new transport-level `repo-rag serve-codex-proxy` surface in
  `src/repo_rag_lab/codex_proxy.py`.
- The proxy accepts Codex Responses API traffic, extracts the user task, runs repository-grounded
  retrieval, attempts DSPy-mediated synthesis first, and injects a developer mediation block back
  into the live request before forwarding it upstream.
- Tightened that mediation path so it is now token-budgeted and signal-aware instead of blindly
  injecting every preview:
  - classify tasks as `deep` vs `trivial`
  - shrink the developer block to top-k essential file hints and evidence previews
  - cap the injected developer block with separate deep/trivial token budgets
  - suppress injection entirely when retrieval + DSPy only produce low-signal boilerplate
  - cache mediation results on disk so per-guild worker PVCs can reuse retrieval/DSPy work across
    multiple Codex requests
- The proxy does not replace Codex as the executor. Instead it keeps Codex as the primary runtime
  and makes `RAG + DSPy` the first-class mediation path in front of Codex when Azure Codex
  Responses traffic is available.
- Added worker-side wiring in `../dataset` so the containerized `codex` path now:
  - keeps `execution_method="codex"`
  - launches the local repo-RAG proxy when the prompt targets a repository-like checkout
  - rewrites Codex Azure config to point at that local Responses-compatible proxy
  - falls back to direct Codex execution if proxy startup or mediation fails
- Explicit `repo_rag_cli` / `dspy` backends remain available for direct repo-answer flows and for
  the local compatibility executor, but they are no longer the only way to get repo-RAG help into
  the worker path.

## Why This Turn Happened

The prior downstream integration treated `repo_rag_cli` and `dspy` as sibling execution methods
that could replace `codex`. That was not aligned with the intended architecture:

- `codex exec` should remain the main executor
- `RAG + DSPy` should operate together as the primary context-shaping layer
- fallback should replace only the failed mediation layer, not the whole executor
- an untrained or unavailable DSPy bundle must never block Codex task execution

The new proxy model satisfies that requirement without needing a fork of the Codex binary itself.

## Current Contract

- Worker-side default `codex` runs now attempt a local repo-RAG mediation proxy when all of the
  following are true:
  - the worker is using Azure Codex Responses config
  - repo-RAG proxying is not disabled through `DATASET_CODEX_REPO_RAG_PROXY=0`
  - the prepared checkout looks like a repository worth mediating
- Mediation order inside the proxy is:
  - `RAG + DSPy` first
  - heuristic mediation when DSPy or retrieval is weak
  - direct pass-through when no useful mediation block can be formed
- The mediation block is no longer unbounded:
  - `DATASET_CODEX_REPO_RAG_TOKEN_BUDGET` and
    `DATASET_CODEX_REPO_RAG_TRIVIAL_TOKEN_BUDGET` cap deep/trivial injections
  - `DATASET_CODEX_REPO_RAG_ESSENTIALS` limits how many file hints/evidence lines survive
  - `DATASET_CODEX_REPO_RAG_CACHE_DIR` and
    `DATASET_CODEX_REPO_RAG_CACHE_TTL_SECONDS` control the persisted cache location and freshness
  - when no meaningful repo-grounded signal exists, the proxy records that status but does not add
    a developer message to the Codex request
- Explicit `execution_method="repo_rag_cli"` and `execution_method="dspy"` still exist for direct
  repo-answer use cases and for the local compatibility executor.
- The worker hot path still exports traces and outcomes into the global Azure Blob + Queue transport
  after Codex finishes, so trainer-side DSPy improvement remains asynchronous.

## Verification

Repo-local:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run pytest tests/test_codex_proxy.py tests/test_utilities.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make files-sync`
- `make verify-surfaces`

Dataset-targeted:

- `python -m compileall src tests`
- `uv run pytest tests/unit/test_worker_codex_cli_exec_small.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py -q`
- `uv run pytest tests/unit/test_worker_codex_cli_exec_small.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/unit/test_worker_codex_cli_exec_branches.py -q`

## Remaining Boundary

- The transport-level mediation path is implemented for the Azure Codex Responses worker flow,
  because that is the production Codex configuration currently wired into the AKS worker image.
- The local compatibility `PromptExecutor` still keeps explicit `repo_rag_cli` auto-detection
  because it does not execute the same full Codex worker path.
- The proxy cache is currently a whole-mediation cache keyed by request plus bundle/runtime
  settings. It reuses retrieval/DSPy results effectively for repeated prompts, but it is not yet a
  separately invalidated retrieval-cache and DSPy-cache pair.
- This turn does not claim model-weight training. The trainer still improves globally published
  DSPy bundles asynchronously from Blob + Queue traces rather than mutating base-model weights.
