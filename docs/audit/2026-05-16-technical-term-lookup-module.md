# 2026-05-16 Technical Term Lookup Module

Prompt-family term extraction now lives in a dedicated module instead of being embedded directly in
`training_samples.py`.

## What Changed

- Added `src/repo_rag_lab/term_extraction.py`.
- Moved prompt stopwords, themed technical-term groups, and the active profile-term extractor into
  that module.
- The extractor now uses multiple themed `frozenset` collections plus one flattened hash lookup for
  O(1) exact-term membership while scanning normalized tokens.
- Expanded the themed technical vocabulary beyond repo/runtime terms to include programming
  languages, databases, API/backend vocabulary, data science, neural networks, research/publication
  vocabulary, infrastructure/devops, Linux commands, Windows commands, explicit Kubernetes terms,
  cloud service names, and game-development terminology.
- Trainer routing still falls back to filtered non-technical tokens when the technical lookup does
  not fill the active profile limit.

## Verification

- `uv run pytest tests/test_term_extraction.py tests/test_training_samples.py -k 'profile_terms or surface_similarity'`
- `uv run python -m compileall src tests`
