# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 16

## Scope

- Remove repo-side Azure config fallback to champion-named family-state container env vars.
- Keep compatibility only in mirrored local state and helper aliases, not in env resolution.

## Contract status in this turn

The family-state storage contract is now stricter inside the repo runtime itself:

1. `AzureArtifactConfig.from_env()` resolves family-state storage only from
   `REPO_RAG_FAMILY_STATE_CONTAINER` / `DATASET_REPO_RAG_FAMILY_STATE_CONTAINER`.
2. `REPO_RAG_CHAMPION_CONTAINER` / `DATASET_REPO_RAG_CHAMPION_CONTAINER` no longer influence
   repo-side Azure config resolution.
3. The remaining `champion_*` compatibility layer is now limited to mirrored file names, payload
   aliases, and wrapper helpers.

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Azure config/runtime code:
  - `src/repo_rag_lab/azure_artifacts.py`
- Azure config tests:
  - `tests/test_runtime_artifacts_azure.py`

## What is implemented now

### 1. Champion env vars no longer participate in Azure config resolution

`AzureArtifactConfig.from_env()` now ignores:

- `REPO_RAG_CHAMPION_CONTAINER`
- `DATASET_REPO_RAG_CHAMPION_CONTAINER`

and resolves the family-state container only from:

- `REPO_RAG_FAMILY_STATE_CONTAINER`
- `DATASET_REPO_RAG_FAMILY_STATE_CONTAINER`
- the default `repo-rag-training-families`

### 2. The active Azure contract is family-state only

Repo-side helper resolution now treats the family-state env names as the only active env contract
for remote trainer state. Champion naming no longer changes the resolved storage target even when
those old env vars are still present.

### 3. Compatibility remains in narrower places only

This turn does not remove:

- mirrored `champion-index.json`
- mirrored `champion_*` machine payload keys
- compatibility wrapper helpers such as `repo_rag_champion_container(...)`

But those layers no longer control env-based storage selection.

## What is not implemented yet

- mirrored local/state payload aliases still use `champion-*` naming in several places
- aggregate `family-state.json` still coexists with the newer per-family replay-set mirror
- live AKS validation of the full family-first handoff still has not been run in this turn
- notebook execution, coverage, UI/browser verification, and live deployment validation were not
  run in this turn

## Verification executed in this turn

Targeted checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_runtime_artifacts_azure.py -q`
  - `pass` (`14 passed`)

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

## Current conclusion

The family-first storage contract now controls both ends of the environment/config path:

- dataset / AKS deploy surfaces already emit only family-state container env vars
- repo-side Azure config resolution now ignores champion container env vars too

The remaining transition work is no longer about which container env name wins. It is now about
removing the narrower file/payload aliases and proving the full path in a live AKS run.
