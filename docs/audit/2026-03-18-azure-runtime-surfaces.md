# Azure Runtime Surfaces Audit

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Repository root: `/home/standard/dspy_rag_in_repo_docs_and_impl1`
- Verification worktree: `/tmp/repo-next-steps-92GBP9`
- Git base during verification: `828dc53212f7749079b99767b09947c91f3ed773`

## Scope

This audit captures the follow-up roadmap work that:

- normalized Azure OpenAI and Azure AI Inference runtime configuration,
- promoted the live Azure probes into first-class `repo-rag` and `make` commands, and
- carried that work into the next step by adding a live repository-answer path that reuses local
  retrieval plus Azure-backed synthesis.

## Executed Commands

Executed successfully in this turn:

- `uv sync --extra azure`
- `uv lock`
- `make hooks-install`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_azure_runtime.py tests/test_workflow_live.py tests/test_utilities.py tests/test_cli_and_dspy.py tests/test_verification.py tests/test_repository_rag_bdd.py`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make quality`
- `set -a; . /home/standard/dspy_rag_in_repo_docs_and_impl1/.env; set +a; make azure-openai-probe`
- `set -a; . /home/standard/dspy_rag_in_repo_docs_and_impl1/.env; set +a; make azure-inference-probe`
- `set -a; . /home/standard/dspy_rag_in_repo_docs_and_impl1/.env; set +a; make ask-live QUESTION="What does this repository research?" LIVE_PROVIDER=azure-openai`
- `set -a; . /home/standard/dspy_rag_in_repo_docs_and_impl1/.env; set +a; make ask-live QUESTION="What does this repository research?" LIVE_PROVIDER=azure-inference`

## Notable Results

- `uv run pytest ...`: passed, `32` focused tests covering Azure runtime normalization, the new
  live workflow path, CLI surfaces, utility surfaces, and Makefile verification
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`: passed, `10` tests
- `uv run repo-rag smoke-test`: passed with `answer_contains_repository: true`,
  `mcp_candidate_count: 1`, and manifest path `artifacts/azure/repo-rag-smoke.json`
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `make quality`: passed with `99` tests and `85.19%` total coverage
- `make azure-openai-probe`: passed and returned `OPENAI_OK` from deployment `gpt-4o`,
  resolved model `gpt-4o-2024-11-20`, API version `2025-01-01-preview`
- `make azure-inference-probe`: passed and returned `INFERENCE_OK`, normalized the configured
  `AZURE_INFERENCE_ENDPOINT` from the full `/chat/completions?...` URI to the deployment-base
  endpoint `/openai/deployments/gpt-4o`, and resolved model `gpt-4o-2024-11-20`
- `make ask-live ... LIVE_PROVIDER=azure-openai`: passed as a live round trip
- `make ask-live ... LIVE_PROVIDER=azure-inference`: passed as a live round trip

## Current Verification Status

Configured and verified in this turn:

- Compile checks: present and passed through `uv run python -m compileall src tests`
- Focused Azure/runtime/CLI utility tests: present and passed through the targeted `uv run pytest`
  slice above
- Required utility pytest slice: present and passed through
  `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- Repository smoke test: present and passed through `uv run repo-rag smoke-test`
- Rust build: present and passed through `cargo build --manifest-path rust-cli/Cargo.toml`
- Lint, notebook lint, mypy, basedpyright, repository-surface verification, complexity, tests, and
  coverage: present and passed through `make quality`
- Live Azure OpenAI probe surface: present and passed through `make azure-openai-probe`
- Live Azure AI Inference probe surface: present and passed through `make azure-inference-probe`
- Live repository-answer surface: present and executed successfully through `make ask-live` for
  both Azure providers

Still absent or not exercised in this turn:

- UI or browser tests: none found in the repository configuration
- Full notebook execution batch: notebook lint and repository-surface checks passed, but
  `make notebook-report` was not rerun end-to-end in this turn
- Post-push GitHub Actions evidence: not yet available before the push for this change set

## Notes

- The new runtime loader accepts either a repo-local `.env` or already-exported process
  environment variables. In this clean worktree, `.env` was intentionally absent, so the live
  Azure commands were verified by exporting `/home/standard/dspy_rag_in_repo_docs_and_impl1/.env`
  into the process environment first.
- The new `make ask-live` surface successfully reaches both Azure providers, but the quality of the
  returned answer is still constrained by the baseline lexical retriever. For the repository-scope
  question used here, both providers responded conservatively that the retrieved evidence did not
  explicitly answer the question, even though the baseline smoke test still confirms the local
  workflow can surface `repository` in its answer text.
- The documentation now matches the code: the repo exposes `ask-live`, `azure-openai-probe`, and
  `azure-inference-probe` through both `make` and `repo-rag`, and the Azure AI Inference endpoint
  normalization is handled inside the package rather than only in ad hoc probe scripts.
