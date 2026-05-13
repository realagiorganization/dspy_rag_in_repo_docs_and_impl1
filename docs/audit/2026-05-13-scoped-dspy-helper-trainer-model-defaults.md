# 2026-05-13 Scoped DSPy Helper/Trainer Model Defaults

## Summary

The repository now splits DSPy model selection into two explicit surfaces:

- `DSPY_HELPER_*` for worker/runtime helper mediation
- `DSPY_TRAINER_*` for trainer-side compile/recompile

Shared `AZURE_OPENAI_*` values remain transport fallback only for Azure-hosted DSPy models and no
longer silently decide which model the helper or trainer uses.

## Effective Defaults

- `DSPY_HELPER_MODEL=azure/gpt-5.4-nano`
- `DSPY_TRAINER_MODEL=azure/gpt-5.4-mini`

Those defaults now live in the repo utility layer, the Makefile environment, the dataset GitHub
Actions workflow, the AKS module generator, and the trainer deploy script.

## Code Paths

- `src/repo_rag_lab/codex_proxy.py`
  - helper mediation resolves through `resolve_dspy_helper_lm_config()`
- `src/repo_rag_lab/utilities.py`
  - trainer recompile resolves through `resolve_dspy_trainer_lm_config()`
- `src/repo_rag_lab/cli.py`
  - `ask --use-dspy` resolves helper scope
  - `dspy-train`, `trainer-recompile`, `trainer-cycle`, and `trainer-service` resolve trainer scope
- `../dataset/.github/workflows/parallel-prompt-execution-aks.yml`
  - publishes scoped helper/trainer env vars into AKS jobs
- `../dataset/deploy_repo_rag_trainer.sh`
  - writes scoped helper/trainer literals into the trainer runtime secret
- `../dataset/aks_module_generator/mixins/base.py`
  - loads scoped helper/trainer settings with `nano` / `mini` defaults
- `../dataset/aks_module_generator/mixins/k8s_manifests.py`
  - injects scoped helper/trainer env vars and API-key secret references into worker pods
- `../dataset/aks_module_generator/mixins/secrets.py`
  - stores `DSPY_HELPER_API_KEY` and `DSPY_TRAINER_API_KEY`

## Validation

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_dspy_training.py tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_cli_and_dspy.py -q`
- `cd ../dataset && pytest tests/test_aks_module_generator_manifests.py tests/test_aks_module_generator_generate_modules.py tests/unit/test_deploy_repo_rag_trainer_script.py -q`
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

## Notes

- `CODEX_AZURE_CONFIG` remains separate and continues to control `codex exec` model selection
  alongside `model_hint`.
- Legacy shared `DSPY_MODEL` / `DSPY_API_*` support remains only as compatibility fallback for
  existing callers; the intended active contract is scoped helper/trainer env vars.
