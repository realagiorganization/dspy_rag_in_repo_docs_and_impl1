# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 8

## Scope

- Propagate the new family-state container contract through dataset / AKS deployment wiring.
- Keep champion-named env aliases mirrored to the same container value so rollout compatibility is
  preserved.

## Contract status in this turn

The repository now advances the family-first contract in one more practical way:

1. Dataset-side workflow env now exposes `REPO_RAG_FAMILY_STATE_CONTAINER` and
   `DATASET_REPO_RAG_FAMILY_STATE_CONTAINER` as first-class deployment inputs.
2. Dataset-side storage-secret generation now exports both family-state and champion alias env keys
   to the same value, alongside the existing trace/bundle/queue settings.
3. The trainer deploy bootstrap now creates the family-state blob container and injects the same
   primary + alias env values into the runtime secret.
4. The generated deployment-script templates and `.env.example` now document the same contract.

This means the new family-state storage contract is no longer trapped inside the repo-rag codebase;
it now has a deployment path into AKS as well.

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Dataset / AKS deployment wiring:
  - `../dataset/.github/workflows/parallel-prompt-execution-aks.yml`
  - `../dataset/.env.example`
  - `../dataset/deploy_repo_rag_trainer.sh`
  - `../dataset/aks_module_generator/mixins/base.py`
  - `../dataset/aks_module_generator/mixins/secrets.py`
  - `../dataset/aks_module_generator/templates/deployment_script/part_1.txt`
  - `../dataset/aks_module_generator/templates/deployment_script/part_4.txt`
- Dataset tests:
  - `../dataset/tests/test_aks_module_generator_manifests.py`
  - `../dataset/tests/unit/test_deploy_repo_rag_trainer_script.py`

## What is implemented now

### 1. Family-state env propagation in dataset / AKS wiring

The AKS workflow and deploy scripts now propagate:

- `DATASET_REPO_RAG_FAMILY_STATE_CONTAINER`
- `REPO_RAG_FAMILY_STATE_CONTAINER`

as primary storage inputs.

### 2. Champion alias env mirroring

The same deployment surfaces now mirror:

- `DATASET_REPO_RAG_CHAMPION_CONTAINER`
- `REPO_RAG_CHAMPION_CONTAINER`

to the same family-state container value so older code paths remain compatible during the rollout.

### 3. Family-state container bootstrap

Trainer deployment bootstrap now creates the primary family-state blob container in Azure Storage
alongside the existing trace and bundle containers.

## What is not implemented yet

- the remote family container still does not store full replay-set traces per family
- the global compile-facing DSPy program still recompiles from the merged dataset even when only a
  subset of families changed
- post-run traces still do not carry the final real execution `hits / total`
- live AKS verification of the new family-state env/container handoff still has not been run
- complete removal of champion alias naming from repo and dataset wiring has not happened yet

## Verification executed in this turn

Dataset-side checks executed in this turn:

- `cd ../dataset && pytest tests/test_aks_module_generator_manifests.py tests/test_aks_module_generator_generate_modules.py tests/unit/test_deploy_repo_rag_trainer_script.py -q`
  - `pass` (`75 passed`)
- `python -m compileall ../dataset/aks_module_generator/mixins/base.py ../dataset/aks_module_generator/mixins/secrets.py ../dataset/deploy_repo_rag_trainer.sh ../dataset/tests/test_aks_module_generator_manifests.py ../dataset/tests/unit/test_deploy_repo_rag_trainer_script.py`
  - `pass`

Repository-native baseline checks executed for the repo-rag side after documenting this stage:

- `make files-sync`
  - `pass`
- `make exploratorium-sync`
  - `pass`
- `make verify-surfaces`
  - `pass`

Verification categories still not covered in this turn:

- live deployment / AKS validation: not run in this turn
- notebook execution: not run in this turn
- coverage: not run in this turn
- UI / browser verification: not applicable in-repo and not run

## Current conclusion

The family-state container contract now has code-level support on both sides of the handoff:

- repo-rag runtime / trainer
- dataset / AKS deployment wiring

The remaining deployment gap is not naming anymore; it is live rollout and validation.
