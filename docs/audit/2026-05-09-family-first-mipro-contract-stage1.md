# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 1

## Scope

- Replace the stage-0 champion-first mental model with the new family-first DSPy / MIPROv2
  contract.
- Start the code migration by changing prompt-family routing and by preserving prompt-lineage
  fields in the DSPy compile object.

## Contract status in this turn

The repository now expresses the agreed stage-1 direction more accurately:

1. Prompt families remain durable trainer state.
2. Prompt-family routing now uses father-style `argmax` similarity with one active `0.8` gate
   instead of the earlier soft-band routing path.
3. Family state now carries explicit compatibility fields for:
   - `family_father_question`
   - `family_father_record`
   - `family_runtime_record`
4. The proxy/trainer compatibility layer still preserves `champion-*` fields, but those are now
   transition aliases rather than the intended product truth.
5. `original_prompt`, `reformulated_prompt`, and `command_trace` now survive into the DSPy compile
   object instead of being dropped before `BootstrapFewShot` / `MIPROv2` see the training rows.
6. Bundle lineage can now point back to the family-state file that drove compilation.

## Repository surfaces changed in this turn

- New planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Historical stage-0 note marked as superseded:
  - `docs/planning/per-turn-dspy-mediation-contract.md`
- Updated architecture docs:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Updated trainer / DSPy code:
  - `src/repo_rag_lab/training_samples.py`
  - `src/repo_rag_lab/dspy_training.py`
  - `src/repo_rag_lab/runtime_artifacts.py`
  - `src/repo_rag_lab/utilities.py`
- Updated tests:
  - `tests/test_training_samples.py`
  - `tests/test_dspy_training.py`

## What is implemented now

### 1. Father-based routing surface

Trainer family payloads now compute and persist a routing father surface from family records. The
active lookup path resolves the best family by comparing the incoming prompt to all available
fathers and then applying a single `0.8` threshold.

### 2. Prompt-lineage compile surface

Trainer examples now retain:

- `original_prompt`
- `reformulated_prompt`
- `command_trace`

The DSPy compile path no longer drops those values. Instead, it composes them into the DSPy-facing
question prompt so the optimizer can at least reason over that lineage during training and
evaluation without requiring an immediate saved-program format break.

### 3. Bundle lineage bridge

Trainer recompile lineage and bundle manifests now expose the family-state path and family count
when available, so later bundle-registry work has a stable lineage hook to build on.

## What is not implemented yet

The new contract is still incomplete:

- `repo-rag-training-families` is not yet the primary remote container
- the live dataset / AKS deploy path still uses champion-named compatibility surfaces
- the published bundle does not yet carry per-family DSPy runtime artifacts
- `MIPROv2` still recompiles one global program, not one dirty family at a time
- per-turn traces still do not receive final post-run real `hits / total` enrichment in the live
  worker path

So this turn started the migration, but it did not finish the full family-artifact runtime model.

## Verification executed in this turn

Repository-native checks executed in this turn:

- `make files-sync`
  - `pass`
- `make exploratorium-sync`
  - `pass`
- `make verify-surfaces`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_training_samples.py tests/test_dspy_training.py tests/test_codex_proxy.py -q`
  - `pass` (`107 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`

## Verification categories not executed in this turn

- lint: not run
- type checking: not run
- coverage: not run
- notebook execution: not run
- dataset / AKS redeploy: not run

## Current conclusion

The repository now has the first real code-level shift from champion-first wording toward the
agreed family-first DSPy / MIPROv2 contract. Routing and compile inputs both moved in the right
direction, but the big remaining work is still ahead:

- move storage and deploy wiring from champion aliases to family-first state
- make `MIPROv2` produce family runtime artifacts
- publish those artifacts inside one monolithic bundle
- make the proxy execute those family artifacts directly at runtime
