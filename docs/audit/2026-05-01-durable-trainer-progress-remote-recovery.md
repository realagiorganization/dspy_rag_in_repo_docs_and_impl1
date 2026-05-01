# Durable Trainer Progress Remote Recovery

- Date: `2026-05-01`
- Scope: make trainer-side DSPy compile inputs recoverable after PVC loss by rebuilding from the
  Azure processed-trace ledger instead of trusting only local `artifacts/trainer/*.yaml`
- Preceding note: `2026-05-01-versioned-trainer-lineage-bundles.md`

## Summary

Trainer-side progress for future DSPy recompilation is no longer limited to the trainer PVC.

The queue drain path already persisted worker traces into Azure under:

- `queued/<queue>/...` while items were awaiting trainer drain
- `processed/<queue>/...` after successful trainer import

But the previous trainer cycle still materialized the next compile input primarily from local
state:

- `artifacts/traces/imported/*.json`
- `artifacts/trainer/training-candidates.yaml`
- `artifacts/trainer/generated-training.yaml`

That meant a dead PVC could still wipe the accumulated input set used to build the next DSPy
program, even though earlier queue items remained partially represented in Azure.

The current code changes that behavior:

- trainer-cycle now restores a deterministic local trace ledger from Azure
  `processed/<queue>/...` blobs before candidate materialization
- candidate materialization now rebuilds from that recovered ledger instead of seeding from the
  prior local candidate snapshot
- generated training examples remain a derived artifact, not the only surviving copy of progress

Operational consequence:

- if the trainer PVC dies, a new trainer instance can rebuild the compile input set for the next
  DSPy program from the Azure processed-trace ledger
- the PVC is now a cache/work directory for trainer execution, not the only durable source of
  training progress

## Code Changes

- `src/repo_rag_lab/runtime_artifacts.py`
  - adds `DEFAULT_TRAINER_RECOVERED_TRACES_DIR`
  - factors trace-record construction through `_build_trace_record(...)`
  - adds `restore_processed_trace_records(...)`, which mirrors Azure
    `processed/<queue>/...` blobs into a deterministic local recovered-trace ledger

- `src/repo_rag_lab/utilities.py`
  - `run_trainer_cycle(...)` now calls `restore_processed_trace_records(...)` before
    `materialize_training_candidates(...)`
  - trainer cycle now materializes candidates from the recovered trace ledger rather than from only
    newly drained local imported files
  - cycle payloads now expose `durable_trace_recovery` so recovery state is visible in history and
    diagnostics

- `src/repo_rag_lab/training_samples.py`
  - `materialize_training_candidates(...)` now supports `seed_existing_output=False`
  - trainer-cycle uses that mode so candidate rebuilds are driven by the recovered trace ledger,
    not by an opaque surviving YAML snapshot

## What This Fix Guarantees

- queue-drained trace payloads already stored in Azure processed blobs are sufficient to rebuild
  the trainer-side candidate set for future DSPy recompilation
- losing `training-candidates.yaml`, `generated-training.yaml`, or the imported-trace mirror on PVC
  no longer implies losing the underlying training progress
- the trainer-side compile dataset is now recoverable from remote state rather than only from local
  state

## What This Fix Does Not Guarantee Yet

- it does not turn every trainer artifact into a remote canonical record; `service-state.json`,
  cycle history JSON, and local generated YAML remain convenience/state surfaces on PVC
- it does not yet prove, through a fresh live AKS trainer restart, that the deployed service has
  exercised this recovery path end-to-end

## Verification Commands

Repository-native checks executed in this turn:

- `uv run python -m compileall src tests` — `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — `40 passed`
- `uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`

Targeted trainer/recovery suites executed in this turn:

- `uv run pytest tests/test_runtime_artifacts_azure.py tests/test_utilities.py -q` — `43 passed`
- `uv run pytest tests/test_dspy_training.py tests/test_training_samples.py tests/test_cli_and_dspy.py tests/test_project_surfaces.py -q`
  — `83 passed`

Surface sync and publication checks executed in this turn:

- `make files-sync` — `pass`
- `make exploratorium-sync` — `pass`
- `make verify-surfaces` — `pass`
- `uv run pytest tests/test_project_surfaces.py -q` — `21 passed`

## Verification Categories Not Exercised In This Turn

- linting: no dedicated lint command was run
- type checking: no dedicated type-check command was run
- coverage: no coverage command was run
- notebook execution: no notebook execution suite was run
- live AKS recovery drill: not re-run in this turn

## Remaining Gaps

1. Run a live trainer restart or fresh trainer pod against existing Azure `processed/...` blobs and
   confirm that the next cycle rebuilds candidates without needing the old PVC.
2. Decide whether `service-state.json` and cycle history should also be mirrored remotely for
   operator recovery, even though they are not now required for DSPy compile progress itself.
