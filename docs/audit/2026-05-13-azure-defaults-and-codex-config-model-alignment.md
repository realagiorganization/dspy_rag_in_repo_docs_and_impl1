# 2026-05-13 Azure Defaults And CODEX_AZURE_CONFIG Model Alignment

## Scope

Investigate why Azure token burn remained dominated by `gpt-5.4` after GitHub Actions variables
were changed to:

- `AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o`
- `AZURE_OPENAI_MODEL_NAME=gpt-4o`
- `AZURE_OPENAI_API_VERSION=2025-03-01-preview`

The immediate goal was to verify whether live trainer/helper/runtime still had hidden `gpt-5.4`
paths and to fix the repository so the intended cheaper default actually wins.

## Confirmed Root Causes

Two independent configuration paths were still preserving `gpt-5.4`.

### 1. Trainer shell defaults still hardcoded `gpt-5.4`

`../dataset/deploy_repo_rag_trainer.sh` still defaulted:

- `AZURE_OPENAI_DEPLOYMENT_NAME:=gpt-5.4`
- `AZURE_OPENAI_MODEL_NAME:=gpt-5.4`

So any deploy path that did not receive explicit overrides could recreate trainer secrets against
`gpt-5.4`.

### 2. Worker Codex path preferred stale `CODEX_AZURE_CONFIG.model`

The prompt worker Azure path uses `CODEX_AZURE_CONFIG` for `codex exec`, not the plain
`AZURE_OPENAI_*` env vars. The stale config payload could still carry:

- `model = "gpt-5.4"`

That happened in two places:

- GitHub Actions created the `codex-azure-config` secret from `CODEX_AZURE_CONFIG`
- worker auth setup normalized the config shape but preserved the embedded `model`

So even with:

- `AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o`
- `AZURE_OPENAI_MODEL_NAME=gpt-4o`

the live Azure Codex worker still used `gpt-5.4` unless a per-prompt `model_hint` explicitly
overrode the config model.

## Contract Clarification

The intended model ownership remains:

- `codex exec` uses `CODEX_AZURE_CONFIG`, optionally overridden by prompt `model_hint`
- DSPy helper/runtime uses `DSPY_*` first, then `AZURE_OPENAI_*`
- trainer compile/recompile uses `DSPY_*` first, then `AZURE_OPENAI_*`

This fix does **not** merge helper/trainer with Codex auth. It only ensures the default Azure
Codex config secret is rewritten to match the configured default Azure model instead of silently
preserving stale `gpt-5.4`.

## Local Fixes

### Dataset repo

- `docker/prompt-executor/worker_codex_auth_setup.py`
  - added env-aware model normalization so `AZURE_OPENAI_MODEL_NAME` /
    `AZURE_OPENAI_DEPLOYMENT_NAME` override stale `CODEX_AZURE_CONFIG.model` during Azure auth
    setup
- `aks_module_generator/mixins/secrets.py`
  - `create_codex_azure_secret()` now normalizes and rewrites the config blob before storing it in
    the Kubernetes secret
- `deploy_repo_rag_trainer.sh`
  - default trainer deployment/model values changed from `gpt-5.4` to `gpt-4o`
  - helper/trainer DSPy paths now rely on dedicated scoped variables rather than a shared
    `DSPY_MODEL`
- `.env.example`
  - examples updated to `gpt-4o`

## Validation

Dataset-side checks:

- `pytest tests/unit/test_worker_codex_auth_setup_small.py -q`
- `pytest tests/test_aks_module_generator_credentials_guilds.py -q`
- `pytest tests/unit/test_deploy_repo_rag_trainer_script.py -q`
- `pytest tests/test_aks_module_generator_generate_modules.py::test_create_deployment_azure_env tests/test_aks_module_generator_generate_modules.py::test_generate_modules_writes_bash_valid_deploy_script -q`
- `bash -n deploy_repo_rag_trainer.sh`

Repo baseline checks:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

## Expected Live Effect

After redeploy:

- trainer secrets created through the dataset deploy path should default to `gpt-4o`, not
  `gpt-5.4`
- Azure worker secrets should normalize stale `CODEX_AZURE_CONFIG` to the configured default model
  unless a prompt `model_hint` explicitly overrides it
- prompt-worker burn from stale Azure config should no longer silently stay on `gpt-5.4`

## Remaining Limitation

This change does not prove the live cluster has already switched. A new deploy/run must still
confirm:

- live trainer secret values
- live worker `CODEX_AZURE_CONFIG` model
- reduced `gpt-5.4` usage in Azure Monitor
