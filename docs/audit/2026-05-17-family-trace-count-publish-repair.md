# 2026-05-17 Family Trace Count Publish Repair

- Scope: investigate why not every proxy trace reaches `repo-rag-training-families`, confirm where counts diverge, and repair the trainer/publish path so all imported traces remain represented in family state.
- Preceding note: `2026-05-16-live-family-run-review.md`

## Live Symptom Reviewed

- Latest reviewed live artifact run: `25983147671_20260517_062635`
- Worker/export side produced `7` trainer-facing traces in one batch.
- Blob import side also produced `7` processed trace blobs.
- Published `repo-rag-training-families` version from that run exposed only `4` persisted family records across `2` families.

This confirmed that the loss happened after queue import, not before it.

## Root Cause Found In Source

Local reproduction against the exact `7` imported trace JSON files showed that the current
`materialize_training_candidates(...)` path does keep all `7` records inside the local family
cache. The two source-level consistency gaps were downstream of that:

1. Thin-index persistence still left `family_record_count` incomplete or `null` in some family
   payloads, and kept `question_variants` inline in top-level `family-state.json`.
2. `upload_remote_family_state(...)` computed aggregate `family_record_count` too early, before
   family payload normalization and record-blob expansion. That let published remote summaries
   undercount family records even when the underlying family payloads and record blobs existed.
3. `fetch_remote_family_state(...)` rehydrated local family payloads without writing the resolved
   `family_record_count` back into cached `family.json`, so the cached family detail could still
   disagree with the remote index summary.

## Source Fixes Landed

- `src/repo_rag_lab/training_samples.py`
  - top-level thin family-state entries now omit inline `question_variants`
  - `question_variant_count` is derived from the stored family payload
  - `family_record_count` is written into both the thin index and each persisted `families/*/family.json`
  - legacy/hydrated family payload normalization now backfills `family_record_count`
- `src/repo_rag_lab/runtime_artifacts.py`
  - remote publish now computes `family_record_count` from the normalized record set actually uploaded
  - published `family-state.json` and `current.json` now both expose aggregate record counts
  - cached rehydrated `family.json` now rewrites the resolved `family_record_count`
- Regression tests added:
  - `tests/test_training_samples.py::test_materialize_training_candidates_preserves_all_imported_full_traces_in_family_records`
  - stronger assertions in `tests/test_runtime_artifacts_azure.py::test_upload_and_fetch_remote_family_state_prefer_family_state_container`

## Verification

Configured checks in this repo:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Checks executed in this turn:

- `uv run python -m compileall src tests` — `pass`
- `uv run pytest tests/test_training_samples.py tests/test_runtime_artifacts_azure.py` — `pass` (`59 passed`)
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py` — `pass` (`59 passed`)
- `uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`

Checks not executed in this turn:

- `make quality` — not run
- `make coverage` — not run
- No separate deployment/integration live rerun was executed in this turn
- No UI-specific verification exists for this change set

## Evidence And Remaining Gap

- Local reproduction now preserves all `7` imported traces as persisted family records.
- Local publish/fetch now keeps `family_record_count` aligned with the actual uploaded record blobs.
- The previous live run cannot fully validate the fix because the code currently checked out in this
  repo (`76e5736b4cc78895e7026a8d48ffb1568a402c95`) does not match the dataset submodule revision
  used for the earlier pipeline image (`30f6974498466be3e5356eea50e784116f88eff1`).

## Current Status

- Source now satisfies the contract that every imported proxy trace remains represented in family
  storage and family-state counts.
- The remaining unverified part is operational: a fresh live pipeline run is still required to
  confirm that the deployed trainer image now publishes all imported traces into
  `repo-rag-training-families` without the earlier `7 -> 4` drop.
