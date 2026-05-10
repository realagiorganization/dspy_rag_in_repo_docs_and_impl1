# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 7

## Scope

- Start exposing real per-family directories inside the remote family-state container instead of
  only storing one shared family-state index blob.
- Keep the stage-6 family-state-first container contract and champion compatibility aliases
  intact.

## Contract status in this turn

The repository now advances the family-first contract in one more concrete way:

1. Every remote family-state upload still writes the aggregate `family-state.json` snapshot, but
   it now also writes one versioned `family.json` blob per prompt family under
   `versions/<family_state_version>/families/<prompt_family_id>/`.
2. Remote family-state fetch now reconstructs the same family-directory shape in the local cache,
   downloading those per-family blobs when they exist and synthesizing them from the aggregate
   snapshot when the remote version is older.

This means `repo-rag-training-families` is no longer only “one container with one shared state
blob”. It now already starts to expose versioned family directories, which is closer to the
intended long-term storage contract.

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Runtime / storage code:
  - `src/repo_rag_lab/runtime_artifacts.py`
- Tests:
  - `tests/test_runtime_artifacts_azure.py`

## What is implemented now

### 1. Versioned family-directory mirror in remote family-state storage

`upload_remote_family_state()` now mirrors each family payload into:

- `versions/<family_state_version>/families/<prompt_family_id>/family.json`

while still writing:

- `versions/<family_state_version>/family-state.json`
- `versions/<family_state_version>/champion-index.json`
- `current.json`

### 2. Local cache reconstruction for remote family directories

`fetch_remote_family_state()` now materializes:

- cached aggregate family-state snapshot
- cached champion-index alias
- cached per-family `families/<prompt_family_id>/family.json` tree

When the remote snapshot predates the new family-directory mirror, fetch falls back to synthesizing
those cached family files from the aggregate family-state payload instead of failing.

## What is not implemented yet

- the remote family container still does not store full replay-set traces per family
- dataset / AKS wiring still uses several champion-named env variables and surfaces
- the global compile-facing DSPy program still recompiles from the merged dataset even when only a
  subset of families changed
- post-run traces still do not carry the final real execution `hits / total`
- live AKS verification of the new remote family-directory contract still has not been run

## Verification executed in this turn

Targeted checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_runtime_artifacts_azure.py -q`
  - `pass` (`13 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/runtime_artifacts.py tests/test_runtime_artifacts_azure.py`
  - `pass`

Repository-native baseline checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_runtime_artifacts_azure.py tests/test_utilities.py tests/test_codex_proxy.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`67 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/azure_artifacts.py src/repo_rag_lab/runtime_artifacts.py tests/test_runtime_artifacts_azure.py tests/test_utilities.py tests/test_codex_proxy.py`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
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

The remote family-state store now has two layers:

- one aggregate snapshot for compatibility and coarse state transfer
- one versioned family-directory mirror that starts to reflect the intended family-native storage
  model

The remaining structural gap is no longer “families do not exist remotely at all”; it is now
“family directories exist, but they still do not hold the full replay-set contract yet.”
