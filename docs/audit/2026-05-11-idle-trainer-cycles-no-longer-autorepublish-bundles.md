# 2026-05-11 Idle Trainer Cycles No Longer Auto-Republish Bundle Versions

## Context

The user reported that a single pipeline run had produced multiple published bundle versions on the
same day:

- `20260511T092140Z`
- `20260511T094009Z`
- `20260511T095234Z`
- `20260511T100446Z`
- `20260511T101758Z`
- `20260511T103126Z`

That should not happen when only one fresh queue import reached the trainer.

## Root Cause

`run_trainer_cycle()` still allowed automatic recompilation whenever:

- `recompile_run_name` was configured
- `pending_recompile` stayed `true`

even when the current cycle had imported **no new traces at all**.

So a long-lived `trainer-service` could keep looping like this:

1. idle poll
2. see stale `pending_recompile`
3. mint a fresh timestamped `resolved_recompile_run_name`
4. compile again
5. publish another immutable bundle version

This was an actual bug and explains how one real queue import could fan out into multiple bundle
versions.

## Fix Implemented

`src/repo_rag_lab/utilities.py` now gates the automatic `pending_recompile` branch on
**current-cycle input**.

The trainer now records:

- `current_cycle_trace_input_count`
- `current_cycle_queue_drain_count`
- `current_cycle_recovered_count`
- `current_cycle_input_detected`

and only auto-triggers a pending recompilation when the current cycle actually imported or
recovered new traces.

An idle cycle with:

- `pending_recompile = true`
- but no new queue / recovered input

now records a warning and skips auto-recompile instead of minting another timestamped bundle
version.

The same patch also merges:

- `imported_trace_paths`
- `recovered_trace_paths`

into one de-duplicated trainer input list, so a fresh queue item cannot be ignored just because
the same cycle also restored a processed-ledger trace.

## Local Verification

Executed in this repository checkout during the same turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `48 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`

Added or updated regressions in `tests/test_utilities.py` now verify both:

1. idle pending-recompile cycles skip auto-recompile and skip publish
2. pending family drift still recompiles once when a cycle actually imports new traces

## Verification Categories Not Executed in This Turn

- live AKS redeploy
  - not run
- live blob inspection after redeploy
  - not run
- coverage / lint / type checking
  - not run in this turn
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - not re-run in this turn because the Rust surface was unchanged

## Conclusion

Yes, the repeated versions were caused by a trainer-side bug.

The local fix now prevents idle `trainer-service` cycles from auto-publishing fresh timestamped
bundle versions when no new queue input arrived in the current cycle.

## Next Step

Redeploy the trainer/runtime image and verify live that:

1. one queue import yields at most one new bundle version
2. later idle cycles report pending state without compiling or publishing again
