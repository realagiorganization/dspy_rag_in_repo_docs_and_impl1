# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 10

## Scope

- Promote family replay-set members from implicit trainer residue to explicit family-state data.
- Mirror those replay-set members into the remote `repo-rag-training-families` container as
  first-class per-family files.

## Contract status in this turn

The repository now advances the family-first contract in one more concrete way:

1. Persisted family state now carries a `family_records` replay set for each prompt family.
2. Candidate materialization now upserts each supported imported trace into that replay set instead
   of only refreshing one runtime/father summary record.
3. Dirty-family compilation now consumes `family_records` before it falls back to context-group,
   runtime, father, or compatibility champion records.
4. Remote family-state upload/fetch now mirrors per-family `family.json`, `father.json`, and
   `records/<snapshot>.json` members under each versioned family directory.

This means the remote family store and the local family compile path are now both shaped around
replay-set members, not only around one carry-forward family summary.

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Trainer/runtime code:
  - `src/repo_rag_lab/training_samples.py`
  - `src/repo_rag_lab/runtime_artifacts.py`
  - `src/repo_rag_lab/dspy_training.py`
- Tests:
  - `tests/test_training_samples.py`
  - `tests/test_runtime_artifacts_azure.py`
  - `tests/test_dspy_training.py`
- Generated surfaces refreshed in this turn:
  - `FILES.md`
  - `FILES.csv`
  - `publication/exploratorium_translation/generated/exploratorium-content.tex`
  - `publication/exploratorium_translation/generated/exploratorium-manifest.json`

## What is implemented now

### 1. Replay-set records are now explicit family-state members

Trainer-side family payloads now persist replay members under `family_records`, and those members
survive family-state load/save cycles in normalized deduplicated form.

### 2. Family compile now sees replay sets, not only one summary record

The family-scoped DSPy compile path now reads replay-set members before compatibility fallbacks.
That makes dirty-family compile behavior depend on the accumulated family dataset instead of a
single runtime/champion summary object.

### 3. Remote family-state mirrors now expose concrete family directory members

Each remote family-state upload now writes:

- `versions/<family_state_version>/families/<prompt_family_id>/family.json`
- `versions/<family_state_version>/families/<prompt_family_id>/father.json`
- `versions/<family_state_version>/families/<prompt_family_id>/records/<snapshot>.json`

Remote fetch reconstructs the same cache tree locally, so the worker-side family mirror already
looks like a versioned family directory layout rather than one flat index blob.

## What is not implemented yet

- the aggregate `family-state.json` / `champion-index.json` file is still preserved as a
  compatibility-backed source of truth beside the newer `records/*.json` mirror
- dirty-family cycles still rebuild the global DSPy object after family artifact compile
- post-run traces still do not carry the final real execution `hits / total`
- live AKS validation of the newer replay-set family mirror still has not been run
- complete removal of champion alias naming from repo and dataset wiring has not happened yet

## Verification executed in this turn

Targeted checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_dspy_training.py tests/test_training_samples.py tests/test_runtime_artifacts_azure.py -q`
  - `pass` (`72 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/training_samples.py src/repo_rag_lab/runtime_artifacts.py src/repo_rag_lab/dspy_training.py tests/test_dspy_training.py tests/test_runtime_artifacts_azure.py`
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

The family-first contract now has a stronger data shape:

- local trainer state has explicit family replay members
- dirty-family compile reads those replay members
- remote family-state storage mirrors those replay members as separate files

The next meaningful gap is no longer “where do replay-set members live.” It is “how does the
runtime and post-run handoff use measured family quality and final real `hits / total` instead of
placeholder per-turn mediation success.”
