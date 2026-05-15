# 2026-05-15 Family Profile Stability Thresholds

- Scope: keep prompt families from diluting their routing profiles with one-off trace terms.
- Preceding note: `2026-05-15-trainer-publish-backlog-recovery.md`

## What Changed

- `training_samples.py` no longer treats the live family routing profile as a simple union of all
  prompt/profile terms ever seen inside a family.
- Each family now persists frequency maps for:
  - `family_prompt_profile_term_counts`
  - `family_command_pattern_counts`
  - `family_constraint_counts`
- The active routing summaries:
  - `family_prompt_profile_terms`
  - `family_command_pattern_summary`
  - `family_constraint_summary`
  are now derived from stable top-k terms instead of from raw union state.
- Stability is family-size aware:
  - one-record families can still surface first-pass profile terms;
  - larger families require repeated evidence before a term enters the active routing summary.

## Why This Mattered

- A family could previously accumulate arbitrary one-off words from intermediate traces and then
  expose them in the live routing summary.
- That made long-lived families gradually easier to match for the wrong reason: not because their
  core task intent got stronger, but because their profile surface kept expanding.

## Verification

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_training_samples.py -k 'profile_terms_ignore_one_off_noise or prefers_family_profile_over_surface_similarity or can_use_family_profile_summaries or strips_execution_envelope_from_family_father'`

## Current Status

- Source-level verification is green for the stability-threshold path.
- A new live run is still needed to confirm the published `family-state.json` now exposes the
  narrowed routing summaries expected from those frequency maps.
