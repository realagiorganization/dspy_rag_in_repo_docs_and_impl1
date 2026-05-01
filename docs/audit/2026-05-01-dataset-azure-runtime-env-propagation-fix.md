# 2026-05-01 Dataset Azure Runtime Env Propagation Fix

## Summary

- Updated the downstream `../dataset` worker code so the default `codex` mediation path now
  derives and forwards repo-rag-compatible Azure OpenAI runtime variables when launching
  `repo-rag serve-codex-proxy`.
- Added a second, deployment-level safeguard in the AKS manifest generator: worker containers now
  receive open `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME`,
  `AZURE_OPENAI_API_VERSION`, and `AZURE_OPENAI_MODEL_NAME` values directly when
  `CODEX_AUTH_TYPE=azure`.
- Added workflow-level support for storing those non-secret Azure runtime fields as GitHub Actions
  repository variables in `parallel-prompt-execution-aks.yml`.
- Verified the local `dataset` code changes with targeted compile and pytest coverage, but did not
  run a new AKS workflow after this fix in the current turn.

## Why This Fix Was Needed

- The latest inspected AKS run `25209573387` had already cleared the earlier image-drift and
  flattened `/app/*.py` resolver blockers.
- That run still fell back to plain `codex_cli` because the launched `repo-rag` proxy subprocess
  failed during startup with:
  - `Missing Azure OpenAI runtime settings: AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_CHAT_COMPLETIONS_URI, AZURE_OPENAI_DEPLOYMENT_NAME or AZURE_OPENAI_CHAT_COMPLETIONS_URI, AZURE_OPENAI_API_VERSION`
- The worker had `CODEX_AZURE_CONFIG` and `AZURE_OPENAI_API_KEY`, but it did not pass the
  non-secret Azure runtime fields that `repo_rag_lab.azure_runtime.resolve_azure_openai_runtime()`
  expects.

## Dataset Code Changes

Changed in `../dataset`:

- `.github/workflows/parallel-prompt-execution-aks.yml`
  - added support for open GitHub Actions variables:
    - `AZURE_OPENAI_ENDPOINT`
    - `AZURE_OPENAI_DEPLOYMENT_NAME`
    - `AZURE_OPENAI_API_VERSION`
    - `AZURE_OPENAI_MODEL_NAME`
- `aks_module_generator/mixins/base.py`
  - derive normalized Azure runtime values from either explicit env vars or `CODEX_AZURE_CONFIG`
- `aks_module_generator/mixins/k8s_manifests.py`
  - inject those non-secret Azure runtime values into Azure-auth worker pods
- `docker/prompt-executor/worker_codex_cli_exec.py`
  - derive and pass a proxy-specific subprocess `env` containing the Azure runtime variables
  - keep API key handling unchanged
- `tests/test_aks_module_generator_generate_modules.py`
  - assert worker manifest env includes the derived `AZURE_OPENAI_*` fields
- `tests/unit/test_worker_codex_cli_exec_small.py`
  - assert the launched repo-rag proxy subprocess receives the derived Azure runtime env

## Local Verification Executed

In `../dataset`:

- `python -m compileall docker/prompt-executor aks_module_generator tests/unit/test_worker_codex_cli_exec_small.py tests/test_aks_module_generator_generate_modules.py` — pass
- `uv run pytest tests/unit/test_worker_codex_cli_exec_small.py tests/test_aks_module_generator_generate_modules.py -k 'repo_rag_codex_proxy_session or create_deployment_azure_env or kubernetes_deployment' -q` — pass (`13 passed`, `45 deselected`)
- `uv run pytest tests/test_aks_module_generator_manifests.py -q` — pass (`28 passed`)

In this repository:

- `uv run python -m compileall src tests` — pass
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — pass (`37 passed`)
- `uv run repo-rag smoke-test` — pass
- `cargo build --manifest-path rust-cli/Cargo.toml` — pass
- `make verify-surfaces` — pass
- `make files-sync` — pass

## Current Status

- The previous runtime diagnosis remains valid for run `25209573387`.
- The new local code state in `dataset` should remove that bootstrap failure by ensuring the proxy
  subprocess sees the expected Azure OpenAI env contract.
- `repo-rag-training-traces` and `repo-rag-bundles` have **not** been rechecked after this fix in
  a fresh AKS run during the current turn.

## Remaining Gaps

- No live AKS rerun after the env-propagation fix was inspected in this turn.
- No claim is made yet that `repo-rag-training-traces` now fills successfully.
- `repo-rag-bundles` still requires a separate trainer publish/promote cycle and remains the wrong
  primary success signal for worker-side mediation.
