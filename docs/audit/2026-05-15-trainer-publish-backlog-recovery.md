# 2026-05-15 Trainer Publish Backlog Recovery

- Scope: explain and fix the missing remote publish after the latest trainer drain.
- Preceding note: `2026-05-15-trace-wrapper-mirroring-and-batch-summary-fix.md`

## What Changed

- `run_trainer_cycle(...)` no longer abandons pending family-state recompilation just because the
  next cycle happens to be idle.
- A prior cycle could drain/import traces, notice visible queue backlog, and correctly defer
  recompile/publish. The bug was that the first later backlog-free idle cycle still exited through
  the `no-queued-input` fast path before it could finish the pending compile/publish work.
- The trainer now:
  - inspects pending family-state before taking the idle fast path;
  - allows pending recompile to trigger once backlog clears, even with zero newly drained items in
    that later cycle;
  - treats pending family-state as sufficient reason to upload `repo-rag-training-families` after
    compilation finishes.

## Why This Mattered

- Live blob inspection showed the failure mode clearly:
  - `repo-rag-training-traces/processed` had the drained traces;
  - `repo-rag-training-families` was empty;
  - `repo-rag-bundles` was empty.
- That means trainer ingestion happened, but publish never recovered after the initial
  `deferred-queue-backlog` decision.

## Verification

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py -k 'deferred_recompile_and_publish_while_queue_backlog_is_visible or recompiles_and_publishes_pending_family_state_after_backlog_clears or recompiles_pending_family_drift_once_new_traces_arrive or skips_recompile_and_publish_without_new_candidates'`

## Current Status

- Local source verification is green for the backlog-recovery path.
- A new live run is still required to confirm that the next backlog-free trainer cycle now uploads
  both remote family-state and remote bundle versions as intended.
