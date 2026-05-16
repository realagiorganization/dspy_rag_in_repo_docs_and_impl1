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
- Verification executed for those follow-up fixes:
  - `uv run python -m compileall src tests`
  - `uv run pytest tests/test_dspy_training.py -k 'recompiles_only_dirty_families'`
  - `cd ../dataset && .venv/bin/pytest tests/unit/test_deployment_script_template_regressions.py -k 'trusted_trace_handoff_after_rehydration'`
  - `cd ../dataset && .venv/bin/pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py -k 'batches_turn_traces_for_queue_handoff'`
- A fresh live run is still required to confirm those two fixes in published blob artifacts.
