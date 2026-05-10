# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 18

## Scope

- Remove champion-named lineage fields from newly written remote family-state `current.json`
  snapshots.
- Keep fallback reads for older `current.json` blobs that still contain champion-named metadata.

## Contract status in this turn

The remote family-state snapshot contract is now narrower again:

1. Fresh `current.json` blobs written by `upload_remote_family_state(...)` no longer contain
   `champion_state_kind`.
2. Fresh `current.json` blobs written by `upload_remote_family_state(...)` no longer contain
   `current_champion_index_blob`.
3. `fetch_remote_family_state(...)` still accepts older snapshots that carry
   `current_champion_index_blob`, so the cleanup does not break restore compatibility.

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Remote snapshot runtime code:
  - `src/repo_rag_lab/runtime_artifacts.py`
- Remote snapshot tests:
  - `tests/test_runtime_artifacts_azure.py`

## What is implemented now

### 1. New `current.json` blobs are family-state only

The snapshot metadata written beside remote family-state uploads now keeps:

- `schema_version`
- `family_state_kind`
- `updated_at`
- `current_version`
- `current_family_state_blob`
- family counts

and no longer writes parallel champion-named lineage markers.

### 2. Backward compatibility remains on reads

This turn does not remove the read-side fallback:

- `fetch_remote_family_state(...)` still checks `current_champion_index_blob` when restoring older
  snapshots

So old remote state can still be consumed while newly written state becomes cleaner.

## What is not implemented yet

- repo-side helper wrappers and several machine payloads still mirror `champion_*` aliases
- mirrored `champion-index.json` files still coexist with `family-state.json`
- live AKS validation of the full family-first loop still has not been run in this turn
- notebook execution, coverage, UI/browser verification, and live deployment validation were not
  run in this turn

## Verification executed in this turn

Targeted checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_runtime_artifacts_azure.py -q`
  - `pass` (`14 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`45 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`
- `make files-sync`
  - `pass`
- `make exploratorium-sync`
  - `pass`
- `make verify-surfaces`
  - `pass`

## Current conclusion

The remote family-state path now stays family-first not only in env names and helper payloads, but
also in the newly written `current.json` snapshot itself. Champion naming still survives only where
it is needed for backward-compatible reads and mirrored files.
