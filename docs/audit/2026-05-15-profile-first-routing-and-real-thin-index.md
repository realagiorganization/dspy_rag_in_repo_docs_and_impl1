# 2026-05-15 Profile-First Routing And Real Thin Index

## Scope

This note records the source-level correction that followed the latest live trainer publish where:

- prompt-family routing still leaned too heavily on prompt-string similarity, and
- `repo-rag-training-families` claimed `family_state_layout = "thin-index"` while the published
  `family-state.json` still carried large inline family payloads.

## Changes

1. `src/repo_rag_lab/training_samples.py`
   - routing now treats family-profile overlap as the primary signal;
   - prompt similarity remains as a secondary precision prior instead of the dominant gate;
   - the overlap calculation now uses shared-anchor coverage, avoiding the old empty/empty
     constraint-overlap false positive.
2. `src/repo_rag_lab/training_samples.py`
   - persisted `family-state.json` entries no longer include inline:
     - `family_father_record`
     - `family_runtime_artifact`
     - `family_records`
     - `context_groups`
   - the thin index now keeps only routing summaries, metrics, counts, and per-family paths.
3. The same code and tests were mirrored into
   `../dataset/submodules/dspy_rag_in_repo_docs_and_impl1`.

## Verification

Configured checks touched by this change:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_training_samples.py -k 'resolve_prompt_family_support or thin_index or thin-index or prompt_profile'`

Executed in this turn:

- `uv run pytest tests/test_training_samples.py -k 'resolve_prompt_family_support or thin_index or thin-index or prompt_profile'` — pass
- `uv run python -m compileall src tests` — pass
- `cd ../dataset/submodules/dspy_rag_in_repo_docs_and_impl1 && uv run pytest tests/test_training_samples.py -k 'resolve_prompt_family_support or thin_index or thin-index or prompt_profile'` — pass
- `cd ../dataset/submodules/dspy_rag_in_repo_docs_and_impl1 && uv run python -m compileall src tests` — pass

## Current Status

- Source now reflects the intended routing bias: family-profile first, prompt-surface similarity
  second.
- Source now reflects a genuinely thin `family-state.json` contract at persistence time.
- Live validation against a new trainer publish is still required before claiming the deployed
  pipeline already matches the new source behavior.
