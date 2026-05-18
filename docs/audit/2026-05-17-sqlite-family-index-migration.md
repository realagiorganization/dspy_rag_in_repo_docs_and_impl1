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
- trainer-side SQLite reads/writes now operate through one local temporary copy and only copy the
  finished bytes back into the artifact path, so the SQLite engine no longer mutates or queries the
  live index directly on the shared trainer PVC

## Live follow-up

On `2026-05-18` the live AKS trainer cycle failed repeatedly before publish with:

- `OperationalError`
- `database is locked`

Observed live command payload:

- `repo-rag trainer-cycle --root /workspace/repo-rag ...`
- image `llmpromptsacr.azurecr.io/repo-rag-runtime:20260518-080657`

The crash happened after the SQLite migration because trainer stored `family-index.sqlite3` on the
shared PVC mount and SQLite was opening that file directly. The fix in this turn keeps the
artifact format as SQLite while moving the actual SQLite engine activity onto one local temporary
copy, then stages the bytes back into the persisted artifact path.

## Verification

Executed:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_training_samples.py tests/test_runtime_artifacts_azure.py tests/test_codex_proxy.py tests/test_dspy_training.py -q`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run pytest tests/test_runtime_artifacts_azure.py tests/test_utilities.py tests/test_training_samples.py -q`
- `uv run repo-rag verify-surfaces`
- `make files-sync`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make quality`

Observed:

- trainer-family materialization passed against the SQLite index path
- Azure family publish/fetch passed with a binary `family-index.sqlite3` blob
- proxy family-registry and family-index fallback tests passed against the migrated path
- SQLite-backed lookup now shortlists families before running the expensive rich similarity pass
- the new SQLite temp-copy regression passes when the old target file is still held open by an
  existing SQLite connection
- regenerated `FILES.md` / `FILES.csv` include the new audit notes and stay aligned with the
  tracked tree
- `make quality` completed successfully with `371 passed`, `3 skipped`, and total coverage `82%`

Not yet run in this turn:

- live AKS / blob verification after a new trainer cycle
