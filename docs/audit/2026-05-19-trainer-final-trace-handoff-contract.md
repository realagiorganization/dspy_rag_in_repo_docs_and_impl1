# Trainer Final Trace Handoff Contract

Date: `2026-05-19`

## Change

This note records the trainer-ingestion fix that followed the first successful live run after the
compact mediation and full-trace policy changes.

The bug was not in family routing or SQLite publishing. It was in the handoff boundary between the
prompt-executor and trainer:

1. the worker exported proxy turn-trace batches but then accidentally disabled batch queue/import
   handoff almost all the time
2. trainer ingestion still accepted raw `codex-proxy-turn-mediation` records as if they were
   normal execution traces

That combination let a proxy mediation trace seed a brand-new singleton family and overwrite the
previous stable six-family library.

## What Changed

- prompt-executor now preserves the intended hierarchy:
  - enriched per-turn batch traces are the preferred trainer-ingestion surface
  - the final single execution trace is only a fallback when no usable batch exists or batch
    handoff fails
- the worker no longer disables batch queue/import handoff by default
- enriched batch traces are normalized out of `codex-proxy-turn-mediation` mode before trainer
  export so they remain valid execution-stage training traces
- worker/backend summaries now reflect batch queue/import handoff correctly
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

- append-only raw mediation traces remain useful for audit/debug/history
- enriched per-turn execution traces are the primary trainer-ingestion surface
- the final single execution trace is fallback-only
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
