# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 9

## Scope

- Stop recompiling the global DSPy program when no dirty family requires a fresh compile.
- Preserve the existing monolithic bundle contract while reducing one obvious no-op trainer cost.

## Contract status in this turn

The repository now advances the family-first contract in one more concrete way:

1. Trainer now checks whether lineage reports any dirty families.
2. When `dirty_family_count=0` and the latest global DSPy artifact still matches the current
   training path, benchmark path, optimizer, retrieval mode, `top_k`, and LM model, trainer copies
   the previous global `program.json` into the new run directory instead of recompiling it again.
3. The new run metadata records that global artifact as `artifact_source="carried-forward"`.

This means the trainer no longer pays a full global compile for the trivial case “nothing changed
in the family graph, but we still need a fresh run/bundle snapshot.”

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Trainer code:
  - `src/repo_rag_lab/dspy_training.py`
- Tests:
  - `tests/test_dspy_training.py`

## What is implemented now

### 1. Dirty-family-aware global carry-forward

Trainer now has an explicit gate for global carry-forward:

- no dirty family ids
- compatible latest global program exists
- matching training / benchmark / optimizer / retrieval / LM surface

When all of those hold, the new run copies the previous program instead of invoking a new DSPy
compile.

### 2. Metadata distinguishes carried-forward global artifacts

The resulting metadata now marks the global `compiled_program_summary` with:

- `artifact_source="carried-forward"`

so later inspection can tell whether a run paid for a real global compile or only republished a
compatible global artifact.

## What is not implemented yet

- dirty-family cycles still rebuild the global DSPy object
- the remote family container still does not store full replay-set traces per family
- post-run traces still do not carry the final real execution `hits / total`
- live AKS verification of the new family-state / carry-forward path still has not been run
- complete removal of champion alias naming from repo and dataset wiring has not happened yet

## Verification executed in this turn

Targeted checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_dspy_training.py tests/test_training_samples.py tests/test_utilities.py -q`
  - `pass` (`101 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/dspy_training.py tests/test_dspy_training.py`
  - `pass`

Repository-native baseline checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
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

The trainer now has three different levels of reuse:

- clean family runtime artifacts carry forward
- the remote family-state container carries forward versioned family directories
- the global DSPy program can also carry forward when the family graph is unchanged

The remaining global compile problem is narrower now: it only persists for dirty-family cycles, not
for every no-op trainer rerun.
