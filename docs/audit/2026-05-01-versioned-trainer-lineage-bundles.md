# Versioned Trainer Lineage Bundles

- Date: `2026-05-01`
- Scope: make trainer-side DSPy recompilation publish immutable bundle versions with explicit
  lineage metadata instead of overwriting one mutable `trainer-auto` bundle record
- Preceding note: `2026-05-01-live-trainer-remote-bundle-publish.md`

## Summary

The trainer compile/publish path now models `TRAINER_RECOMPILE_RUN_NAME` as a run family rather
than a storage key. Each successful trainer-side recompilation mints a unique timestamped bundle
version such as `trainer-auto-20260501T170000Z`, records the imported trace paths plus candidate
dedupe counters into bundle lineage metadata, and publishes that immutable version as the bundle
artifact that later channel promotion and rollback target.

This closes the semantic gap where:

- multiple successful recompiles could previously refresh the same `trainer-auto` bundle version
- channel promotion could appear versioned while trainer-side recompilation still reused one
  mutable bundle key
- global trainer history could not state exactly which trace items and candidate-materialization
  pass produced a given published bundle

The candidate accumulation path remains incremental and deduplicated:

- imported traces still materialize through `artifacts/trainer/training-candidates.yaml`
- duplicate examples are suppressed by normalized candidate keys
- replacement counts stay visible when a new candidate supersedes the prior record for the same
  question
- the generated compile input under `artifacts/trainer/generated-training.yaml` still merges base
  examples plus deduped candidates before DSPy recompilation

## Code Changes

Trainer-side versioning and lineage:

- `src/repo_rag_lab/utilities.py`
  - adds `_sanitize_training_run_name(...)`
  - adds `_versioned_training_run_name(...)`
  - `run_trainer_cycle(...)` now derives a unique resolved run/bundle version per successful
    recompile while preserving the requested run family
  - `run_trainer_cycle(...)` now records imported trace paths, candidate counts, duplicate counts,
    and replacement counts into `lineage_metadata`
  - `_trainer_recompile_payload(...)` now forwards `bundle_version`, `run_family`, and
    `lineage_metadata`

- `src/repo_rag_lab/dspy_training.py`
  - `DSPyTrainingConfig` now accepts `bundle_version`, `run_family`, and `lineage_metadata`
  - `train_repository_program(...)` now persists those fields into DSPy metadata
  - `DSPyTrainingResult` now returns `run_family` and `lineage_metadata`

- `src/repo_rag_lab/runtime_artifacts.py`
  - `build_bundle_manifest(...)` now honors an explicit metadata `bundle_version`
  - bundle manifests now persist `run_family` and `lineage`

Resulting repository contract:

- `trainer-auto` becomes a family label, not the published artifact key
- every successful recompilation publishes one immutable bundle version
- `stable` / `canary` channel state points to a concrete published version
- `bundle-rollback` and `bundle-promote` now operate on those immutable versions instead of a
  repeatedly overwritten trainer alias

## Verification Commands

Repository-native checks executed in this turn:

- `uv run python -m compileall src tests` — `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — `40 passed`
- `uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`

Targeted suites executed in this turn for the new semantics:

- `uv run pytest tests/test_dspy_training.py tests/test_utilities.py -q` — `59 passed`
- `uv run pytest tests/test_runtime_artifacts_azure.py tests/test_training_samples.py tests/test_cli_and_dspy.py -q`
  — `45 passed`

Surface sync and publication checks executed in this turn:

- `make files-sync` — `pass`
- `make exploratorium-sync` — `pass`
- `make verify-surfaces` — `pass`
- `uv run pytest tests/test_project_surfaces.py -q` — `21 passed`

## What Is Confirmed

- trainer recompilation no longer has to publish back into one mutable `trainer-auto` bundle
  version
- bundle manifests now preserve the distinction between:
  - `run_name`: the unique compile instance
  - `run_family`: the logical trainer stream such as `trainer-auto`
  - `bundle_version`: the immutable published version used by channel promotion and rollback
- lineage metadata is now available directly in bundle metadata instead of only in separate trainer
  history JSON
- incremental candidate accumulation still deduplicates examples before compile input generation

## What Is Not Yet Revalidated Live

- no fresh AKS trainer cycle was run in this turn to prove the new unique version names are being
  published into the live `repo-rag-bundles` container
- no fresh worker-side AKS run was executed in this turn to prove later workers resolve one of the
  newly versioned stable/canary channel pointers end-to-end

## Verification Categories Not Exercised In This Turn

- linting: no dedicated lint command was run
- type checking: no dedicated type-check command was run
- coverage: no coverage command was run
- notebook execution: no notebook execution suite was run
- browser/UI validation: no UI surface exists for this trainer-only change
- live AKS deployment validation: not re-run in this turn

## Remaining Gaps

1. Run one fresh trainer cycle in AKS after new queue items arrive and confirm that the remote
   bundle container now receives a new immutable version path rather than another refresh of
   `versions/trainer-auto/...`.
2. Revalidate worker-side bundle consumption against a promoted `stable` or `canary` pointer that
   references one of those newly versioned bundles.
3. Decide whether automatic promotion should remain manual or whether
   `TRAINER_PROMOTE_CHANNEL=canary` should become the default trainer-service posture.
