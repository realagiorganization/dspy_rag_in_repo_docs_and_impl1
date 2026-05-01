# 2026-05-01 Dataset Azure Responses API-Version Default Fix

## Summary

- Inspected live AKS run `25211606827`, which used fresh images
  `prompt-executor:20260501-102931` and `queue-initializer:20260501-102931`.
- Confirmed the repo-rag mediation path was now active enough to export inline
  `repo_rag_*` artifacts, but the worker still failed before successful Codex
  execution because Azure rejected the Responses API call.
- The concrete error captured in the run artifacts was:
  - `Azure OpenAI Responses API is enabled only for api-version 2025-03-01-preview and later`
- Updated downstream `../dataset` code so Azure-auth worker and proxy paths no
  longer default to `2023-12-01-preview` when `CODEX_AZURE_CONFIG` omits an
  explicit `query_params.api-version`.
- Also changed the proxy config rewrite path so an explicit
  `AZURE_OPENAI_API_VERSION` env var now overrides any older `api-version`
  embedded in `CODEX_AZURE_CONFIG`.

## Why This Fix Was Needed

- The user-supplied `CODEX_AZURE_CONFIG` now uses the modern Azure Responses
  shape:
  - `base_url = "https://gpt45standard.openai.azure.com/openai/v1"`
  - `wire_api = "responses"`
  - no explicit `query_params = { api-version = ... }`
- The inspected worker/image stack still had several old fallbacks that filled
  in `2023-12-01-preview` when no explicit version existed:
  - `../dataset/docker/prompt-executor/worker_codex_auth_setup.py`
  - `../dataset/docker/prompt-executor/worker_codex_cli_exec.py`
  - `../dataset/aks_module_generator/mixins/base.py`
- Those old defaults were sufficient for older Azure OpenAI surfaces but are no
  longer valid for the Azure Responses API used by the Codex proxy path.
- The run evidence therefore shifted the primary blocker again:
  - image drift: fixed earlier
  - flattened `/app/*.py` project-root resolution: fixed earlier
  - missing proxy runtime env: fixed earlier
  - stale Azure Responses `api-version` default: newly identified and fixed in
    this turn

## Live Run Evidence

Inspected AKS run:

- GitHub Actions run: `25211606827`
- Worker image: `prompt-executor:20260501-102931`
- Queue initializer image: `queue-initializer:20260501-102931`
- Azure artifact prefix:
  - `executions/25211606827_20260501_105955`

Confirmed from the downloaded run artifacts:

- `backend_used` still resolved to `codex_cli` at the top-level result because
  the actual `codex exec` failed
- inline `repo_rag_*` artifacts were present, proving the proxy path was now
  entering live mediation instead of being skipped before startup
- `codex_response.txt` contained the Azure error:
  - `BadRequest`
  - `Azure OpenAI Responses API is enabled only for api-version 2025-03-01-preview and later`
- `repo-rag-training-traces` remained empty after the run because execution
  failed before successful downstream handoff
- `repo-rag-bundles` remained empty, which is still expected without a separate
  trainer publish/promote cycle

## Dataset Code Changes

Changed in `../dataset`:

- `docker/prompt-executor/worker_codex_auth_setup.py`
  - raised the default Azure Responses-compatible API version from
    `2023-12-01-preview` to `2025-03-01-preview`
  - uses the new default for config parsing and Azure preflight fallback
- `docker/prompt-executor/worker_codex_cli_exec.py`
  - raised the same default in repo-rag proxy Azure runtime derivation
  - changed proxy config rewriting so `AZURE_OPENAI_API_VERSION` overrides any
    stale `query_params.api-version` from `CODEX_AZURE_CONFIG`
- `aks_module_generator/mixins/base.py`
  - raised the default worker manifest/runtime value to
    `2025-03-01-preview`
- `docker/prompt-executor/router-mcp.js`
  - raised the legacy router default to `2025-03-01-preview` so the image does
    not keep a second stale Azure Responses fallback
- tests updated:
  - `tests/unit/test_worker_codex_auth_setup_small.py`
  - `tests/unit/test_worker_codex_cli_exec_small.py`
  - `tests/test_000_worker_pipeline_coverage.py`
  - `tests/unit/test_execute_worker_prompts_impl_codex_logging.py`
  - `tests/unit/test_execute_worker_prompts_unit.py`

## Local Verification Executed

In `../dataset`:

- `python -m compileall docker/prompt-executor aks_module_generator tests/unit/test_worker_codex_auth_setup_small.py tests/unit/test_worker_codex_cli_exec_small.py tests/test_000_worker_pipeline_coverage.py tests/unit/test_execute_worker_prompts_impl_codex_logging.py tests/unit/test_execute_worker_prompts_unit.py` — pass
- `uv run pytest tests/unit/test_worker_codex_auth_setup_small.py tests/unit/test_worker_codex_cli_exec_small.py -q` — pass (`70 passed`)
- `uv run pytest tests/unit/test_execute_worker_prompts_impl_codex_logging.py::test_validate_azure_deployment_success_and_not_found tests/unit/test_execute_worker_prompts_unit.py::test_validate_azure_deployment_calls_http tests/unit/test_execute_worker_prompts_unit.py::test_validate_azure_deployment_handles_404 -q` — pass (`3 passed`)
- `uv run pytest tests/test_aks_module_generator_generate_modules.py::test_create_deployment_azure_env tests/test_aks_module_generator_manifests.py -q` — pass (`29 passed`)

Notes on broader downstream suites:

- A broad ad hoc run across large `execute_worker_prompts_impl` files was noisy
  and failed on pre-existing auth-fixture assumptions unrelated to the new
  Azure `api-version` change. The targeted verification above directly covered
  the modified defaults, manifest wiring, proxy rewrite precedence, and Azure
  preflight callsites.

In this repository:

- `uv run python -m compileall src tests` — pass
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — pass
- `uv run repo-rag smoke-test` — pass
- `cargo build --manifest-path rust-cli/Cargo.toml` — pass
- `make files-sync` — pass
- `make verify-surfaces` — pass

## Current Status

- The latest live AKS evidence now shows the repo-rag proxy path getting far
  enough to prove mediation/bootstrap progress instead of failing before startup.
- The newly fixed default/preference bug is the concrete reason that run
  `25211606827` still failed against Azure Responses.
- No fresh AKS rerun after this `api-version` fix was inspected in the current
  turn, so `repo-rag-training-traces` is still unverified after the newest code
  state.

## Remaining Gaps

- A new image build + AKS rerun is still required to verify that:
  - the Azure Responses API call now succeeds with `2025-03-01-preview` or later
  - `repo-rag-training-traces` stops remaining empty
- `repo-rag-bundles` remains the wrong primary success signal for worker-side
  mediation because bundle publication still belongs to the separate trainer
  publish/promote lifecycle.
