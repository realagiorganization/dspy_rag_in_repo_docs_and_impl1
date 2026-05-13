# 2026-05-11 Family Runtime Bridge Falls Back To Family-State Locally

## Summary

The remaining local runtime bug behind `family_artifact_selected=false` is now fixed in code.

Before this change, the proxy could:

- match an existing family father
- expose `prompt_family_id` and `prompt_family_similarity`
- still stay on `dspy_status=heuristic`

even when the family already had a compiled runtime artifact inside remote family-state storage.

The break was in the bridge from:

- matched bundle/family registry entry
- to a runnable local `program.json`

Two concrete gaps were fixed:

1. when bundle-local `family_registry` existed but pointed at a stale or missing family
   `program.json`, the proxy did not fall back to the fetched `family-state.json` runtime artifact
   path
2. exported trainer-facing trace records hid family/runtime metadata inside the nested `trace`
   payload instead of surfacing it as first-class fields

## Fix

`src/repo_rag_lab/codex_proxy.py` now:

- resolves family runtime programs relative to both the repository root and the bundle root
- lazily resolves `family-state.json` only when needed
- falls back from a stale bundle-local registry entry to a synthesized registry built from the
  fetched `family-state.json`
- keeps bundle-local registry priority when it already points at a valid runnable artifact
- emits repo-relative `program_path` values when the selected family artifact lives under the
  repository cache instead of the staged bundle mirror

`src/repo_rag_lab/runtime_artifacts.py` now exports the following family/runtime fields directly in
trainer-facing trace records:

- `bundle_version`
- `program_path`
- `prompt_family_id`
- `prompt_family_similarity`
- `prompt_family_band`
- `family_runtime_hit_rate`
- `family_artifact_hit_rate`
- `family_artifact_selected`
- `mediation_metric_hits`
- `mediation_metric_total`

## Evidence

Targeted runtime regressions now pass:

- `tests/test_codex_proxy.py::test_build_codex_mediation_prefers_bundle_family_registry`
- `tests/test_codex_proxy.py::test_build_codex_mediation_falls_back_to_family_state_when_bundle_registry_path_is_stale`
- `tests/test_utilities.py::test_run_trace_export_preserves_family_runtime_metadata`

The stale-registry regression proves the intended family-first runtime path:

- bundle registry matches `prompt_family_id="pf-demo"`
- staged bundle family path is stale/missing
- fetched `family-state.json` still carries a valid family runtime artifact under
  `artifacts/trainer/remote-family-state/.../runtime-artifact/program.json`
- `build_codex_mediation(...)` now returns:
  - `dspy_status="success"`
  - `family_artifact_selected=true`
  - repo-relative `program_path`

## Verification

Configured repository checks relevant to this fix:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_codex_proxy.py tests/test_utilities.py -q`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make files-sync`
- `make exploratorium-sync`
- `make verify-surfaces`

Executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_codex_proxy.py tests/test_utilities.py -q` — `66 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — `50 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`

Not executed in this turn:

- coverage
- full lint/type-check suites
- live AKS rerun validating `family_artifact_selected=true` end-to-end
- trainer-side queue drain on newly exported traces

## Remaining Gap

This fixes the local runtime bridge. It does **not** prove live AKS behavior yet.

The next live rerun should now answer only the deployment question:

- does the worker pod fetch the same family-state runtime artifact and set
  `family_artifact_selected=true` at runtime?

