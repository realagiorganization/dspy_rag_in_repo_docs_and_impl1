# 2026-05-10 Live Trainer Service Replays Processed Ledger While Queue Is Empty

## Context

The user asked whether the live trainer had started running continuously even though the
`repo-rag-training` queue was empty, noting that the latest publication had happened only a few
minutes earlier.

This note records the live AKS inspection of the `repo-rag` namespace plus a fresh local baseline
verification pass from this repository checkout.

## Live Findings

### 1. The queue is empty, but the long-lived trainer service still keeps recompiling

Live inspection in namespace `repo-rag` shows:

- deployment pod:
  - `repo-rag-trainer-service-7c5b69786f-rwx8z`
- active cronjob job pod:
  - `repo-rag-trainer-cycle-29640765-jsk5h`

The trainer queue is currently empty:

- `kubectl -n repo-rag exec repo-rag-trainer-service-7c5b69786f-rwx8z -- sh -lc 'find /workspace/repo-rag/artifacts/traces/queued -maxdepth 2 -type f'`
  returned no queued files
- the persisted service state also reports:
  - `total_drained_count = 0`
  - `queue_drain.selected_count = 0`
  - `queue_drain.drained_count = 0`

However, the service is still recompiling because it is recovering and ingesting the historical
processed ledger:

- `recovered-imported-traces/` currently contains `121` files
- the latest recorded cycle restored `22` processed traces even though queue drain found `0`
  queued items
- the same cycle then rebuilt trainer candidates and recompiled DSPy artifacts

So the current live trainer behavior is:

- **queue empty**
- **service still performs expensive recovery/materialization/recompile work**

That confirms the user's suspicion.

### 2. The live trainer is running with stale deployment config

The current live command lines are still:

- `--recompile-optimizer bootstrapfewshot`
- `--minimum-bundle-pass-rate 1.0`

This is visible both in the running pod descriptions and in the live ConfigMap:

- `TRAINER_RECOMPILE_OPTIMIZER=bootstrapfewshot`
- `TRAINER_MIN_BUNDLE_PASS_RATE=1.0`

So the live cluster has **not** picked up the newer local fixes that:

- remove the hidden bundle gate default
- stop using `bootstrapfewshot` as the unintended trainer-side default for this family-first path

### 3. The "running without stop" behavior is a mix of intended polling plus unintended replay

Part of what the user is seeing is expected:

- `trainer-service` is designed as a long-lived poller
- the current live deployment has:
  - `--poll-interval-seconds 60.0`
  - `--max-idle-cycles` unset

So the service is meant to keep running forever unless redeployed or stopped.

But the expensive part is **not** expected:

- idle cycles should not keep replaying the processed ledger and recompiling from it
- in the live state they still do

### 4. The cronjob path is also unhealthy

Live cronjob inspection shows:

- the cronjob runs every `15` minutes
- a current job pod has already been running for about an hour
- the pod restarted once after exiting with code `1`
- Kubernetes is now emitting:
  - `JobAlreadyActive`
  - `Not starting job because prior execution is running and concurrency policy is Forbid`

So the namespace currently has both:

- a continuously polling `trainer-service`
- and a stuck/long-running `trainer-cycle` job

This is another reason the system looks like it is "working without stopping".

## Evidence Summary

The most important live evidence captured in this turn:

- `kubectl -n repo-rag get pods -o wide`
- `kubectl -n repo-rag get deploy,cronjob,job,svc,cm,secret`
- `kubectl -n repo-rag get events --sort-by=.lastTimestamp | tail -n 80`
- `kubectl -n repo-rag describe pod repo-rag-trainer-service-7c5b69786f-rwx8z`
- `kubectl -n repo-rag describe pod repo-rag-trainer-cycle-29640765-jsk5h`
- `kubectl -n repo-rag logs repo-rag-trainer-service-7c5b69786f-rwx8z --tail=200`
- `kubectl -n repo-rag exec repo-rag-trainer-service-7c5b69786f-rwx8z -- sh -lc 'cat /workspace/repo-rag/artifacts/trainer/service-state.json'`
- `kubectl -n repo-rag get configmap repo-rag-trainer-config -o yaml`

Key facts from those commands:

- queue empty
- service still recovering processed traces
- `121` recovered trace files present locally in the trainer PVC
- current live service state shows `cycles_executed = 2`, `failed_cycle_count = 2`,
  `bundle_gate_failure_count = 2`
- live config still forces:
  - `bootstrapfewshot`
  - `TRAINER_MIN_BUNDLE_PASS_RATE = 1.0`

## Local Verification Baseline

Executed in this repository checkout during the same turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `47 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`

## Conclusion

The trainer is currently "working without stop" for two separate reasons:

1. **By design**, `trainer-service` is a perpetual poller with no `max_idle_cycles`.
2. **By bug/stale deploy**, the live service still replays processed traces and recompiles even
   when the queue is empty, and it is still running with the old:
   - `bootstrapfewshot`
   - `TRAINER_MIN_BUNDLE_PASS_RATE=1.0`

So the current live behavior is not a simple queue backlog. It is a stale trainer deployment
continuing to do expensive historical recovery and compile work while the queue itself is empty.

## Next Action

The live fix should not start with more worker runs. The next operator step should be:

1. redeploy the trainer with the current repository code and current deployment defaults
2. ensure the live ConfigMap no longer contains:
   - `TRAINER_MIN_BUNDLE_PASS_RATE=1.0`
   - `TRAINER_RECOMPILE_OPTIMIZER=bootstrapfewshot` unless explicitly desired
3. verify that an idle service cycle reports:
   - empty queue
   - no processed-ledger replay
   - no recompile
