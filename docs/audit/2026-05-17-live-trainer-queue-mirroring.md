# 2026-05-17 Live Trainer Queue Mirroring

- Scope: inspect the newest live `execution-artifacts` run, verify whether trainer consumed and
  published all new traces, and repair the queue-surface bug that left Azure-backed runs without a
  local `queued` mirror on the trainer PVC.
- Preceding note: `2026-05-17-ci-and-dataset-repair.md`

## Live Evidence

- Latest successful pipeline run inspected: GitHub Actions `25986469008`, completed
  `2026-05-17 08:57:31 UTC`.
- Matching blob artifact run downloaded:
  `execution-artifacts/executions/25986469008_20260517_091602/...`.
- Worker artifact evidence:
  - `repo_rag_turn_trace_batch_manifest.json` reported `12` trace paths in batch
    `20260517T090849Z`.
  - `trusted_trace_handoff_summary.json` reported `skipped=1` with
    `worker-backend-handoff-already-succeeded`.
  - `repo_rag_codex_proxy_last.json` still showed `dspy_status="skipped"` and
    `prompt_family_id=null`, so runtime family reuse did not happen in this run.
- Live blob evidence:
  - `repo-rag-training-traces/batches/20260517T090849Z/` contained `12` blobs.
  - `repo-rag-training-traces/processed/repo-rag-training/20260517...` gained the same `12`
    blobs.
  - `repo-rag-training-traces/queued/repo-rag-training/` was empty by the time of inspection.
  - `repo-rag-training-families` contained `0` blobs.
  - `repo-rag-bundles` contained `0` blobs.
- Live Kubernetes evidence:
  - recent `repo-rag-trainer-cycle-*` pods were `Completed`, not still running
  - their logs showed no-op cycles with `queued_count_before=0`, `drained_count=0`,
    `candidate_count=0`, `publish_requested=false`, and
    `pending_recompile.reason="missing-family-state"`
  - a debug pod mounted to `repo-rag-trainer-artifacts` showed:
    - `artifacts/traces/imported/` contained the `12` new imported trace records
    - `artifacts/trainer/recovered-imported-traces/` still held older processed-history copies
    - `artifacts/traces/queued/` did not exist at all
    - `artifacts/trainer/family-state.json`,
      `artifacts/trainer/training-candidates.yaml`, and
      `artifacts/dspy/channels/stable.json` were all missing

## Root Cause Split

### Confirmed queue-surface bug

- Under the Azure Blob + Queue backend, `queue_trace_record(...)` uploaded the queued item to the
  remote blob container and queue, but it did not mirror the same queued payload into the local
  PVC under `artifacts/traces/queued/...`.
- The same gap affected batch mirrors: remote `batches/...` blobs existed, while local
  `artifacts/traces/batches/...` was absent.
- This violated the repo-local queue contract and removed a crucial debugging/audit surface even
  when remote Azure transport worked.

### Separate live deployment drift

- The current repository source reproduces the live `12` imported traces successfully:
  `materialize_training_candidates(...)` on the copied live payloads created
  `artifacts/trainer/family-state.json`, `training-candidates.yaml`, and a `9`-family summary
  locally without errors.
- That means the cluster symptom "`processed` traces exist but trainer outputs do not" is not
  reproducible on the current `HEAD`.
- The remaining live gap is therefore operational drift: the AKS runtime image
  `llmpromptsacr.azurecr.io/repo-rag-runtime:20260517-084100` is lagging the current source-level
  trainer fixes, so a redeploy with the updated repository image/submodule is still required.

## Source Fixes Landed

- `src/repo_rag_lab/runtime_artifacts.py`
  - Azure-backed `queue_trace_record(...)` now always writes one local queued mirror under
    `artifacts/traces/queued/<queue>/...` before uploading the remote blob/queue item.
  - Azure-backed batched trace handoff now also writes one local batch mirror under
    `artifacts/traces/batches/<batch>/...` before uploading the remote batch blob.
  - The Azure return payload now reports `local_queue_item_path` and `local_batch_trace_path` so
    verification and downstream callers can assert both local and remote artifacts.
- `tests/test_runtime_artifacts_azure.py`
  - added regression coverage that the Azure queue path creates those local queued/batch mirrors
    while preserving the remote blob/queue behavior.

## Verification

Checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_runtime_artifacts_azure.py tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — `pass` (`79 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`
- `make quality` — `pass` (`366 passed`, `3 skipped`, coverage `81.38%`)
- `UV_CACHE_DIR=/tmp/uvcache uv run python - <<'PY' ... materialize_training_candidates(...) ... PY`
  on copied live PVC traces — `pass`
  - input traces: `12`
  - loaded candidates: `12`
  - family candidate count: `12`
  - materialized family count: `9`

Checks not executed in this turn:

- No fresh post-fix AKS pipeline run has been observed yet with the updated repository image.
- No fresh remote publish into `repo-rag-training-families` / `repo-rag-bundles` has been
  observed yet after the code repair, because the running cluster image is still behind the
  current source tree.

## Current Status

- The missing local `queued` / `batches` mirror is now fixed in source and covered by tests.
- The current source tree can materialize the live `12` imported traces into family state
  correctly.
- The remaining live failure is deployment drift, not an unreproduced source-level trainer logic
  bug: the cluster must be redeployed with the updated runtime image before a new run can confirm
  remote `repo-rag-training-families` and `repo-rag-bundles` publication again.
