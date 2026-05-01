# DSPY Bundle Version Pinning Contract

- Date: `2026-05-01`
- Scope: switch the downstream worker/runtime contract from channel-first bundle lookup to
  explicit immutable bundle-version pinning through `DSPY_BUNDLE_VERSION`, while keeping
  `stable` / `canary` channel resolution as a compatibility fallback
- Preceding note: `2026-05-01-aks-run-25226558751-rag-heuristic-trusted-handoff.md`

## Summary

The repo-RAG trainer/runtime surface now treats timestamped immutable bundle versions such as
`20260501T135609Z` as the primary runtime artifact identity, and the downstream `dataset`
deployment now propagates one explicit deployment-wide pin through `DSPY_BUNDLE_VERSION`.

That closes the gap where:

- trainer-side publishes were already creating immutable bundle directories under
  `versions/<bundle_version>/...`
- workers were still defaulting to `bundle-inspect --channel stable`
- missing `channels/stable.json` left workers in heuristic DSPy fallback even when a valid bundle
  already existed in Azure Blob storage

With this contract:

- trainer-side recompilation now continues to mint timestamp-only immutable bundle versions
- deployments pin one exact bundle version through `DSPY_BUNDLE_VERSION`
- prompt-level `bundle_version` remains the strongest one-off override
- `DATASET_REPO_RAG_BUNDLE_CHANNEL` and `stable` / `canary` remain optional fallback and rollback
  surfaces rather than the primary worker lookup path

## Code And Documentation Changes

Current repository:

- `src/repo_rag_lab/utilities.py`
  - `_versioned_training_run_name(...)` now returns timestamp-only immutable bundle versions
    instead of prefixing the trainer family into the storage key
  - utility-summary bundle wording now describes immutable versions plus optional channel aliases
- `tests/test_utilities.py`
  - regression coverage now expects timestamp-only trainer publish versions
- `docs/architecture/research-narrative.md`
  - documents `DSPY_BUNDLE_VERSION` as the primary worker-side runtime selector
- `docs/planning/dataset-integration-plan.md`
  - updates the dataset integration story to explicit version pinning with channel fallback
- `docs/operations/trainer-deployment.md`
  - records immutable `versions/<timestamp>/` artifacts plus deployment-time pinning semantics
- `README.md`
  - updates `bundle-fetch` guidance to explicit `BUNDLE_VERSION=<timestamp_version>` usage

Downstream `../dataset` repository:

- `.github/workflows/parallel-prompt-execution-aks.yml`
  - now forwards `vars.DSPY_BUNDLE_VERSION` into workflow env
- `aks_module_generator/mixins/base.py`
  - now records `DSPY_BUNDLE_VERSION` during module generation
- `aks_module_generator/mixins/k8s_manifests.py`
  - now propagates `DSPY_BUNDLE_VERSION` and `DATASET_REPO_RAG_BUNDLE_VERSION` into worker pod env
- `docker/prompt-executor/worker_execution_prompt.py`
  - now resolves explicit bundle pins through `prompt_meta.bundle_version`, then
    `DSPY_BUNDLE_VERSION`, then the compatibility alias before attempting channel lookup
- `src/execution/prompt_executor.py`
  - mirrors the same precedence for the local compatibility executor
- `README.md`, `USAGE.md`, and `agents.md`
  - now describe `DSPY_BUNDLE_VERSION` as the primary runtime bundle selector
- targeted tests now verify:
  - workers skip `bundle-inspect` when `DSPY_BUNDLE_VERSION` is set
  - the local compatibility executor does the same
  - AKS manifests include the explicit bundle pin in pod env

## Verification Commands

Current repository checks executed in this turn:

- `uv run python -m compileall src tests` — `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — `40 passed`
- `uv run pytest tests/test_project_surfaces.py -q` — `21 passed`
- `uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`

Downstream `dataset` checks executed in this turn:

- `python -m compileall docker/prompt-executor src/execution aks_module_generator tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/unit/test_prompt_executor_repo_rag_cli.py tests/test_aks_module_generator_manifests.py`
  — `pass`
- `uv run pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/unit/test_prompt_executor_repo_rag_cli.py tests/test_aks_module_generator_manifests.py -q`
  — `43 passed`

Repository surface sync executed in this turn:

- `make files-sync` — `pass`
- `make verify-surfaces` — `pass`

## What Is Confirmed

- trainer-side immutable bundle versions now use timestamp-only storage keys
- downstream workers can be pinned directly to one immutable bundle version through
  `DSPY_BUNDLE_VERSION`
- channel lookups are no longer required for the normal “one global bundle for every worker”
  deployment model
- prompt-level bundle-version overrides still work and remain stronger than deployment env
- bundle channels remain available for optional aliasing, promotion, and rollback instead of being
  removed outright

## Verification Categories Not Exercised In This Turn

- linting: no dedicated lint command was run
- type checking: no dedicated type-check command was run
- coverage: no coverage command was run
- notebook execution: no notebook execution suite was run
- live AKS deployment validation: not re-run in this turn
- GitHub Actions post-push validation: not applicable because no push happened in this turn

## Remaining Gaps

1. Run one fresh trainer publish and one fresh worker deployment with a real non-placeholder
   `DSPY_BUNDLE_VERSION` to confirm end-to-end live bundle consumption in AKS.
2. Decide whether `stable` / `canary` should remain manual operational aliases or whether the
   trainer should auto-promote a newly published bundle after gates pass.
