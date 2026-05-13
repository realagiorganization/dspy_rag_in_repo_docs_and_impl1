# 2026-05-13 Trainer Local Cache Thin Index One Version Per Queue Cycle

## Scope

Lock the trainer onto the user-requested lifecycle:

1. one queue event authorizes one trainer cycle
2. trainer reuses an existing local family cache when present
3. trainer adopts the latest remote family-state version only when the local cache is missing
4. trainer rebuilds from `repo-rag-training-traces/processed` only when neither local nor remote
   state exists
5. that from-scratch rebuild stays local until current `queued` traces are applied
6. `family-state.json` acts as a thin index, while full family payloads live under
   `artifacts/trainer/families/<prompt_family_id>/...`

## Root Cause

The previous trainer path still allowed one logical training request to inflate into multiple
remote versions:

- family-state preparation could rebuild transformed family state from `processed` history before
  current `queued` traces were applied
- that bootstrap rebuild used the normal materialization path, so it could publish a remote
  family-state snapshot on its own
- the same trainer cycle then applied the current `queued` traces and published again

That was the structural reason a single run could mint more than one family-state version even
after earlier queue-only fixes.

## Code Changes

- `src/repo_rag_lab/utilities.py`
  - adds `_prepare_local_trainer_family_cache(...)`
  - adds `_clear_local_trainer_family_cache(...)`
  - adds `_adopt_remote_family_cache(...)`
  - `run_trainer_cycle(...)` now prepares one active local family cache before ingesting current
    queue input
  - from-scratch rebuilds call `materialize_training_candidates(..., upload_remote_state=False)`
    so no intermediate remote version is minted
- `src/repo_rag_lab/training_samples.py`
  - `family-state.json` is now written as a thin index
  - full family payloads are persisted under `artifacts/trainer/families/<prompt_family_id>/`
    as `family.json`, `father.json`, and `records/*.json`
  - `load_family_state_payload(...)` hydrates the full family payload from those local files
- `src/repo_rag_lab/runtime_artifacts.py`
  - remote family-state upload/fetch now understands the thin index plus per-family cache layout
- `src/repo_rag_lab/dspy_training.py`
  - dirty-family compile reads hydrated family state through `load_family_state_payload(...)`

## Verification

Ran:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_training_samples.py tests/test_runtime_artifacts_azure.py tests/test_utilities.py tests/test_dspy_training.py -q`

Result:

- `131 passed`
- compile step passed

New regression coverage now verifies:

- existing local family cache is reused without remote fetch or processed replay
- the latest remote family-state version is adopted into local cache when local state is absent
- from-scratch cache preparation uses `upload_remote_state=False`
- trainer-cycle still applies current `queued` traces after that local cache preparation
- persisted `family-state.json` no longer duplicates replay-set payloads inline

## Remaining Risk

- this is a local code fix only until a new trainer image is deployed
- older live versions can still re-enter the old behavior if restarted without redeploy
- the top-level thin index still carries lightweight routing/runtime summaries, so the next size
  audit should measure a real live family-state version after redeploy instead of assuming the file
  is now minimal in absolute terms
