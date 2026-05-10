# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 5

## Scope

- Move family artifact compilation from “recompile every family” to “recompile only dirty
  families, carry clean families forward”.
- Surface dirty-family state explicitly in trainer summaries and pending-recompile decisions.

## Contract status in this turn

The repository now advances the family-first contract in three more concrete ways:

1. Family state persists a `family_needs_recompile` flag per prompt family.
2. Trainer-side family artifact compilation now recompiles only dirty families and carries clean
   family artifact references forward from the latest family-artifact registry.
3. Trainer pending-recompile detection now treats dirty-family flags as a direct reason to
   recompile instead of waiting only for published-bundle lineage drift.

This means the local trainer now behaves much closer to the agreed contract: “change only the
family that changed”, while still publishing one monolithic bundle.

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Runtime / trainer code:
  - `src/repo_rag_lab/training_samples.py`
  - `src/repo_rag_lab/dspy_training.py`
  - `src/repo_rag_lab/runtime_artifacts.py`
  - `src/repo_rag_lab/utilities.py`
- Tests:
  - `tests/test_training_samples.py`
  - `tests/test_dspy_training.py`
  - `tests/test_utilities.py`

## What is implemented now

### 1. Dirty-family state in persisted family payloads

`materialize_training_candidates()` now marks touched families with `family_needs_recompile=true`.
The compact family-state summary now reports `dirty_family_count` and `dirty_family_ids`, and the
same fields are mirrored into the trainer-candidate summary payload.

### 2. Dirty-only family artifact compilation

`train_repository_program()` now reuses the latest persisted `family_artifact_registry` and only
recompiles families whose state is marked dirty or whose artifact is missing. Clean families carry
their existing artifact references forward into the new bundle metadata instead of being rebuilt
again.

Successful family artifact handling writes back into family state:

- `family_runtime_artifact`
- `family_needs_recompile=false`

### 3. Pending recompile respects dirty-family flags

Trainer-side pending recompile detection now prefers explicit dirty-family state. A family can now
force recompilation even before bundle-lineage drift is computed, which aligns better with the
target “family changed -> family recompile” contract.

## What is not implemented yet

- the global compile-facing DSPy program still recompiles from the merged dataset even when only a
  subset of families changed
- `repo-rag-training-families` is still not the active remote family-state container
- compatibility `champion_*` aliases still exist in repo and dataset wiring
- post-run traces still do not carry the final real execution `hits / total`
- live AKS verification of the new dirty-family runtime path still has not been run

## Verification executed in this turn

Targeted checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_training_samples.py tests/test_dspy_training.py tests/test_utilities.py -q`
  - `pass` (`100 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_runtime_artifacts_azure.py tests/test_codex_proxy.py -q`
  - `pass` (`20 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/training_samples.py src/repo_rag_lab/dspy_training.py src/repo_rag_lab/runtime_artifacts.py src/repo_rag_lab/utilities.py tests/test_dspy_training.py tests/test_utilities.py`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/codex_proxy.py src/repo_rag_lab/runtime_artifacts.py tests/test_codex_proxy.py tests/test_runtime_artifacts_azure.py`
  - `pass`

Repository-native baseline checks executed in this turn:

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
- live deployment / AKS validation: not run in this turn
- UI / browser verification: not applicable in-repo and not run

## Current conclusion

The local repository now has a real dirty-family trainer loop:

- families become dirty when new traces touch them
- dirty families recompile
- clean families carry forward their runtime artifacts
- successful family compile clears the dirty flag

The remaining bottlenecks are now the global compile layer and the live deployment path, not the
absence of family-local trainer state.
