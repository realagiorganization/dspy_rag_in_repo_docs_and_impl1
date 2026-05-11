# 2026-05-11 Trainer Service Preflights Queue Before Running Cycles

## Context

The live `repo-rag-trainer-service` had already been stopped operationally:

- `kubectl -n repo-rag scale deployment repo-rag-trainer-service --replicas=0`
- `kubectl -n repo-rag patch cronjob repo-rag-trainer-cycle -p '{"spec":{"suspend":true}}'`

Verification immediately after those commands showed:

- `deployment.apps/repo-rag-trainer-service` at `0/0`
- `cronjob.batch/repo-rag-trainer-cycle` with `SUSPEND=True`
- no active trainer jobs
- only old completed / failed historical jobs remaining

The user then asked for a stronger guarantee: the trainer should begin a cycle only when queue
input exists.

## Live Architecture Constraint

The repository still does **not** have a queue-triggered autoscaler or launcher.

Local source inspection confirmed the live design is still:

- one long-lived `trainer-service` poller
- one optional `trainer-cycle` CronJob

There is no KEDA / `ScaledObject` / `ScaledJob` / queue-event controller in the current repo or
dataset deployment path.

So the strict statement is:

- we can stop the live trainer now
- we can harden the code so the service **does not invoke `trainer-cycle` unless queue/recovery
  input exists**
- but we do **not** yet have infrastructure that auto-starts the pod itself exactly when queue
  becomes non-empty

## Root Cause

Even after the earlier Stage 26 fix stopped idle cycles from auto-republishing bundles, the
service still executed a full `run_trainer_cycle()` on every poll interval.

That meant:

1. the pod kept waking up every poll
2. it still entered the trainer-cycle code path
3. only *inside* that cycle did it discover there was no new queue work

So the service still behaved like a poller that always starts a cycle, instead of a poller that
checks for queue input first.

## Fix Implemented

Three local code changes now enforce a queue-first preflight:

1. `src/repo_rag_lab/azure_artifacts.py`
   - added `AzureArtifactStore.approximate_queue_message_count(...)`
2. `src/repo_rag_lab/runtime_artifacts.py`
   - added `inspect_pending_trainer_inputs(...)`
   - this reports:
     - `queue_visible_count`
     - `recoverable_processed_count`
     - `current_cycle_input_detected`
3. `src/repo_rag_lab/utilities.py`
   - `run_trainer_service()` now calls that preflight helper before every loop
   - if there are no queued items and no recoverable processed traces, the service:
     - does **not** call `run_trainer_cycle()`
     - records an idle state update
     - increments idle counters
     - sleeps or exits on `max_idle_cycles`

In other words, after redeploy the service still exists as a poller, but it only starts an actual
trainer cycle when queue/recovery input exists.

## Tests Added

Updated / added regressions now cover:

- `tests/test_utilities.py`
  - `test_run_trainer_service_skips_cycle_when_queue_and_recovery_are_empty`
  - existing service tests now patch the new preflight helper explicitly
- `tests/test_runtime_artifacts_azure.py`
  - filesystem queue visibility + recoverable processed-trace detection
  - Azure queue visibility inspection

## Local Verification

Executed in this repository checkout during the same turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_runtime_artifacts_azure.py -q`
  - `64 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_repository_rag_bdd.py -q`
  - `3 passed`

## Verification Categories Not Executed In This Turn

- live AKS redeploy with the new code
  - not run
- live queue appearance test after redeploy
  - not run
- coverage / lint / mypy / basedpyright
  - not run in this turn
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - not re-run in this turn
- `uv run repo-rag smoke-test`
  - not re-run in this turn

## Conclusion

Yes, the live trainer is stopped.

Yes, the local code now enforces: **no `trainer-cycle` invocation without queued or recoverable
trace input**.

No, the infrastructure is still not truly queue-triggered in the Kubernetes sense; achieving that
would require a new queue-event launcher or autoscaler.
