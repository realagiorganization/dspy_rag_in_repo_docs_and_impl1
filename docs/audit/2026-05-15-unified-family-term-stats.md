# 2026-05-15 Unified Family Term Stats

- Scope: collapse family profile counts and normalized weights into one shared term-stats surface.
- Preceding note: `2026-05-15-family-profile-stability-thresholds.md`

## What Changed

- Prompt-family routing state now stores per-term profile evidence in unified mappings:
  - `family_prompt_profile_term_stats`
  - `family_command_pattern_term_stats`
  - `family_constraint_term_stats`
- Each term entry now carries both:
  - `count`
  - `weight`
- The legacy list-style routing summaries are still present:
  - `family_prompt_profile_terms`
  - `family_command_pattern_summary`
  - `family_constraint_summary`
  but they are derived views only.
- Backward compatibility remains in place for older persisted `*_counts` payloads during family-state
  hydration.

## Why This Mattered

- Separate count-only and weight-only dictionaries were more likely to drift apart and made family
  profile inspection harder.
- One shared stats object keeps all term evidence in one place while preserving both:
  - raw family evidence strength (`count`)
  - normalized routing contribution (`weight`)

## Verification

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_training_samples.py -k 'profile_terms_ignore_one_off_noise or prefers_family_profile_over_surface_similarity or can_use_family_profile_summaries or strips_execution_envelope_from_family_father'`

## Current Status

- Source-level verification is green for unified term stats.
- A new live run is still needed to confirm newly published `family-state.json` blobs expose the new
  `*_term_stats` fields as expected.
