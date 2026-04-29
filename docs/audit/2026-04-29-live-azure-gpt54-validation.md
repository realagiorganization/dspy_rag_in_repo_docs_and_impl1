# 2026-04-29 Live Azure GPT-5.4 Validation

## Summary

This audit records the first bounded local validation of the live Azure OpenAI path after the
trainer-side deployment surfaces were added. The repository now proves that:

- `repo-rag azure-openai-probe` works against a real Azure OpenAI `gpt-5.4` deployment.
- `repo-rag ask-live` produces a real live repository answer from the same deployment.
- the env-gated live integration test file can run locally instead of skipping when the full Azure
  runtime contract is supplied.
- `repo-rag trainer-recompile` can compile a real DSPy bundle against that live deployment.
- `repo-rag trainer-cycle --recompile-run-name ...` can run the same live recompilation path and
  then correctly block publish when the trainer-side DSPy bundle benchmark gate is not met.

During that validation a real runtime-compatibility bug was fixed in
`src/repo_rag_lab/azure_runtime.py`: the Azure OpenAI chat-completions path previously sent
`max_tokens`, which `gpt-5.4` rejects. The runtime now prefers `max_completion_tokens` and falls
back to `max_tokens` only when a model explicitly reports that the newer parameter is unsupported.

## Configuration Used

The bounded live runs used:

- `AZURE_OPENAI_ENDPOINT=https://gpt45standard.openai.azure.com/`
- `AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5.4`
- `AZURE_OPENAI_API_VERSION=2024-12-01-preview`
- optional `AZURE_OPENAI_MODEL_NAME=gpt-5.4`

The local shell still did not persist those non-secret variables globally, so the commands below
were executed with inline environment assignments while reusing the already configured
`AZURE_OPENAI_API_KEY`.

## Code And Documentation Changes

Changes landed in this repository:

- updated Azure OpenAI chat-completions compatibility in:
  - `src/repo_rag_lab/azure_runtime.py`
- added regression coverage for the preferred and fallback token-parameter behavior in:
  - `tests/test_azure_runtime.py`
- updated operator and architecture docs in:
  - `README.md`
  - `docs/operations/azure-deployment.md`
  - `docs/operations/environment.md`
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
  - `docs/planning/repo-hardening-plan.md`
  - `docs/planning/dataset-integration-plan.md`
  - `docs/audit/README.md`
- updated `../dataset` operator docs to reflect the external-first central inference choice:
  - `../dataset/README.md`
  - `../dataset/USAGE.md`
  - `../dataset/agents.md`

No `../dataset` runtime code changed in this turn.

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

- `uv run python -m compileall src tests`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_azure_runtime.py tests/test_workflow_live.py tests/test_live_azure_integration.py`
- `uv run repo-rag smoke-test`
- `AZURE_OPENAI_ENDPOINT='https://gpt45standard.openai.azure.com/' AZURE_OPENAI_DEPLOYMENT_NAME='gpt-5.4' AZURE_OPENAI_API_VERSION='2024-12-01-preview' AZURE_OPENAI_MODEL_NAME='gpt-5.4' uv run repo-rag azure-openai-probe`
- `AZURE_OPENAI_ENDPOINT='https://gpt45standard.openai.azure.com/' AZURE_OPENAI_DEPLOYMENT_NAME='gpt-5.4' AZURE_OPENAI_API_VERSION='2024-12-01-preview' AZURE_OPENAI_MODEL_NAME='gpt-5.4' uv run repo-rag ask-live --question 'What does this repository research?' --provider azure-openai --output json`
- `AZURE_OPENAI_ENDPOINT='https://gpt45standard.openai.azure.com/' AZURE_OPENAI_DEPLOYMENT_NAME='gpt-5.4' AZURE_OPENAI_API_VERSION='2024-12-01-preview' AZURE_OPENAI_MODEL_NAME='gpt-5.4' uv run pytest tests/test_live_azure_integration.py`
- `AZURE_OPENAI_ENDPOINT='https://gpt45standard.openai.azure.com/' AZURE_OPENAI_DEPLOYMENT_NAME='gpt-5.4' AZURE_OPENAI_API_VERSION='2024-12-01-preview' AZURE_OPENAI_MODEL_NAME='gpt-5.4' uv run repo-rag trainer-recompile --root . --run-name trainer-live-check --output json`
- `AZURE_OPENAI_ENDPOINT='https://gpt45standard.openai.azure.com/' AZURE_OPENAI_DEPLOYMENT_NAME='gpt-5.4' AZURE_OPENAI_API_VERSION='2024-12-01-preview' AZURE_OPENAI_MODEL_NAME='gpt-5.4' uv run repo-rag trainer-cycle --root . --queue-name dataset --recompile-run-name trainer-cycle-live-check --output json`
- `make files-sync`
- `make exploratorium-sync`
- `make verify-surfaces`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

Observed results:

- `uv run python -m compileall src tests`: passed
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_azure_runtime.py tests/test_workflow_live.py tests/test_live_azure_integration.py`:
  passed, `44 passed, 3 skipped`
