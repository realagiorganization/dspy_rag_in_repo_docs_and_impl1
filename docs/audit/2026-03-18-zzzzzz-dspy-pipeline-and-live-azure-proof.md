# DSPy Pipeline And Live Azure Proof

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Verification worktree: `/tmp/repo-rag-step2.kDs6IY`
- Shared repository source for env loading: `/home/standard/dspy_rag_in_repo_docs_and_impl1`
- Previous audit anchor: `2026-03-18-repository-benchmark-broadening.md`

## Scope

This audit records two linked outcomes:

- the DSPy scaffolding is now a stronger repository-native compile-and-reuse workflow
- the Azure OpenAI runtime path is proven live through the repo-native probe and ask surfaces

The code changes in this turn add a first-class `dspy-artifacts` surface, make the DSPy runtime
auto-resolve the latest compiled program when no explicit program path is supplied, and document
that behavior across the repo narrative and operator docs.

## Executed Commands

Executed successfully in this turn:

- `uv run ruff format src/repo_rag_lab/dspy_training.py src/repo_rag_lab/dspy_workflow.py src/repo_rag_lab/utilities.py src/repo_rag_lab/cli.py src/repo_rag_lab/verification.py tests/test_dspy_training.py tests/test_cli_and_dspy.py tests/test_project_surfaces.py tests/test_utilities.py tests/test_verification.py`
- `uv run pytest tests/test_dspy_training.py tests/test_cli_and_dspy.py tests/test_utilities.py tests/test_verification.py tests/test_project_surfaces.py`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make verify-surfaces`
- `make hooks-install`
- `set -a; source /home/standard/dspy_rag_in_repo_docs_and_impl1/.env; set +a; make dspy-train DSPY_RUN_NAME=step2-live-compile DSPY_MAX_BOOTSTRAPPED_DEMOS=1 DSPY_MAX_LABELED_DEMOS=1`
- `set -a; source /home/standard/dspy_rag_in_repo_docs_and_impl1/.env; set +a; make dspy-artifacts`
- `set -a; source /home/standard/dspy_rag_in_repo_docs_and_impl1/.env; set +a; make ask-dspy QUESTION="What does this repository research?"`
- `set -a; source /home/standard/dspy_rag_in_repo_docs_and_impl1/.env; set +a; make azure-openai-probe RUNTIME_LOAD_ENV_FILE=0`
- `set -a; source /home/standard/dspy_rag_in_repo_docs_and_impl1/.env; set +a; make ask-live QUESTION="What does this repository research?" LIVE_PROVIDER=azure-openai RUNTIME_LOAD_ENV_FILE=0`
- `make quality`

## Results

- focused DSPy/CLI/utilities/surface tests: passed, `61 passed in 16.09s`
- `uv run python -m compileall src tests`: passed
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`: passed, `14 passed in 11.91s`
- `uv run repo-rag smoke-test`: passed with:
  - `answer_contains_repository: true`
  - `mcp_candidate_count: 1`
  - `manifest_path: artifacts/azure/repo-rag-smoke.json`
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `make verify-surfaces`: passed with `issue_count: 0`
- `make hooks-install`: passed
- live DSPy compile: passed and wrote:
  - `artifact_dir: artifacts/dspy/step2-live-compile`
  - `program_path: artifacts/dspy/step2-live-compile/program.json`
  - `metadata_path: artifacts/dspy/step2-live-compile/metadata.json`
  - `training_example_count: 8`
  - `optimizer: bootstrapfewshot`
  - `lm_model: azure/gpt-4o`
  - `benchmark_summary.pass_rate: 0.625`
- `make dspy-artifacts`: passed and reported:
  - `run_count: 1`
  - `latest_run_name: step2-live-compile`
  - `latest_program_path: artifacts/dspy/step2-live-compile/program.json`
  - `program_exists: true`
- `make ask-dspy QUESTION="What does this repository research?"`: passed without an explicit
  `DSPY_PROGRAM_PATH` and returned:
  - `This repository researches repository-grounded Retrieval-Augmented Generation (RAG), focusing on integration, optimization, and evaluations tied to repository-specific corpora.`
- `make azure-openai-probe RUNTIME_LOAD_ENV_FILE=0`: passed with:
  - `provider: azure-openai`
  - `status: success`
  - `reply: OPENAI_OK`
  - `model: gpt-4o-2024-11-20`
  - `endpoint: https://gpt45standard.openai.azure.com`
  - `deployment_name: gpt-4o`
  - `api_version: 2025-01-01-preview`
  - `env_file_found: false`
  - `loaded_env_keys: []`
- `make ask-live ... LIVE_PROVIDER=azure-openai RUNTIME_LOAD_ENV_FILE=0`: passed and produced a
  live Azure-backed answer grounded in retrieved repository evidence
- `make quality`: passed with `124 passed in 93.25s` and total coverage `87.99%`

## Current Verification Status

Configured and exercised in this turn:

- compile checks
- lint and notebook lint checks
- type checking through `mypy` and `basedpyright`
- repository surface verification
- focused DSPy/CLI/utilities/project-surface pytest coverage
- full repository pytest coverage gate
- Rust wrapper build
- DSPy compile-save-reuse flow with a live Azure-backed LM
- DSPy artifact inventory reporting
- live Azure OpenAI runtime contract probe
- live repository ask path through Azure OpenAI

Not exercised in this turn:

- Azure AI Inference live probe
- full notebook batch execution
- publication PDF build
- post-push GitHub Actions evidence for this head

## Notes

- The verification worktree did not contain a local `.env`, so the live DSPy and Azure runs used
  environment variables sourced from the shared checkout at
  `/home/standard/dspy_rag_in_repo_docs_and_impl1/.env`. That is why the Azure probe reports
  `env_file_found: false` and `loaded_env_keys: []` while still succeeding.
- The first full `make quality` pass failed after the live DSPy compile because
  `tests/test_cli_and_dspy.py::test_repository_rag_skips_program_without_configuration` assumed the
  repository had no compiled DSPy artifact. This turn fixes that test to pin the no-artifact case
  explicitly instead of depending on ambient repo state.
- The live DSPy benchmark result is useful but not perfect: `pass_rate: 0.625` confirms the
  compile pipeline works with the configured model, while also reinforcing the repo’s existing
  narrative that retrieval quality and benchmark design remain the main bottlenecks.
