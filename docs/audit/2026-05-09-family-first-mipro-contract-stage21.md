# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 21

## Scope

- Remove active mirrored `champion-index.json` writes from the family-first local and remote state
  path.
- Preserve only fallback reads for older `champion-index.json` snapshots and older remote
  `current_champion_index_blob` metadata.

## Contract status in this turn

The family-first path is now stricter about what counts as active state:

1. Trainer materialization writes only `artifacts/trainer/family-state.json`.
2. Remote family-state upload writes only the versioned `family-state.json` blob plus
   family-directory members; it no longer uploads a mirrored versioned `champion-index.json`.
3. Remote family-state fetch restores only `family-state.json` into the local cache tree.
4. Proxy family-state resolution prefers `family-state.json`; direct `champion-index.json` lookup
   now exists only as a fallback for older local snapshots.
5. Older local and remote champion-named snapshots still remain readable so migration compatibility
   is preserved.

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Latest audit pointer:
  - `docs/audit/README.md`
- Runtime/trainer code:
  - `src/repo_rag_lab/azure_artifacts.py`
  - `src/repo_rag_lab/runtime_artifacts.py`
  - `src/repo_rag_lab/codex_proxy.py`
  - `src/repo_rag_lab/training_samples.py`
  - `src/repo_rag_lab/utilities.py`
- Tests:
  - `tests/test_runtime_artifacts_azure.py`
  - `tests/test_codex_proxy.py`
  - `tests/test_training_samples.py`
  - `tests/test_dspy_training.py`
  - `tests/test_utilities.py`

## What is implemented now

### 1. Local trainer state is family-state-only on new writes

`materialize_training_candidates(...)` now writes only `family-state.json`. It still accepts an
older local `champion-index.json` as migration input when the new family-state file is absent, but
it no longer mirrors the freshly generated payload back into that old filename.

### 2. Remote family-state uploads stop republishing champion mirrors

`upload_remote_family_state(...)` now publishes:

- `versions/<family_state_version>/family-state.json`
- `versions/<family_state_version>/families/<prompt_family_id>/family.json`
- `versions/<family_state_version>/families/<prompt_family_id>/father.json`
- `versions/<family_state_version>/families/<prompt_family_id>/records/<snapshot>.json`
- `current.json`

It no longer uploads a versioned `champion-index.json` mirror for new state snapshots.

### 3. Remote family-state fetch restores only the active cache path

`fetch_remote_family_state(...)` now restores only the active local cache tree under
`artifacts/trainer/remote-family-state/<family_state_version>/...`, with `family-state.json` as
the aggregate snapshot. Older remote `current.json` blobs that still point at
`current_champion_index_blob` remain supported during fetch.

### 4. Proxy resolution is family-state-first without reintroducing mirrored state

`_resolve_family_state_path(...)` now prefers only `family-state.json` in the bundle/repository
roots. The old `champion-index.json` path is checked only as a direct legacy fallback when the new
family-state file is absent.

## What is not implemented yet

- aggregate `family-state.json` is still the compatibility-backed source of truth beside the
  per-family replay-set mirror
- deeper internal `family_champion_*` structural naming inside the trainer payload model still
  exists even though active storage is family-first
- live AKS validation of the full family-first handoff still has not been run in this turn
- notebook execution, coverage, UI/browser verification, and live deployment validation were not
  run in this turn

## Verification executed in this turn

Targeted checks executed before the repository-wide sync:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_runtime_artifacts_azure.py tests/test_training_samples.py tests/test_dspy_training.py tests/test_codex_proxy.py tests/test_utilities.py -q`
  - `pass` (`124 passed, 2 skipped`)
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/azure_artifacts.py src/repo_rag_lab/runtime_artifacts.py src/repo_rag_lab/codex_proxy.py src/repo_rag_lab/training_samples.py src/repo_rag_lab/utilities.py tests/test_runtime_artifacts_azure.py tests/test_training_samples.py tests/test_dspy_training.py tests/test_codex_proxy.py tests/test_utilities.py`
  - `pass`

Repository-wide sync and verification commands were run after the doc updates. The `make` targets
were executed with `UV_CACHE_DIR=/tmp/uvcache` because the sandboxed default `uv` cache path under
`~/.cache/uv` was not writable in this session.

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`45 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache make files-sync`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache make exploratorium-sync`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache make verify-surfaces`
  - `pass`

## Current conclusion

The family-first migration no longer carries `champion-index.json` as a live mirrored state
surface. New local and remote writes are now family-state-only, while older champion-named
snapshots remain readable as migration input. That narrows the remaining compatibility layer to
legacy reads and deeper internal structure names instead of duplicated active state files.
