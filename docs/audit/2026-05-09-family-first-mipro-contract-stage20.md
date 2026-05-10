# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 20

## Scope

- Remove no-longer-used public `champion_*` wrapper helpers from the repo API surface.
- Keep compatibility only in mirrored files and fallback reads for older stored state.

## Contract status in this turn

The family-first migration now reaches the public helper surface too:

1. `repo_rag_champion_container(...)` has been removed.
2. `upload_remote_champion_index(...)` and `fetch_remote_champion_index(...)` have been removed.
3. champion-named blob-name wrapper helpers have been removed.

Runtime behavior does not change in this turn; the deleted helpers were already unused by the
active family-first path.

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Azure/runtime helper code:
  - `src/repo_rag_lab/azure_artifacts.py`
  - `src/repo_rag_lab/runtime_artifacts.py`
- Helper tests:
  - `tests/test_runtime_artifacts_azure.py`

## What is implemented now

### 1. Champion helper wrappers are gone

The repo API surface no longer publishes separate champion-named wrappers for:

- family-state container lookup
- family-state upload wrapper
- family-state fetch wrapper
- champion-named blob-name alias helpers

### 2. Compatibility remains in the data plane, not the helper plane

This turn does **not** remove:

- mirrored `champion-index.json` files
- fallback reads for older `current_champion_index_blob`
- compatibility views such as `summarize_champion_index(...)`

So the repo can still read older stored state, but it stops advertising parallel champion-named
helper APIs for new code to call.

## What is not implemented yet

- mirrored local/state payload aliases still exist in deeper helper layers
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

The compatibility layer has moved one level deeper. Champion naming is still preserved where it is
needed to read older stored state, but it is no longer exposed as a parallel public helper API in
the active repository code.
