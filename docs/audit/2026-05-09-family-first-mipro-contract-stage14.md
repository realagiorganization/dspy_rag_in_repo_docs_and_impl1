# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 14

## Scope

- Move operator-facing trainer diagnostics from champion wording to family wording.
- Keep mirrored `champion_*` payload fields only as compatibility aliases.

## Contract status in this turn

The repository now advances the family-first contract at the operator/diagnostic layer:

1. Pending-recompile reasons now describe the active object as the family set, not the champion
   set.
2. Family drift, family trace-path drift, and family candidate availability are now the primary
   reason strings exposed by trainer utilities.
3. Trainer-cycle warnings now also speak about the family set as the active published/runtime
   contract.

This does not remove the mirrored `champion_*` machine payload fields yet, but it stops presenting
them as the primary human-facing language for the trainer loop.

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Trainer utility code:
  - `src/repo_rag_lab/utilities.py`
- Trainer utility tests:
  - `tests/test_utilities.py`

## What is implemented now

### 1. Pending-recompile reasons are now family-first

Primary reason strings now use family terminology, including:

- `missing-family-state-path`
- `missing-family-state`
- `bundle-matches-current-family-set`
- `no-family-candidates`
- `family-record-hash-drift`
- `family-snapshot-drift`
- `family-trace-path-drift`

### 2. Trainer warnings now match the family-first contract

When recompilation remains pending because the published bundle lags the current state, trainer
warnings now speak about the current family set instead of the old champion set.

### 3. Compatibility aliases remain available

The machine payload still mirrors compatibility fields such as `champion_index_path`,
`champion_record_hashes`, and related alias surfaces so older code paths do not break during the
rollout.

## What is not implemented yet

- complete removal of `champion_*` payload aliases from repo and dataset wiring has not happened
  yet
- dataset deploy/bootstrap surfaces still mirror champion-named environment variables
- live AKS validation of the new family-first diagnostic wording has not been run in this turn
- notebook execution, coverage, UI/browser verification, and live deployment validation were not
  run in this turn

## Verification executed in this turn

Targeted checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_training_samples.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`72 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/utilities.py tests/test_utilities.py`
  - `pass`

Repository-native checks executed in this turn:

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
- UI / browser verification: not run in this turn
- live deployment / AKS validation: not run in this turn

## Current conclusion

The family-first contract is now more consistent at the operator layer:

- local and remote state already preferred family naming
- trainer diagnostics now prefer family naming too
- champion naming still remains only as a mirrored compatibility surface

The next highest-signal gap is to remove the remaining `champion_*` compatibility layer from repo
and dataset wiring, then validate the whole family-first contract in a live AKS trainer cycle.
