# 2026-05-11 Trainer Is Now Queue-Only And Will Not Replay Processed History

## Context

The live trainer had slipped back into an unsafe posture:

- `repo-rag-trainer-service` was running as a poller
- `repo-rag-trainer-cycle` CronJob was already suspended
- Azure `queued/` was empty
- but the service pod still carried a large recovered/imported trace ledger under
  `artifacts/trainer/recovered-imported-traces/` and `artifacts/traces/imported/`

The user requirement is stricter than the earlier preflight fix:

- trainer work must begin only when a new trace appears in `queued/`
- processed / recovered history must not trigger or augment an active train cycle
- unchanged families must carry forward; only families that received a new trace may recompile

## Live Confirmation Before The Fix

The following live checks were run before changing code:

- `kubectl get deploy,cronjob,jobs,pods -n repo-rag -o wide`
- `kubectl logs deployment/repo-rag-trainer-service -n repo-rag --tail=400`
- `kubectl exec -n repo-rag deploy/repo-rag-trainer-service -- ...`
- Azure blob listing for `repo-rag-training-traces` and `repo-rag-training-families`

Observed state:

- `repo-rag-trainer-service` was `1/1`
- `repo-rag-trainer-cycle` was `SUSPEND=True`
- service logs still showed DSPy bootstrap activity
- `queued_count = 0`
- `processed_count = 0`
- `recovered_count = 239`
- `artifacts/trainer/family-state.json` and `generated-training.yaml` kept updating

That combination confirmed the dangerous behavior: the trainer could still treat historical
processed-ledger recovery as actionable work even when the queue itself was empty.

## Immediate Live Mitigation

The live module was stopped immediately:

- `kubectl scale deployment repo-rag-trainer-service -n repo-rag --replicas=0`
- `kubectl patch cronjob repo-rag-trainer-cycle -n repo-rag -p '{"spec":{"suspend":true}}'`
- deleted stale trainer-cycle jobs

Verification after shutdown:

- `deployment.apps/repo-rag-trainer-service` -> `0/0`
- `cronjob.batch/repo-rag-trainer-cycle` -> `SUSPEND=True`
- no active trainer pods/jobs remained

## Root Cause

Two code paths still violated the strict queue-only contract:

1. `inspect_pending_trainer_inputs(...)` in `src/repo_rag_lab/runtime_artifacts.py`
   previously set:
   - `current_cycle_input_detected = queue_visible_count > 0 or recoverable_processed_count > 0`
2. `run_trainer_cycle(...)` in `src/repo_rag_lab/utilities.py`
   still called `restore_processed_trace_records(...)` and merged recovered trace paths into the
   active train input set

That meant processed history could still:

- trigger service preflight
- enter active candidate materialization
- keep dirty-family recompiles alive without any fresh queued trace

## Fix Implemented

The queue-only contract is now explicit.

### 1. Service preflight is queue-only

`inspect_pending_trainer_inputs(...)` now reports `current_cycle_input_detected=True` **only** when
`queue_visible_count > 0`.

`recoverable_processed_count` is still reported diagnostically, but it no longer authorizes a
trainer cycle.

### 2. Active trainer cycles no longer replay processed history

`run_trainer_cycle(...)` now:

- does **not** call `restore_processed_trace_records(...)`
- does **not** merge recovered trace paths into `trainer_trace_paths`
- records a disabled recovery summary:
  - `status = "queue-only-disabled"`
  - `restored_count = 0`

So the active train input set now comes only from fresh queue drain items.

### 3. Dirty-family recompiles remain incremental

This fix does **not** undo family-level incrementality:

- fresh queued traces still materialize into families
- only dirty families recompile
- clean families still carry forward from the previous versioned family-state / bundle artifacts

What changed is only the source of active work:

- before: queue plus recovered history
- now: queue only

## Test Updates

The regression suite was updated to match the new contract:

- `tests/test_runtime_artifacts_azure.py`
  - recoverable processed traces no longer imply `current_cycle_input_detected=True`
- `tests/test_utilities.py`
  - active trainer-cycle tests now expect queue-only trace paths
  - durable recovery payloads now assert `status = "queue-only-disabled"`
  - family-drift recompilation tests now require a real drained queued trace
  - service idle-skip warnings now explicitly mention queued traces only

## Local Verification

Executed in this repository checkout during the same turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_runtime_artifacts_azure.py tests/test_utilities.py -q`
  - `64 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_repository_rag_bdd.py -q`
  - `49 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`
- `make files-sync`
  - pending at audit creation time
- `make verify-surfaces`
  - pending at audit creation time

## Conclusion

Yes, the live trainer had re-entered an unsafe loop posture.

Yes, it was stopped immediately.

Yes, the local code now matches the stricter requirement:

- trainer service starts real work only when `queued/` has new input
- processed / recovered history is no longer replayed into active cycles
- dirty-family recompiles still happen incrementally, but only from fresh queue-derived traces

The remaining operational step is redeploying the updated image before the trainer is re-enabled in
AKS.
