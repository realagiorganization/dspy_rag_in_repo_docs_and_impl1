# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 12

## Scope

- Stop rebuilding the global DSPy program on dirty-family trainer cycles when the compile-facing
  merged dataset did not actually change.
- Anchor that global carry-forward decision to persisted training/benchmark example signatures
  instead of to `dirty_family_count` alone.

## Contract status in this turn

The repository now advances the family-first contract one step further:

1. Global DSPy carry-forward no longer depends only on `dirty_family_count=0`.
2. The latest global artifact can now be reused during dirty-family cycles when both of these are
   true:
   - the previous global metadata already recorded training and benchmark example signatures
   - those signatures still match the newly materialized compile-facing dataset
3. Dirty-family cycles can therefore recompile only family-local runtime artifacts without
   automatically paying for a full global DSPy compile.

This changes the previous stage-11 limitation from “dirty-family cycles always rebuild the global
object” to “older metadata without signatures still forces one transitional full compile.”

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
- DSPy training/runtime code:
  - `src/repo_rag_lab/dspy_training.py`
- DSPy training tests:
  - `tests/test_dspy_training.py`

## What is implemented now

### 1. Global carry-forward now keys off compile-facing dataset signatures

`train_repository_program()` now computes stable signatures for:

- the ordered training example set
- the ordered benchmark example set

and persists them into global DSPy metadata.

### 2. Dirty-family cycles can now skip the global compile

When the latest global metadata contains matching signatures for the same training/benchmark set,
the new run now copies the previous global `program.json` forward even if lineage still reports
dirty families. Family-local runtime artifacts can therefore be recompiled without forcing another
global compile in the same cycle.

### 3. Older metadata still triggers one transitional compile

If the previous global metadata does not yet contain those signatures, the repository still falls
back to a fresh global compile. That preserves compatibility with already-published older bundles
and makes the carry-forward path activate from the next compatible run onward.

## What is not implemented yet

- aggregate `family-state.json` is still the compatibility-backed source of truth beside the newer
  per-family `records/*.json` mirror
- complete removal of compatibility `champion-*` naming from repo and dataset wiring has not
  happened yet
- live AKS validation of this signature-gated dirty-family carry-forward path has not been run in
  this turn
- notebook execution, coverage, UI/browser verification, and live deployment validation were not
  run in this turn

## Verification executed in this turn

Targeted checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_dspy_training.py -q`
  - `pass` (`33 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/dspy_training.py tests/test_dspy_training.py`
  - `pass`

Repository-native checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_dspy_training.py tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`78 passed`)
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

The family-first trainer/runtime split is now closer to the intended steady state:

- dirty families can still recompile their own runtime artifacts
- the global DSPy object is no longer rebuilt only because dirty-family flags exist
- the remaining transition caveat is older metadata that predates training/benchmark signatures

The next highest-signal gap is live validation: confirm in a real AKS trainer cycle that the new
signature-gated global carry-forward survives the full queue, family-state, bundle, and publish
path.
