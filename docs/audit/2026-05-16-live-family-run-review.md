# 2026-05-16 Live Family Run Review

- Scope: review the latest live pipeline run after deleting old prompt-family versions, with focus on trainer publish, published family-state structure, and prompt-family formation quality.
- Preceding note: `2026-05-15-unified-family-term-stats.md`

## What Changed

- The worker run did not reuse stale DSPy artifacts after the prior family-state cleanup.
- Trainer published a new family-state version and promoted a new stable bundle:
  - `repo-rag-training-families/current.json` -> `20260515T223707Z`
  - `repo-rag-bundles/channels/stable.json` -> `20260515T223232545221Z`
- The published family-state now exposes the new unified term-stat surfaces:
  - `family_prompt_profile_term_stats`
  - `family_command_pattern_term_stats`
  - `family_constraint_term_stats`

## Live Findings

### Worked

- Runtime skipped DSPy reuse while the family index was unavailable and emitted fresh `full_trace` records.
- Trainer drained the queued traces and published both:
  - a new `repo-rag-training-families` version
  - a new stable bundle in `repo-rag-bundles`
- The published family-state contains unified per-term stats with both:
  - `count`
  - `weight`
- Prompt-family formation looked mechanically coherent for this run:
  - `9` exported traces became `8` families
  - exact or near-exact duplicate prompts merged instead of fragmenting into extra families
  - no obvious cross-family misclassification was observed in the published father/record pairs

### Did Not Work

- `family-state.json` still is not a real thin index in live output:
  - size was `373839` bytes for only `8` families
  - inline payloads still remain, including:
    - `family_records`
    - `family_father_record`
    - `family_runtime_artifact`
    - `context_groups`
    - legacy champion fields
- Queue wrapper mirroring is still not correct in the latest live artifacts:
  - `repo_rag_turn_trace_export_batch.json` item summaries contain `trainer_signal_kind` and `prompt_family_band`
  - `repo_rag_turn_trace_enqueue_batch.json` still leaves those item-level fields `null`
  - `.trusted_trace_queue_item.*.json` also still leaves the same top-level fields `null`
- `family_record_count` remained `null` even though inline `family_records` were present, so the published index summary is internally inconsistent.

## Evidence Used

- Local run artifacts under `../dataset/artifacts`
- Blob reads from:
  - `repo-rag-training-families/current.json`
  - `repo-rag-training-families/versions/20260515T223707Z/family-state.json`
  - `repo-rag-bundles/channels/stable.json`

## Current Status

- Live evidence confirms trainer publish recovery and unified term stats in published family-state.
- Live evidence does **not** yet confirm a truly thin family-state index.
- Live evidence also shows the queue/enqueue wrapper mirroring bug is still present after export.

## Follow-up Fixes

- Source-level fixes now landed for the two remaining issues found above:
  - DSPy recompilation now rewrites `family-state.json` back through the thin-index persist path,
    instead of leaving the post-training full in-memory payload serialized at the top level.
  - The dataset deployment handoff script now mirrors trainer/family signal fields into:
    - top-level trusted queue wrappers
    - batch enqueue item summaries
- The active prompt-family summary selector is now stricter:
  - published `family_count` / `prompt_family_count` will be backfilled directly into the remote
    `family-state.json` payload instead of being left `null`
  - active `family_prompt_profile_terms` now prefer technical lookup terms only when a family has
    any technical vocabulary at all
  - broad narrative and low-signal terms such as `actually`, `against`, `compact`, `file`,
    `files`, `path`, `paths`, `prompt`, `query`, and purely numeric tokens are excluded from the
    active summary surface instead of merely being ranked lower
  - the technical lookup now also includes additional category coverage for:
    - `macos_commands`
    - `mobile_dev`
    - `package_managers`
    - `security_infosec`
- Verification executed for those follow-up fixes:
  - `uv run python -m compileall src tests`
  - `uv run pytest tests/test_term_extraction.py tests/test_runtime_artifacts_azure.py -k 'profile_summary or technical_term_categories or low_signal or upload_remote_family_state'`
  - `uv run pytest tests/test_training_samples.py -k 'profile_terms_ignore_one_off_noise or prefers_family_profile_over_surface_similarity or can_use_family_profile_summaries or strips_execution_envelope_from_family_father'`
  - `uv run pytest tests/test_dspy_training.py -k 'recompiles_only_dirty_families'`
  - `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
  - `uv run repo-rag smoke-test`
  - `cargo build --manifest-path rust-cli/Cargo.toml`
  - `cd ../dataset && .venv/bin/pytest tests/unit/test_deployment_script_template_regressions.py -k 'trusted_trace_handoff_after_rehydration'`
  - `cd ../dataset && .venv/bin/pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py -k 'batches_turn_traces_for_queue_handoff'`
- A fresh live run is still required to confirm those two fixes in published blob artifacts.

## Cron-Only Publish Follow-up

The next live trainer investigation found a separate publish blocker after queue drain had already
been repaired:

- worker export, trusted queue handoff, and blob queue drain all succeeded
- `queued/repo-rag-training/` became empty
- `processed/repo-rag-training/` filled with fresh imported trace records
- but `repo-rag-training-families/current.json` and `repo-rag-bundles/channels/stable.json`
  still did not appear

Root cause:

- cron-only trainer runs were still allowed to execute with no explicit `recompile_run_name`
- `run_trainer_cycle(...)` only entered the compile/publish path when `recompile_run_name` was
  not `None`
- therefore a cycle could drain fresh queue items, build candidates, and still exit without any
  compile/publish attempt

Source-level fix:

- `DEFAULT_TRAINER_K8S_RECOMPILE_RUN_NAME` is now `trainer-auto`
- `run_trainer_cycle(...)` now auto-adopts that same run-family when:
  - queue backlog is clear, and
  - either new candidates were imported, or a pending unpublished family-state already exists

Verification executed for the fix:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py -k 'trainer_k8s_manifest_generation_writes_expected_manifests or auto_uses_default_recompile_family_when_queue_drains or recompiles_pending_family_state_after_backlog_clears or recompiles_pending_family_drift_once_new_traces_arrive or skips_recompile_and_publish_without_new_candidates'`

