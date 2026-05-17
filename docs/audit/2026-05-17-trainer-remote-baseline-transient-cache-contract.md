# 2026-05-17 Trainer Remote-Baseline / Transient-Cache Contract

- Scope: replace the stale explanation that trainer could legitimately reuse PVC-local family
  state as its baseline, then align source, deployment defaults, and docs with the stricter
  family-first contract.
- Preceding note: `2026-05-17-symmetric-singleton-family-routing.md`

## Contract Correction

The active trainer contract is now:

- `repo-rag-training-families` is the only durable baseline for trainer family state.
- The trainer PVC is only a temporary artifact workspace for the current Codex Exec / trainer run:
  - queued and imported trace files
  - one in-flight `artifacts/trainer/pending-cycle.json`
  - one smart local mirror of the current remote `family_state_version`
  - current-cycle generated candidate / training files
- A local trainer cache is allowed, but only as a mirror of a known remote version.
- If the remote family-state version changes, the active local family cache must be discarded and
  refreshed from remote before the new queued traces are applied.
- If no remote family-state version exists yet, trainer may bootstrap a transient local family
  state from the current queue cycle only; that state is not authoritative until it is published
  into `repo-rag-training-families`.
- Trainer recompiles only dirty families touched by the current queued traces.
- `processed/...` is not an active baseline-replay path for trainer cycles.

## Source Fixes Landed

- `src/repo_rag_lab/utilities.py`
  - `_prepare_local_trainer_family_cache(...)` no longer prefers arbitrary existing local family
    state and no longer rebuilds active baseline state from processed-history replay
  - trainer now keeps explicit `artifacts/trainer/cache-source.json` metadata so a local cache can
    be reused only when it is already a mirror of the same remote `family_state_version`
  - fresh queue-triggered cycles now reset transient trainer outputs before baseline preparation
    while preserving only the in-flight `pending-cycle.json` ledger when needed
  - once materialization begins, the remote-cache provenance is cleared so mutated local family
    state cannot be mistaken for authoritative baseline state
  - after successful remote family-state publish, the local cache is re-tagged as a mirror of the
    newly published remote version
- `src/repo_rag_lab/trainer_deployment.py`
  - the default PVC contract is now `repo-rag-artifacts` instead of
    `repo-rag-trainer-artifacts`
  - generated manifests now write `repo-rag-artifacts.pvc.yaml`
- Documentation updated:
  - `docs/planning/family-first-mipro-runtime-contract.md`
  - `docs/operations/trainer-deployment.md`
  - `docs/architecture/research-narrative.md`
  - `docs/architecture/dspy-rag-guide.md`

## Verification

Checks executed in this turn:

- `uv run python -m compileall src tests` — `pass`
- `uv run pytest tests/test_utilities.py tests/test_cli_and_dspy.py -q` — `pass` (`91 passed`)
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — `pass`
  (`62 passed`)
- `uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`
- `make quality` — `pass` (`370 passed, 3 skipped`, coverage `81.49%`)

Checks not executed in this turn:

- No new live AKS run has been inspected yet on an image that contains this stricter
  remote-baseline cache contract.
- No post-push GitHub Actions run exists yet for this turn because no commit or push has been made
  yet.

## Current Status

- The repository contract no longer allows trainer to treat PVC-local family state as durable
  truth between pipeline runs.
- Trainer cache reuse is still supported, but only as a smart mirror of the current remote family
  version.
- Temporary trace handling remains PVC-backed under `artifacts/`, which matches the worker/trainer
  execution-artifact requirement without letting that PVC become the trainer source-of-truth.
