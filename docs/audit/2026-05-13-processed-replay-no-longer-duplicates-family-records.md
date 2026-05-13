# 2026-05-13 Processed Replay No Longer Duplicates Family Records

## Scope

Investigate why the live trainer minted multiple `repo-rag-training-families` versions for what
looked like two logical queue events, and verify whether the later family-population version
replayed historical `processed` traces or only the newest queued traces.

## Live Evidence

- The trainer was stopped before analysis: `repo-rag-trainer-service` scaled to `0`, and
  `repo-rag-trainer-cycle` was suspended.
- Remote family-state versions present during inspection were:
  - `20260513T113036Z`
  - `20260513T114510Z`
  - `20260513T120021Z`
  - `20260513T120237Z`
  - `20260513T120803Z`
  - `20260513T121607Z`
- The thin-index contract was active in live storage:
  - `versions/20260513T120803Z/family-state.json` size `5967`
  - `versions/20260513T121607Z/family-state.json` size `5967`
  - top-level `family-state.json` contained only thin routing/index metadata plus per-family paths

## What Actually Happened

Remote family payload inspection showed:

- `20260513T120237Z` contained `3` family replay records
- `20260513T120803Z` contained `25` family replay records
- `20260513T121607Z` contained `50` family replay records

The critical detail is that `20260513T121607Z` did **not** contain newer `recorded_at` values than
`20260513T120803Z`. Instead, it replayed the same logical trace set from `processed` using new
imported trace filenames such as:

- original imported path:
  `artifacts/traces/imported/20260513T120200Z-worker-0-...-0.json`
- replayed imported path:
  `artifacts/traces/imported/20260513T121509Z-20260513T120200Z-worker-0-...-0.json`

That proved the trainer was not pulling all `206` historical processed traces into one family.
Instead, it replayed the **same 25 logical traces** from the latest processed batch and treated
them as new snapshots because snapshot identity depended on the imported trace path.

## Root Cause

Two coupled bugs were present:

1. Imported trace records did not preserve a stable source identity from the original queued item.
   Replaying the same processed queue item therefore generated a fresh imported path and a fresh
   `exact_snapshot_id`.
2. `materialize_training_candidates(...)` still uploaded a fresh remote family-state version even
   when the current cycle produced no accepted/candidate records, which allowed empty or thin
   no-op versions to accumulate.

## Code Changes

- `src/repo_rag_lab/runtime_artifacts.py`
  - imported trace records now persist `source_queue_item_path`, `source_trace_name`, and
    `source_batch_name`
  - queue drain and processed replay both pass the same stable queued-item identity into imported
    trace records
- `src/repo_rag_lab/training_samples.py`
  - trainer candidate identity now prefers a stable source token derived from the queued item or a
    canonicalized imported trace filename
  - family replay upserts now dedupe logical replays instead of double-counting them
  - existing family payloads are sanitized on load so already duplicated replay records collapse
    back onto one logical trace
  - remote family-state uploads are skipped when the current cycle loaded no accepted/candidate
    records

## Interpretation

- `family-state.json` was **not** the large replay buffer anymore; the live file was already a thin
  index.
- The runaway growth that the user observed came from replayed `family.json` record sets, not from
  the top-level index file.
- The trainer did restore from `processed`, but in this case it replayed the same most recent
  logical batch rather than all historical processed traces.

## Verification

Ran:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_runtime_artifacts_azure.py tests/test_training_samples.py -q`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Results:

- compile step passed
- targeted tests: `50 passed`
- repository utility tests: `52 passed`
- smoke test passed
- cargo build passed

## Remaining Risk

- This is still a local fix until a new trainer image is deployed.
- Live storage already contains versions with duplicated family replay records; the next trainer run
  with the new code should sanitize them when the family cache is hydrated.
- The deployment still needs one authoritative execution mode for trainer cycles; dual activation
  of service and cronjob remains a separate operational risk even after replay dedupe is fixed.
