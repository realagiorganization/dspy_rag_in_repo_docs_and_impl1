# 2026-05-16 Cron-Only Trainer Orchestration

## Summary

- AKS trainer orchestration now prefers a single cron-driven `trainer-cycle` surface.
- The default Cron schedule is tightened from `*/15 * * * *` to `*/5 * * * *`.
- Kubernetes manifest generation no longer emits a `trainer-service` Deployment.
- The `trainer-service` CLI remains available only for local debugging and one-off recovery work.

## Why

Live inspection showed two near-simultaneous `repo-rag-training-families` versions in one queue
window because both of these were active against the same publish path:

- `repo-rag-trainer-service`
- `repo-rag-trainer-cycle`

That was operationally wrong for the desired contract:

- workers may enqueue traces whenever they want
- one scheduled trainer wake-up should drain the queue
- one trainer pass should publish at most one family-state / bundle set per schedule window

## Changes

- `src/repo_rag_lab/trainer_deployment.py`
  - default cycle schedule is now `*/5 * * * *`
  - manifest generation writes only the service account, config map, secret example, PVC, and
    `trainer-cycle.cronjob.yaml`
- `Makefile`
  - `TRAINER_K8S_CYCLE_SCHEDULE` default changed to `*/5 * * * *`
- trainer deployment docs now describe cron-only AKS behavior

## Expected Live Behavior

- `queued` may accumulate between scheduled windows
- every five minutes `trainer-cycle` checks for work
- if the queue is empty, the CronJob exits quickly
- if the queue has items, the CronJob drains them, recompiles if needed, and publishes once
- no long-lived in-cluster trainer poller competes for the same publish path