- `uv run repo-rag smoke-test`:
  passed with `command_status: "success"` and `answer_contains_repository: true`
- `uv run repo-rag azure-openai-probe` with the inline Azure OpenAI contract:
  passed with `command_status: "success"`, `reply: "OPENAI_OK"`, and `model:
  "gpt-5.4-2026-03-05"`
- `uv run repo-rag ask-live ... --provider azure-openai --output json`:
  passed with `command_status: "success"` and returned a live repository answer plus the shared
  runtime trace payload
- `uv run pytest tests/test_live_azure_integration.py` with the same inline Azure OpenAI contract:
  passed, `3 passed`
- `uv run repo-rag trainer-recompile --root . --run-name trainer-live-check --output json`:
  passed with `command_status: "success"`, wrote
  `artifacts/dspy/trainer-live-check/program.json`,
  `artifacts/dspy/trainer-live-check/metadata.json`, and
  `artifacts/dspy/trainer-live-check/bundle.json`, and reported a live benchmark summary with
  `case_count: 8`, `pass_count: 6`, `pass_rate: 0.75`
- `uv run repo-rag trainer-cycle --root . --queue-name dataset --recompile-run-name trainer-cycle-live-check --output json`:
  returned `command_status: "fail"` by design because the trainer-side bundle gate blocked
  publish; that same run still proved the live recompilation path worked, reporting
  `recompile_status: "compiled"`, `gate_passed: true` for retrieval, and `bundle_gate_passed:
  false` with `benchmark_pass_rate: 0.625`
- `make files-sync`:
  passed and refreshed `FILES.md`, `FILES.csv`, and `AGENTS.md.d/FILES.md`
- `make exploratorium-sync`:
  passed and refreshed the exploratorium translation TeX, manifest, and PDF surfaces
- `make verify-surfaces`:
  passed with `issue_count: 0`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`:
  passed, `28 passed`

Verification categories not executed in this turn:

- `make quality`
- `make coverage`
- live Azure AI Inference provider validation
- live Kubernetes deployment of the trainer manifests
- `../dataset` runtime or AKS execution in this exact turn

## Status Impact

- The repository no longer has an unverified Azure OpenAI compatibility story for GPT-5.4-class
  chat-completions deployments; the runtime bug is fixed and locally validated.
- The current central inference decision is now explicit instead of implied: workers and
  trainer-side live recompilation stay on an external Azure/OpenAI inference contract first,
  while any shared internal inference tier remains a later optimization rather than a hidden
  requirement for the current runtime.
- The current blocker for broader live trainer-side operation is no longer basic Azure runtime
  compatibility. It is now higher-level policy work such as the chosen bundle gate thresholds,
  central inference placement, and whether the live-recompiled bundle should clear the benchmark
  threshold before promotion.
- The trainer-side publish gate is now backed by direct live evidence rather than only unit tests:
  a live recompilation can succeed while publish still stays blocked.
