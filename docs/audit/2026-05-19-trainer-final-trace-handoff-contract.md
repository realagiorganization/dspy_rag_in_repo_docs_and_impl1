# Trainer Final Trace Handoff Contract

Date: `2026-05-19`

## Change

This note records the trainer-ingestion fix that followed the first successful live run after the
compact mediation and full-trace policy changes.

The bug was not in family routing or SQLite publishing. It was in the handoff boundary between the
prompt-executor and trainer:

1. the worker exported proxy turn-trace batches and then skipped the final trainer-facing
   execution-trace handoff whenever a batch manifest existed
2. trainer ingestion still accepted `codex-proxy-turn-mediation` records as if they were normal
   execution traces

That combination let a proxy mediation trace seed a brand-new singleton family and overwrite the
previous stable six-family library.

## What Changed

- prompt-executor now treats `repo_rag_turn_traces/<batch>/...` as audit-only artifacts
- the worker always performs final execution-trace export and queue/import handoff after proxy
  execution, even when a turn-trace batch was also exported
- the worker no longer records batch queue/import payloads as if they were trainer handoff outputs
- trainer ingestion now rejects mediation-only records when either of these is true:
  - `source_command = codex-proxy-turn-mediation`
  - `trace.mode = codex-proxy-turn-mediation`

## Why

The product contract is that trainer behavior should be stable regardless of whether a previous
remote library already exists:

- if no version exists, trainer builds families from the final execution traces in the imported
  batch
- if a version exists, trainer loads that baseline and applies the same family assignment logic to
  the new final execution traces

That contract breaks if trainer sometimes sees real execution traces and sometimes sees
intermediary mediation turns. The family algorithm was behaving consistently; the input surface was
not.

The repaired invariant is therefore:

- append-only turn traces remain useful for audit/debug/history
- trainer ingestion uses only final execution traces
- mediation-only traces are never valid training exemplars

## Verification

Executed in the current turn:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_training_samples.py -q`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make quality`
- `cd ../dataset && pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py -q`

Observed:

- `compileall` passed
- `tests/test_training_samples.py` passed as `42 passed`
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed as `62 passed`
- smoke test passed
- Rust build passed
- dataset worker regression slice passed as `24 passed`
- `make quality` passed with:
  - `374 passed`
  - `3 skipped`
  - total coverage `81.57%`

## Scope Notes

- This note covers repository-local correctness of the worker-to-trainer trace boundary.
- Live AKS redeploy and a fresh trainer cycle are still required to prove the repaired invariant in
  blob-backed production state.
