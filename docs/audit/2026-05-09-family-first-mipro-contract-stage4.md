# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 4

## Scope

- Turn the bundle-embedded family registry into an executable runtime surface instead of a
  placeholder-only registry.
- Verify that family-scoped DSPy artifacts survive trainer compile, bundle publish/fetch, and
  proxy execution.

## Contract status in this turn

The repository now advances the family-first contract in three concrete ways:

1. Trainer compilation emits one family-scoped DSPy artifact per persisted prompt family and
   records those outputs in metadata as `family_artifact_registry`.
2. Remote bundle publish/fetch now transfers those family `program.json` / `metadata.json` assets
   beside the global compiled program.
3. After a family match, the proxy can execute the matched family artifact directly and passes
   `original_prompt`, `reformulated_prompt`, and `command_trace` into that runtime call.

This is the first local stage where the monolithic bundle contains family runtime artifacts that
the proxy can actually execute, not only family lookup metadata.

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Runtime / trainer code:
  - `src/repo_rag_lab/dspy_training.py`
  - `src/repo_rag_lab/dspy_workflow.py`
  - `src/repo_rag_lab/runtime_artifacts.py`
  - `src/repo_rag_lab/codex_proxy.py`
- Tests:
  - `tests/test_dspy_training.py`
  - `tests/test_codex_proxy.py`
  - `tests/test_runtime_artifacts_azure.py`

## What is implemented now

### 1. Family artifact registry in compile metadata

`train_repository_program()` now compiles family-scoped DSPy artifacts under
`artifacts/dspy/<run>/families/<family_id>/...` and records them in metadata as
`family_artifact_registry`. Bundle generation consumes that registry and marks matching family
entries as executable runtime artifacts instead of placeholder-only runtime records.

### 2. Remote bundle round-trip for family artifacts

`upload_remote_bundle()` and `fetch_remote_bundle()` now move family runtime asset files through
the Azure bundle container. Remote fetch rewrites the cached local `bundle.json` so matched family
entries point at the downloaded local cache paths.

### 3. Proxy execution of matched family artifacts

`build_codex_mediation()` now resolves a family runtime program path from the bundle registry and
uses that family program when it exists. The runtime call no longer collapses family execution to
the global bundle program, and the call now carries `original_prompt`, `reformulated_prompt`, and
`command_trace`.

## What is not implemented yet

- dirty-family-only `MIPROv2` recompilation; the local trainer still recompiles every persisted
  family instead of only dirty ones
- `repo-rag-training-families` as the primary remote family-state container
- removal of compatibility `champion_*` aliases from the repo and dataset wiring
- post-run enrichment of per-turn traces with final real `hits / total`
- live AKS verification that the newly published runtime actually downloads and executes family
  artifacts instead of the older global-only path

## Verification executed in this turn

Targeted checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_dspy_training.py tests/test_codex_proxy.py tests/test_runtime_artifacts_azure.py tests/test_training_samples.py -q`
  - `pass` (`77 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_cli_and_dspy.py -q`
  - `pass` (`32 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/codex_proxy.py src/repo_rag_lab/dspy_workflow.py src/repo_rag_lab/runtime_artifacts.py src/repo_rag_lab/dspy_training.py tests/test_codex_proxy.py tests/test_dspy_training.py tests/test_runtime_artifacts_azure.py`
  - `pass`

Repository-native baseline checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`44 passed`)
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

Verification categories that still do not exist or were not run in this turn:

- coverage: not run in this turn
- notebook execution: no notebook execution suite was run in this turn
- live deployment / AKS validation: not run in this turn
- UI / browser verification: not applicable in-repo and not run

## Current conclusion

The local repository now has the first executable version of the family-first bundle model:

- one monolithic bundle
- internal family registry
- compiled family runtime artifacts
- remote bundle round-trip for those family artifacts
- proxy execution of the matched family artifact with full prompt lineage

The next bottlenecks are now trainer-side granularity and live rollout, not the absence of
family-scoped runtime artifacts in the local codebase.
