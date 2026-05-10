# 2026-05-10 Family-State Root Alias And Latest-Bundle Staging Fallback

## Context

AKS run `25634202380_20260510_170342` still executed in heuristic mode even after reset-lane and
batch-handoff fixes landed. The downloaded execution artifacts showed:

- `bundle_resolved=false`
- `bundle_version=null`
- `program_loaded=false`
- `dspy_status=heuristic`

At the same time the operator-visible `repo-rag-training-families` container still looked empty
unless one manually descended into `versions/<family_state_version>/...`.

That narrowed the remaining live gap to two specific surfaces:

1. execution-side bundle activation still depended on `channels/stable.json` being present or
   mirrored, even when immutable bundle versions already existed in `repo-rag-bundles`
2. remote family-state upload still wrote only versioned family directories, not a current root
   alias that made the container obviously non-empty to operators

## Local Fix

The repository now closes both gaps locally.

### Repo-RAG Runtime Artifacts

`src/repo_rag_lab/runtime_artifacts.py` now:

- resolves the latest immutable remote bundle version directly from `versions/<bundle>/bundle.json`
  when channel lookup does not produce a version
- reports that fallback via `resolved_from="latest-remote-version"`
- mirrors the active family-state snapshot at the root of
  `repo-rag-training-families` as:
  - `family-state.json`
  - `families/<prompt_family_id>/family.json`
  - `families/<prompt_family_id>/father.json`
  - `families/<prompt_family_id>/records/<snapshot>.json`

That means the family-state container now exposes both:

- immutable versioned history under `versions/<family_state_version>/...`
- one operator-facing current view at container root

### Dataset Deploy Staging

`../dataset/aks_module_generator/templates/deployment_script/part_1.txt` now:

- lists `versions/` blobs when `channels/stable.json` is absent
- resolves the latest remote immutable bundle version from
  `versions/<bundle>/bundle.json`
- synthesizes a local staged `channels/stable.json` pointing at that resolved version
- then stages the same bundle assets into `.repo_rag_bundle_store`

This keeps worker pods from falling back to heuristic mode solely because the stable channel blob
is missing while immutable bundle assets already exist.

## Verification

Ran locally:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_runtime_artifacts_azure.py -q`
  - `16 passed`
- `cd ../dataset && pytest tests/unit/test_deployment_script_template_regressions.py tests/test_aks_module_generator_generate_modules.py::test_generate_modules_writes_bash_valid_deploy_script -q`
  - `15 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `45 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

## Remaining Risk

No new live AKS run has been checked after these fixes. The expected next live proof points are:

- `repo_rag_backend.json` should no longer show `bundle_version=null`
- `repo_rag_codex_proxy_last.json` should no longer stay in `dspy_status=heuristic`
- `repo-rag-training-families` should visibly contain root-level `family-state.json` and
  `families/<family_id>/...` entries after the next trainer-side upload
