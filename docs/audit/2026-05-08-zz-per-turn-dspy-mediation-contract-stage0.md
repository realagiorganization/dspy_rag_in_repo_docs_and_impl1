# Repository audit note for 2026-05-08 per-turn DSPy mediation contract stage 0

## Scope

- Align the repository and `../dataset` worker path with the user-defined per-turn DSPy runtime contract.
- Record concrete local verification for the new prompt-reformulation, command-trace, batch-trace, champion, and bundle surfaces.

## Contract status in this turn

The repository now matches the requested stage-0 contract substantially more closely:

1. `codex exec` remains the orchestrator.
2. The proxy intercepts each outbound `Responses` request, extracts the visible turn state, and treats the current turn uniformly whether it originated from the user or from the model's prior loop output.
3. The runtime now records both:
   - `original_prompt`
   - `reformulated_prompt`
4. The runtime also records `command_trace` as a first-class field in turn traces, candidate materialization, champion state, and compile-facing training data.
5. Per-turn proxy traces accumulate locally under one worker batch directory and are handed off together after the `codex exec` run completes.
6. Batch handoff now propagates `batch_name` into queueing, so the trace store mirrors those queued turn traces under `repo-rag-training-traces/batches/<timestamp>/...` in addition to the normal queue path.
7. Trainer-side prompt-family handling stays on the user-specified active thresholds:
   - `0.8` => direct family replacement gate
   - `0.6` => soft-family band
8. The active runtime/trainer metric path is the requested `hits / total` form, with no additional weighted ranking coefficients introduced in this turn.

## Repo-side implementation surfaces

- New contract/planning source:
  - `docs/planning/per-turn-dspy-mediation-contract.md`
- Updated architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Proxy/runtime/trainer changes:
  - `src/repo_rag_lab/codex_proxy.py`
  - `src/repo_rag_lab/runtime_artifacts.py`
  - `src/repo_rag_lab/training_samples.py`
  - `src/repo_rag_lab/utilities.py`
  - `src/repo_rag_lab/cli.py`
  - `src/repo_rag_lab/azure_artifacts.py`

## Dataset-side implementation surfaces

- Worker batch handoff and queue mirror support:
  - `../dataset/docker/prompt-executor/worker_execution_prompt.py`
  - `../dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py`

## Verification executed in this turn

Repository checks executed in this turn:

- `make files-sync`
  - `pass`
- `make verify-surfaces`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_runtime_artifacts_azure.py tests/test_utilities.py tests/test_cli_and_dspy.py tests/test_codex_proxy.py tests/test_training_samples.py tests/test_dspy_training.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`143 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`

Dataset checks executed in this turn:

- `python -m compileall /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_execution_prompt.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py`
  - `pass`
- `cd /home/standard/Desktop/realagi_work/dataset && pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py -q`
  - `pass` (`14 passed`)

## Verification categories not executed in this turn

- lint: not run
- type checking: not run
- coverage: not run
- notebook execution: not run
- UI/browser validation: not applicable / not run
- AKS deployment validation: not run
- live Azure blob/queue proof after redeploy: not run

## Current remaining gap

This turn implemented the local code path and the worker/trainer storage contract, but it did not deploy a new live image or rerun the AKS pipeline. So the code now expresses the intended stage-0 per-turn DSPy flow, but live publication behavior in the real cluster is still unverified until one fresh worker run and one fresh trainer cycle are observed after redeploy.

## DSPy helper-model contract

The auxiliary DSPy-model path is now explicit instead of implicit:

1. `resolve_dspy_lm_config()` now treats `DSPY_MODEL` as the primary model selector.
2. When `DSPY_MODEL=azure/...` is set, the runtime still reuses the shared
   `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, and `AZURE_OPENAI_API_VERSION` transport
   values unless `DSPY_API_KEY`, `DSPY_API_BASE`, or `DSPY_API_VERSION` override them.
3. The Codex proxy status payload now records `dspy_lm_model`, so worker artifacts can show which
   helper model actually executed the reformulation + DSPy mediation path.
4. The dataset worker delivery path now propagates `DSPY_MODEL`, `DSPY_API_BASE`,
   `DSPY_API_VERSION`, `DSPY_MODEL_TYPE`, `DSPY_TEMPERATURE`, and `DSPY_MAX_TOKENS` into the pod
   env, and it stores `DSPY_API_KEY` in the `codex-azure-config` secret when present.
5. The dataset AKS GitHub Actions workflow now exports the same `DSPY_*` variables, so the
   helper-model choice can be driven from repository/workflow variables instead of only local
   shell state.

Focused verification for this helper-model contract in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_dspy_training.py tests/test_codex_proxy.py tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`79 passed`)
- `cd /home/standard/Desktop/realagi_work/dataset && pytest tests/test_aks_module_generator_manifests.py tests/test_aks_module_generator_generate_modules.py tests/unit/test_deploy_repo_rag_trainer_script.py -q`
  - `pass` (`75 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`
- `make verify-surfaces`
  - `pass`
