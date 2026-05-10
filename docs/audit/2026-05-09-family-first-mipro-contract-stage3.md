# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 3

## Scope

- Advance the family-first migration from external family-state compatibility surfaces into the
  monolithic bundle itself.
- Make the proxy prefer bundle-embedded family lookup before falling back to the external
  family-state file.

## Contract status in this turn

The repository now moved one step closer to the target runtime contract:

1. `bundle.json` now carries an internal `family_registry`.
2. That registry is built from the current family-state file during bundle creation.
3. Each registry family currently contains:
   - `prompt_family_id`
   - `family_father_question`
   - `family_father_record`
   - `family_runtime_record`
   - normalized runtime metric payload derived from `metric_hits`, `metric_total`, and
     `metric_ratio`
4. The proxy now resolves prompt-family support from the bundle registry first and falls back to
   the external family-state file only when the bundle does not yet expose a registry.

This still does **not** mean per-family MIPRO runtime artifacts are done. The runtime artifact
inside the registry is currently a compatibility placeholder based on the persisted
`family_runtime_record`, not yet a dedicated compiled family subprogram.

## Repository surfaces changed in this turn

- Updated planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Updated architecture narrative:
  - `docs/architecture/research-narrative.md`
- Updated runtime / trainer code:
  - `src/repo_rag_lab/runtime_artifacts.py`
  - `src/repo_rag_lab/training_samples.py`
  - `src/repo_rag_lab/codex_proxy.py`
- Updated tests:
  - `tests/test_dspy_training.py`
  - `tests/test_codex_proxy.py`

## What is implemented now

### 1. Bundle-embedded family registry

Bundle creation now reads the current family-state file from lineage metadata and writes a
normalized `family_registry` into `bundle.json`. The bundle remains monolithic, but it now starts
to look like the intended internal registry model instead of only carrying one global program path
plus lineage pointers.

### 2. Bundle-first runtime lookup

The proxy no longer needs to depend only on a sidecar family-state file when a bundle already
contains the same family information. It now checks bundle registry data first, which is a better
fit for the final product direction: one published bundle whose internal family registry drives
runtime routing.

## What is not implemented yet

- the bundle registry still stores placeholder runtime record payloads instead of dedicated
  per-family DSPy / MIPRO artifacts
- proxy execution still runs the global compiled bundle program after family match instead of a
  family-specific runtime artifact
- dirty-family `MIPROv2` recompilation is still not split away from the global compile path
- `repo-rag-training-families` is still not the active remote container
- worker-side post-run `hits / total` enrichment is still not complete

## Verification executed in this turn

Repository-native checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_dspy_training.py tests/test_codex_proxy.py tests/test_runtime_artifacts_azure.py tests/test_training_samples.py -q`
  - `pass` (`75 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_repository_rag_bdd.py -q`
  - `pass` (`3 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/codex_proxy.py src/repo_rag_lab/runtime_artifacts.py src/repo_rag_lab/training_samples.py tests/test_dspy_training.py tests/test_codex_proxy.py`
  - `pass`

## Current conclusion

The repository now has the first practical version of the monolithic family bundle model:

- one bundle
- internal family registry
- proxy lookup from that registry

The next step is the harder one: replace placeholder runtime records in that registry with actual
family-level optimized DSPy artifacts and then make the proxy execute those family artifacts
directly after routing.
