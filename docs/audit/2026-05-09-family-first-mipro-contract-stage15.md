# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 15

## Scope

- Remove champion-named container-env emission from dataset / AKS deploy surfaces.
- Keep champion-named env handling only as repo-side compatibility fallback input.

## Contract status in this turn

The deploy-facing family-state contract is now stricter:

1. Dataset-side repo-rag storage secrets now emit only family-state container env vars.
2. Trainer deploy bootstrap no longer exports or injects champion-named container env vars into
   generated secrets.
3. Generated deployment-script templates now resolve and publish only
   `REPO_RAG_FAMILY_STATE_CONTAINER` / `DATASET_REPO_RAG_FAMILY_STATE_CONTAINER`.

This narrows the remaining `champion_*` compatibility layer to repo-side readers and older local
state aliases instead of continuing to publish champion naming as live deployment truth.

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Dataset deploy/bootstrap surfaces:
  - `../dataset/aks_module_generator/mixins/secrets.py`
  - `../dataset/deploy_repo_rag_trainer.sh`
  - `../dataset/aks_module_generator/templates/deployment_script/part_1.txt`
  - `../dataset/aks_module_generator/templates/deployment_script/part_4.txt`
- Dataset tests:
  - `../dataset/tests/test_aks_module_generator_manifests.py`
  - `../dataset/tests/unit/test_deploy_repo_rag_trainer_script.py`

## What is implemented now

### 1. Dataset storage secrets are family-state only

Generated repo-rag storage secrets now include:

- `DATASET_REPO_RAG_FAMILY_STATE_CONTAINER`
- `REPO_RAG_FAMILY_STATE_CONTAINER`

and no longer publish:

- `DATASET_REPO_RAG_CHAMPION_CONTAINER`
- `REPO_RAG_CHAMPION_CONTAINER`

### 2. Trainer deploy bootstrap no longer exports champion container env vars

The trainer deployment script now defaults only the family-state container contract and injects
only family-state container literals into the runtime secret.

### 3. Generated deployment-script templates match the same contract

The generated deployment-script templates now resolve the family-state container from family-state
env vars only and stop exporting champion-named container env aliases during script generation.

### 4. Compatibility is preserved only on the reader side

Repo-side runtime/config resolution still accepts champion-named env vars as fallback inputs, but
the deployment/bootstrap layer no longer republishes them.

## What is not implemented yet

- repo-side compatibility `champion_*` env-var fallbacks and state aliases still exist
- aggregate `family-state.json` is still mirrored beside the newer per-family replay-set layout
- live AKS validation of the new deploy contract and full family-first trainer loop has not been
  run in this turn
- notebook execution, coverage, UI/browser verification, and live deployment validation were not
  run in this turn

## Verification executed in this turn

Targeted dataset checks executed in this turn:

- `cd ../dataset && pytest tests/test_aks_module_generator_manifests.py tests/test_aks_module_generator_generate_modules.py tests/unit/test_deploy_repo_rag_trainer_script.py -q`
  - `pass` (`75 passed`)
- `cd ../dataset && python -m compileall aks_module_generator/mixins/secrets.py aks_module_generator/templates/deployment_script/part_1.txt aks_module_generator/templates/deployment_script/part_4.txt deploy_repo_rag_trainer.sh tests/test_aks_module_generator_manifests.py tests/unit/test_deploy_repo_rag_trainer_script.py`
  - `pass`

Repository-native checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`45 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`
- `make files-sync`
  - `pass`
- `make exploratorium-sync`
  - `pass`
- `make verify-surfaces`
  - `pass`

## Current conclusion

The family-first contract is now the only deploy/bootstrap contract for the repo-rag family-state
container:

- deployment secrets no longer emit champion container aliases
- trainer bootstrap scripts no longer export champion container aliases
- generated deployment templates no longer regenerate champion container aliases

The remaining compatibility layer is now narrower and more explicit: champion naming still exists
only where the repo must read older state or older env names, not where new AKS deployments are
defined.