Current status:

- source now matches the intended cron-only contract: a trainer cycle that drains fresh queued
  traces should not require a separately supplied run family to compile and publish
- a fresh live AKS run is still required to confirm that the queue-drain-only failure mode is gone

## Queue Duplicate and Summary Follow-up

The next live run after the cron-only publish fix exposed two narrower issues in the queue/import
surface:

- `repo_rag_turn_trace_enqueue_batch.json` generated by the trusted deployment handoff still
  omitted item-level and top-level prompt snapshots (`question`, `original_prompt`,
  `reformulated_prompt`), even though the underlying queue-item payloads already carried them.
- `processed/repo-rag-training/` showed duplicate imports for the same logical trace batch:
  one series from the worker's direct Azure queue handoff and a second series from the trusted
  deployment handoff re-uploading the same exported traces.

Root causes:

- The deployment script's trusted batch handoff summary wrote only the family-signal fields and
  never mirrored prompt snapshots into `handoff_items` or the batch-level representative summary.
- The same deployment script only skipped already-completed worker handoffs when
  `repo_rag_turn_trace_enqueue_batch.json` or `repo_rag_turn_trace_import_batch.json` already
  existed and were populated. Older worker surfaces could still set `repo_rag_backend.json`
  to `trace_queued=true` / `trace_handoff_status=queued` without that batch summary, which let the
  trusted handoff requeue the same batch.
- Trainer-side queue drain did not yet suppress duplicate logical queue items inside the same drain
  cycle, so when both queue producers fired the second copy still became another `processed/...`
  blob.

Source-level fixes now landed:

- `drain_trace_queue(...)` now derives a stable logical dedupe key per queue item and skips later
  duplicates in both Azure Blob + Queue mode and filesystem mode.
- Worker-side `trace-enqueue` calls now pass `--batch-name`, preserving stronger lineage for
  trainer-side dedupe and audit surfaces.
- The trusted deployment handoff script now:
  - recognizes already successful worker queue/import handoff from `repo_rag_backend.json`
    in addition to the batch summary files
  - mirrors `question`, `original_prompt`, and `reformulated_prompt` into `handoff_items`
  - writes batch-level representative prompt snapshots (`*_values`) alongside the family-signal
    summary.

Verification executed for those follow-up fixes:

- `uv run python -m compileall src tests` — `pass`
- `uv run pytest tests/test_runtime_artifacts_azure.py -k 'queue_trace_record_and_drain_trace_queue_use_azure_blob_queue or skips_duplicate_logical_azure_items'` — `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py` — `pass`
- `uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`
- `cd ../dataset && .venv/bin/pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py -k 'batches_turn_traces_for_queue_handoff'` — `pass`
- `cd ../dataset && .venv/bin/pytest tests/unit/test_deployment_script_template_regressions.py -k 'trusted_trace_handoff_after_rehydration'` — `pass`

Current status:

- Source now suppresses duplicate logical queue imports inside one trainer drain cycle.
- Source now preserves prompt snapshots in the trusted deployment handoff batch summary.
- A fresh live AKS run is still required to confirm two things together:
  - `processed/repo-rag-training/` no longer receives duplicate logical copies of one batch
  - `repo_rag_turn_trace_enqueue_batch.json` in uploaded artifacts now exposes prompt snapshots
    at both top-level and per-item surfaces.

## Remote Reset Follow-up

The next live review exposed one more cold-start violation after operators deleted
`repo-rag-training-families` from blob:

- worker exported and queued the whole trace batch correctly
- trainer drained and processed the queue correctly
- publish completed, but the published family-state collapsed to a single family that reflected
  only one final trace step instead of the full batch

The most plausible root cause was stale local trainer cache reuse:

- `_prepare_local_trainer_family_cache(...)` still preferred an existing local
  `artifacts/trainer/family-state.json` + `artifacts/trainer/families/` cache before checking
  whether any remote family-state version still existed
- after operators deleted remote family-state versions, the next queue-triggered cycle could still
  reuse an old local cache instead of performing the intended from-scratch rebuild

Source-level fix now landed:

- queue-triggered cycles with fresh imported traces no longer reuse local trainer cache when
  `fetch_remote_family_state(...)` reports that no remote family-state version exists
- in that scenario the trainer now clears the stale local family cache and rebuilds from
  processed/seed traces before materializing new candidates

Verification executed for the fix:

- `uv run python -m compileall src tests` — `pass`
- `uv run pytest tests/test_utilities.py -k 'prepare_local_trainer_family_cache or run_trainer_cycle'` — `pass`
- `uv run pytest tests/test_repository_rag_bdd.py` — `pass`
- `uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`

Current status:

- source now matches the intended operator contract for remote family-state deletion:
  a queue-triggered cycle should not silently reuse stale local family cache when the remote
  family-state has been removed
- a fresh live AKS run is still required to confirm that the next cold-start publish materializes
  the whole imported batch instead of one stale-family carry-forward
