# 2026-05-16 Profile-Term Selectivity Tightening

The prompt-family routing profile was still too permissive in live family-state snapshots because
the active `family_prompt_profile_terms` surface allowed up to 24 terms and retained too much
recurring conversational filler. Even after the shift to `*_term_stats`, families could still
publish stable-but-generic tokens like `just`, `really`, `needed`, or `whether`, which made some
profiles look broader than their technical intent.

## Changes

- Reduced `_FAMILY_PROMPT_PROFILE_LIMIT` from `24` to `12`.
- Expanded the prompt-profile stopword filter so recurring narrative filler is excluded from the
  active routing profile even when it repeats across traces.
- Kept the term weights unchanged: weights still derive directly from per-family term frequency,
  while the active `family_prompt_profile_terms` summary now stays narrower and more technical.

## Verification

- `uv run pytest tests/test_training_samples.py -k 'profile_terms_ignore_one_off_noise or prefers_family_profile_over_surface_similarity'`
- `uv run python -m compileall src tests`
