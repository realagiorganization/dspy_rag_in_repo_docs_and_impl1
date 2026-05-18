# Thin SQLite Family Index

Date: `2026-05-18`

## Change

The trainer family index remains SQLite-backed, but it no longer stores one duplicated rich
`payload_json` blob per family entry.

The generated hot-path artifact is still:

- `artifacts/trainer/family-index.sqlite3`

The detailed family payloads still live outside the index:

- `families/<prompt_family_id>/family.json`
- `families/<prompt_family_id>/father.json`
- `families/<prompt_family_id>/records/*.json`

## What Changed

- removed the duplicated `payload_json` column from new SQLite index writes
- kept legacy SQLite read compatibility so older published indexes can still be loaded
- stored routing summaries and term stats as explicit SQLite columns instead of one duplicated JSON
  payload blob
- normalized the SQLite metadata kinds away from the old champion/family-state labels:
  - `record_kind = repo-rag-trainer-family-index`
  - `family_state_kind = repo-rag-trainer-family-index`
- preserved direct `write_family_index_payload(...)` workflows by materializing sidecar
  `family.json` / `father.json` / `records/*.json` files when callers pass already-hydrated family
  payloads

## Why

The previous SQLite migration still carried too much duplication inside the index:

- every family row stored one rich `payload_json`
- the index therefore remained partly "fat", only wrapped in SQLite
- the metadata still advertised the old champion/family-state kinds even though the repo had
  already moved off `family-state.json`

This turn makes the SQLite index align with the intended contract:

- SQLite is the routing index
- detailed family payloads stay file-backed
- the index is thin enough to avoid replaying rich family blobs inside the hot-path artifact

## Verification

Executed in this turn:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_training_samples.py tests/test_runtime_artifacts_azure.py tests/test_utilities.py -q`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make quality`

Observed:

- targeted SQLite family-index suites passed: `121 passed`
- utilities + repository BDD suite passed: `62 passed`
- smoke test passed
- Rust build passed
- `make quality` passed with:
  - `372 passed`
  - `3 skipped`
  - total coverage `81.64%`

## Scope Notes

- This note covers repository-local correctness of the thin SQLite index shape and verification
  surfaces.
- It does **not** claim a fresh live AKS trainer deployment was run on top of this exact change in
  the same turn.
