# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 6

## Scope

- Move the remote family-state Azure contract from champion-first naming to family-state-first
  naming.
- Keep the existing champion-named env vars, helper names, and blob aliases alive as compatibility
  surfaces during the migration.

## Contract status in this turn

The repository now advances the family-first contract in three more concrete ways:

1. Azure artifact config now resolves `REPO_RAG_FAMILY_STATE_CONTAINER` /
   `DATASET_REPO_RAG_FAMILY_STATE_CONTAINER` as the primary remote family-state surface, with the
   older champion-named env vars kept only as fallback inputs.
2. Remote family-state upload now writes a primary `family-state.json` blob into
   `repo-rag-training-families` while mirroring the same payload into `champion-index.json` for
   compatibility.
3. Remote family-state fetch now reads the family-state-first container/blob contract first while
   still materializing the old local `champion-index.json` cache path for older local callers.

This means the local repository has now crossed the container-contract boundary: family state is
no longer merely a naming preference in local code, it is now the primary remote storage contract
too.

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Runtime / storage code:
  - `src/repo_rag_lab/azure_artifacts.py`
  - `src/repo_rag_lab/runtime_artifacts.py`
- Tests:
  - `tests/test_runtime_artifacts_azure.py`

## What is implemented now

### 1. New primary remote family-state container

`AzureArtifactConfig.from_env()` now resolves `family_state_container` from:

- `REPO_RAG_FAMILY_STATE_CONTAINER`
- `DATASET_REPO_RAG_FAMILY_STATE_CONTAINER`
- legacy champion-named env vars as fallback
- default `repo-rag-training-families`

Compatibility `champion_container` is still populated, but the runtime helpers now resolve the
effective remote container through the new family-state-first surface.

### 2. Family-state-first blob naming with champion aliasing

The versioned blob contract now has a primary `family-state.json` blob and still mirrors the same
payload into `champion-index.json`. `current.json` remains the shared pointer blob.

That gives newer code a family-first path without forcing older consumers to fail immediately.

### 3. Family-state-first fetch/upload wrappers

`upload_remote_family_state()` and `fetch_remote_family_state()` now use the effective family-state
container and family-state blob names as their primary contract. The returned payloads still mirror
the old champion alias keys so existing call sites do not break during the migration.

## What is not implemented yet

- `repo-rag-training-families` still stores one shared family-state snapshot, not a fully
  directory-native replay-set layout per family
- dataset / AKS wiring still uses several champion-named env variables and surfaces
- the global compile-facing DSPy program still recompiles from the merged dataset even when only a
  subset of families changed
- post-run traces still do not carry the final real execution `hits / total`
- live AKS verification of the new remote family-state contract still has not been run

## Verification executed in this turn

Targeted checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_runtime_artifacts_azure.py -q`
  - `pass` (`13 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_runtime_artifacts_azure.py tests/test_utilities.py tests/test_codex_proxy.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`67 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/azure_artifacts.py src/repo_rag_lab/runtime_artifacts.py tests/test_runtime_artifacts_azure.py tests/test_utilities.py tests/test_codex_proxy.py`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`

Repository-native baseline checks executed in this turn:

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

Verification categories still not covered in this turn:

- notebook execution: not run in this turn
- coverage: not run in this turn
- live deployment / AKS validation: not run in this turn
- UI / browser verification: not applicable in-repo and not run

## Current conclusion

The local repository now treats family state as the primary remote object, not only as a local
alias over champion state. The next architectural bottlenecks are:

- turning `repo-rag-training-families` into a fully family-native replay-set store
- removing the remaining champion alias layer from dataset / AKS wiring
- enriching traces with real final `hits / total` so family runtime selection can use actual
  observed performance instead of transitional placeholders
