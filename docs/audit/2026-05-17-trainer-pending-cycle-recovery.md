# 2026-05-17 Trainer Pending-Cycle Recovery

- Scope: explain why fresh `repo-rag-training-traces` runs still failed to publish new
  `repo-rag-training-families` / `repo-rag-bundles` versions even after Azure queue mirroring was
  repaired, then harden the trainer so one drained queue cycle survives pod replacement and later
  resumes from local state.
- Preceding note: `2026-05-17-live-trainer-queue-mirroring.md`

## Live Evidence

- Latest pipeline run inspected for this follow-up: GitHub Actions `25987961494`, completed
  `2026-05-17 10:10:10 UTC`.
- Matching worker artifacts still reported a successful queue handoff:
  - `repo_rag_backend.json` showed `trace_queued=true`,
    `trace_handoff_mode="queue"`, and `trace_handoff_status="queued"`.
  - `repo_rag_turn_trace_batch_manifest.json` listed `8` trace files in batch
    `20260517T102248Z`.
- Live blob state after that run:
  - `repo-rag-training-traces/queued/repo-rag-training/` was empty at inspection time
  - `repo-rag-training-traces/batches/20260517T102248Z/` contained those `8` traces
  - `repo-rag-training-traces/processed/repo-rag-training/...` already contained the same `8`
    traces, and each processed payload still recorded
    `queue_item_path="artifacts/traces/queued/repo-rag-training/...json"`
- Live trainer-cycle state:
  - visible `repo-rag-trainer-cycle-*` pods logged `queued_count_before=0`,
    `drained_count=0`, `candidate_count=0`, and `publish_requested=false`
  - Kubernetes events for job `29650230` showed one trainer pod was killed and a replacement pod
    was started for the same cycle

## Root Cause

- The source tree already mirrored queued items locally and remotely, so the remaining bug was not
  “queued was never created”.
- The failure window was between `drain_trace_queue(...)` and family-state publication:
  - one trainer pod could drain queued items and move them to `processed`
  - that same pod could then die before `materialize_training_candidates(...)`,
    family-state upload, or bundle publish finished
  - the replacement pod would see an empty queue and skip the cycle entirely
- Because the queue drain had already happened, there was no durable local marker telling the next
  trainer pod which imported trace paths still belonged to the interrupted cycle.

## Source Fixes Landed

- `src/repo_rag_lab/utilities.py`
  - introduced `artifacts/trainer/pending-cycle.json` as a local durable ledger for the current
    trainer cycle immediately after queue drain succeeds
  - trainer cycles now resume from that ledger when the live queue is already empty but the prior
    cycle did not finish
  - the resumed cycle reports
    `durable_trace_recovery.status="pending-cycle-resume"` and restores the exact imported trace
    paths that were already drained
  - the pending-cycle ledger now survives any failed trainer cycle and is only cleared after the
    overall cycle finishes successfully
- `tests/test_utilities.py`
  - added regression coverage for:
    - resuming a previously drained cycle after queued blobs have already disappeared
    - keeping the pending-cycle ledger when recompile fails after queue drain
    - keeping the pending-cycle ledger when materialization crashes before publication

## Verification

Checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py -q -k 'pending_cycle'` —
  `pass` (`3 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_runtime_artifacts_azure.py tests/test_repository_rag_bdd.py -q` —
  `pass` (`82 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`

Checks not executed in this turn:

- No new post-fix AKS run has been observed yet on a trainer image that includes this
  `pending-cycle` recovery logic.
- No fresh remote publish into `repo-rag-training-families` / `repo-rag-bundles` has been
  observed yet after this source repair.

## Current Status

- `queued -> processed` no longer creates an unrecoverable hole when the trainer pod dies after
  drain and before publish.
- The trainer now has a durable local resume point for the current cycle instead of relying on the
  queue still being visible after pod replacement.
- A fresh deployed run is still needed to confirm that the repaired trainer now publishes new
  family-state and bundle versions in the live cluster.
