# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 13

## Scope

- Move the primary local trainer-state filename and cache path from champion naming to family-state
  naming.
- Preserve `champion-index.json` as a mirrored compatibility alias and fallback read source for
  older local snapshots.

## Contract status in this turn

The repository now advances the family-first contract on the local storage surface too:

1. Primary local trainer state now lives at `artifacts/trainer/family-state.json`.
2. The older local alias `artifacts/trainer/champion-index.json` is still written beside it.
3. Remote family-state fetch now caches into `artifacts/trainer/remote-family-state/<version>/`.
4. If a local repo still only has `champion-index.json`, trainer materialization now falls back to
   reading it instead of silently discarding the old snapshot.

This makes the local contract match the already-primary remote contract more closely without
breaking older callers, older tests, or older persisted local trainer state.

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Generated repository surfaces:
  - `FILES.md`
  - `FILES.csv`
  - `AGENTS.md.d/FILES.md`
  - `publication/exploratorium_translation/generated/exploratorium-content.tex`
  - `publication/exploratorium_translation/generated/exploratorium-manifest.json`
- Runtime/trainer code:
  - `src/repo_rag_lab/runtime_artifacts.py`
  - `src/repo_rag_lab/training_samples.py`
  - `src/repo_rag_lab/codex_proxy.py`
- Runtime/trainer tests:
  - `tests/test_runtime_artifacts_azure.py`
  - `tests/test_training_samples.py`

## What is implemented now

### 1. Local family-state is now the primary filename

The repository now defaults to:

- `artifacts/trainer/family-state.json`
- `artifacts/trainer/remote-family-state/`

instead of treating champion-named local paths as the primary contract.

### 2. Champion-named local state is still mirrored

Trainer candidate materialization now writes the same payload to:

- `family-state.json`
- `champion-index.json`

when those paths differ, so older compatibility surfaces keep working while the repo transitions.

### 3. Old local snapshots are still accepted

If the primary `family-state.json` file is absent but `champion-index.json` exists, trainer
materialization now reads the champion-named file as fallback input before rewriting both paths.

### 4. Proxy lookup prefers family-state local paths

Proxy-side local family-state resolution now checks both primary `family-state.json` paths and the
older champion alias paths before falling back to remote cache recovery.

## What is not implemented yet

- aggregate `family-state.json` is still the compatibility-backed source of truth beside the newer
  per-family `records/*.json` mirror
- complete removal of `champion-*` naming from repo and dataset wiring has not happened yet
- live AKS validation of the new local `family-state.json` primary path has not been run in this
  turn
- notebook execution, coverage, UI/browser verification, and live deployment validation were not
  run in this turn

## Verification executed in this turn

Targeted checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_training_samples.py tests/test_runtime_artifacts_azure.py tests/test_codex_proxy.py tests/test_utilities.py -q`
  - `pass` (`92 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/runtime_artifacts.py src/repo_rag_lab/training_samples.py src/repo_rag_lab/codex_proxy.py tests/test_runtime_artifacts_azure.py`
  - `pass`

Repository-native checks executed in this turn:

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

Verification categories still not covered in this turn:

- notebook execution: not run in this turn
- coverage: not run in this turn
- UI / browser verification: not run in this turn
- live deployment / AKS validation: not run in this turn

## Current conclusion

The family-first contract is now less contradictory on disk:

- remote storage already preferred family-state naming
- local storage now prefers the same family-state naming
- champion naming remains available only as a mirror and migration fallback

The next highest-signal gap is still the same one at the product boundary: remove the remaining
`champion-*` compatibility layer from repo and dataset wiring, then confirm the new contract in a
real AKS trainer cycle.
