# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 17

## Scope

- Remove champion-named fields from remote family-state upload/fetch payloads.
- Keep the mirrored `champion-index.json` file only as storage compatibility, not as the active
  payload contract.

## Contract status in this turn

The remote family-state API contract is now narrower and more family-first:

1. `upload_remote_family_state(...)` now returns only `family_state_*` fields.
2. `fetch_remote_family_state(...)` now returns only `family_state_*` fields.
3. The compatibility `champion-index.json` file is still mirrored on disk and in blob storage, but
   it is no longer advertised as the active remote-family-state payload surface.

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Remote family-state runtime code:
  - `src/repo_rag_lab/runtime_artifacts.py`
- Remote family-state tests:
  - `tests/test_runtime_artifacts_azure.py`

## What is implemented now

### 1. Upload payloads are family-state only

`upload_remote_family_state(...)` now emits:

- `family_state_container`
- `family_state_version`
- `remote_family_state_blobs`
- `remote_family_member_blobs`
- `family_state_path`

and no longer emits parallel champion-named payload aliases.

### 2. Fetch payloads are family-state only

`fetch_remote_family_state(...)` now emits:

- `family_state_found`
- `family_state_container`
- `family_state_version`
- `family_state_blob`
- `family_state_path`

while still reconstructing the cached mirrored `champion-index.json` file under the remote cache
directory for backward compatibility.

### 3. Compatibility survives in storage, not in the primary payload

This turn does not remove the mirrored `champion-index.json` file from:

- local `remote-family-state/` cache directories
- versioned blob uploads inside `repo-rag-training-families`
- current blob metadata fields that still mention `current_champion_index_blob`

But callers of the direct upload/fetch helpers now get a cleaner family-first payload contract.

## What is not implemented yet

- repo-side helper wrappers and several machine payloads still mirror `champion_*` aliases
- aggregate `family-state.json` still coexists with the newer per-family replay-set mirror
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

The remote family-state path is no longer dual-advertised as both family-state and champion-state.
Storage compatibility remains, but the helper payload contract now points callers only at the
family-state naming.
