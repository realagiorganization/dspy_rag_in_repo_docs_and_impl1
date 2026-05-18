# SQLite Family Index Migration

Date: `2026-05-17`

## Change

The generated prompt-family routing index no longer uses `family-state.json`.

The active generated index is now:

- `artifacts/trainer/family-index.sqlite3`

The detailed family payloads remain file-backed:

- `families/<prompt_family_id>/family.json`
- `families/<prompt_family_id>/father.json`
- `families/<prompt_family_id>/records/*.json`

## Why

The JSON index still forced the runtime to:

1. download or read one growing monolithic blob
2. parse the entire JSON document
3. then run the already-linear family scoring pass

SQLite removes the giant-JSON transport layer from the hot path and now also backs a real
shortlist / top-k routing step before rich family scoring.

## Implemented in this turn

- trainer persistence writes the routing index through SQLite
- remote family publish/fetch uploads and restores the versioned SQLite index blob
- proxy/runtime path resolves the SQLite family index first
- runtime family lookup now uses `coarse shortlist -> rich score on top-k` instead of one full
  rich scan across every family
- legacy callers that still point at `family-state.json` can resolve the adjacent generated
  SQLite index during migration

## Verification

Executed:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_training_samples.py tests/test_runtime_artifacts_azure.py tests/test_codex_proxy.py tests/test_dspy_training.py -q`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag verify-surfaces`
- `make files-sync`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make quality`

Observed:

- trainer-family materialization passed against the SQLite index path
- Azure family publish/fetch passed with a binary `family-index.sqlite3` blob
- proxy family-registry and family-index fallback tests passed against the migrated path
- SQLite-backed lookup now shortlists families before running the expensive rich similarity pass
- regenerated `FILES.md` / `FILES.csv` include the new audit notes and stay aligned with the
  tracked tree
- `make quality` completed successfully with `371 passed`, `3 skipped`, and total coverage `82%`

Not yet run in this turn:

- live AKS / blob verification after a new trainer cycle
