# 2026-05-16 Active Profile Summary Selectivity

## Context

Live `repo-rag-training-families` output showed that family formation itself was broadly correct,
but the active `family_prompt_profile_terms` summary still admitted broad narrative terms such as
`already`, `contains`, `does`, and `fields`. Those terms diluted routing precision even though the
full family term statistics already contained stronger technical signals like `gif`, `readme`,
`recorder`, `repo`, `script`, and `worktree`.

## Changes

- Kept full `*_term_stats` payloads unchanged as the source of truth for counts and weights.
- Added an explicit active-summary selector in `src/repo_rag_lab/term_extraction.py` that:
  - prefers terms present in the technical lookup categories;
  - penalizes broad narrative/generic terms in `PROFILE_SUMMARY_NARRATIVE_STOPWORDS`;
  - allows active prompt summaries to stay **below** the 12-term ceiling when the remaining
    candidates are only filler/noise.
- Switched `src/repo_rag_lab/training_samples.py` to use that selector for prompt, command, and
  constraint summaries instead of plain count sorting.
- Added targeted tests that reproduce the live failure mode where equal-count narrative terms used
  to displace stronger technical terms.

## Verification

- `uv run python -m compileall src tests` — pass
- `uv run pytest tests/test_term_extraction.py tests/test_training_samples.py -k 'summary_terms or profile_terms_ignore_one_off_noise or prefers_technical_terms_in_active_summary or surface_similarity'` — pass
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py` — pass
- `uv run repo-rag smoke-test` — pass
- `cargo build --manifest-path rust-cli/Cargo.toml` — pass

## Result

The family term statistics remain complete, but the active routing summaries are now intentionally
more selective: technical terms dominate when they are available, and the summary is no longer
forced to fill all 12 slots with low-value narrative vocabulary.
