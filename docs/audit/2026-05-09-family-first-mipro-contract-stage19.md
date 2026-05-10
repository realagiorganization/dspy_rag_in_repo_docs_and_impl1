# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 19

## Scope

- Remove champion-named fields from trainer-candidate summaries and pending-recompile payloads.
- Keep the mirrored `champion-index.json` file only as on-disk compatibility state.

## Contract status in this turn

The trainer-side machine payload contract is now more strictly family-first:

1. `materialize_training_candidates(...)` no longer emits `champion_index_path`,
   `champion_trace_record_paths`, `champion_exact_snapshot_ids`, `champion_record_hashes`, or
   `remote_champion_state` in its summary payload.
2. `run_trainer_candidates(...)` now advertises only `family_state_path` as the active trainer
   state artifact path.
3. `_trainer_pending_recompile_summary(...)` now emits only family-state counters and paths, while
   still reading older lineage and candidate payloads compatibly when champion-named fields are all
   that exist.

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Trainer candidate/runtime code:
  - `src/repo_rag_lab/training_samples.py`
  - `src/repo_rag_lab/utilities.py`
- Trainer summary tests:
  - `tests/test_training_samples.py`
  - `tests/test_utilities.py`

## What is implemented now

### 1. Family-state summaries are now family-only by default

`summarize_family_state(...)` now returns only:

- `family_trace_record_paths`
- `family_exact_snapshot_ids`
- `family_record_hashes`
- other family-state counters

The explicit compatibility wrapper `summarize_champion_index(...)` still re-adds the old
`champion_*` aliases for call sites that intentionally request the compatibility view.

### 2. Trainer candidate summaries no longer advertise champion alias fields

`materialize_training_candidates(...)` and the JSON returned by `trainer-candidates` now expose:

- `family_state_path`
- `family_trace_record_paths`
- `family_exact_snapshot_ids`
- `family_record_hashes`

while the mirrored `artifacts/trainer/champion-index.json` file still exists on disk beside
`artifacts/trainer/family-state.json`.

### 3. Pending-recompile payloads are family-first too

Pending-recompile summaries and trainer-cycle recompile lineage now publish only the family-state
path plus the family-state counters/hashes. They still **read** older bundle lineage or older
training-candidate payloads that carry `champion_*` fields, but they no longer write those fields
back out as part of the active contract.

## What is not implemented yet

- mirrored local/state payload aliases still exist in several deeper helper layers
- mirrored `champion-index.json` files still coexist with `family-state.json`
- live AKS validation of the full family-first loop still has not been run in this turn
- notebook execution, coverage, UI/browser verification, and live deployment validation were not
  run in this turn

## Verification executed in this turn

Targeted checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_training_samples.py tests/test_utilities.py -q`
  - `pass` (`69 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`45 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`
- `make files-sync`
  - `pass`
- `make exploratorium-sync`
  - `pass`
- `make verify-surfaces`
  - `pass`

## Current conclusion

The family-first migration now reaches the main trainer machine payloads too. Champion naming is
still present as a compatibility file and explicit compat wrapper, but it is no longer the active
summary contract for trainer candidate materialization or pending-recompile reporting.
