# 2026-05-11 Family Runtime Artifact Fallback And Bundle Staging Path Fix

## Context

The user asked for the concrete reason the DSPy family library still was not being used by live
workers and requested a direct fix focused on library activation, not helper-LM cost reduction.

Two independent execution-stage gaps were confirmed:

1. Worker bundle staging in the dataset deploy script was being skipped when the workflow ran from
   `aks_modules/`, because the script checked for `tools/pvc_artifact_sync.sh` relative to the
   current shell directory instead of the repository root.
2. Even when `repo-rag-training-families` already contained populated families, worker-side family
   lookup could still fail to execute a matched family runtime artifact because the family-state
   container stored `family.json`, `father.json`, and `records/...`, but **not** the compiled
   family `program.json` / `metadata.json` files needed for runtime execution when
   `repo-rag-bundles` was empty or unpublished.

Those two gaps explain the observed pattern:

- prompt-family lookup could succeed
- `prompt_family_id` could be assigned
- but `family_artifact_selected` still stayed false
- and the proxy fell back to passthrough / heuristic mediation

## Root Cause

### 1. Deploy-stage PVC sync path was shell-relative

The GitHub Actions workflow enters `cd aks_modules` before invoking `./deploy.sh`. The generated
deployment script, however, still checked:

- `tools/pvc_artifact_sync.sh`

instead of a repo-root-resolved path. In that context the helper script was not executable from
the current directory, so deploy-stage messages such as:

- `Skipping repo-rag bundle staging because tools/pvc_artifact_sync.sh is unavailable`

were true even though the helper script existed in the dataset repository.

That meant `.repo_rag_bundle_store` was never synced into the worker artifacts PVC for those runs.

### 2. Family-state did not carry executable family artifacts

The family-state container already persisted:

- `current.json`
- `versions/<family_state_version>/families/<family_id>/family.json`
- `father.json`
- `records/<snapshot>.json`

But it did not persist:

- `runtime-artifact/program.json`
- `runtime-artifact/metadata.json`

As a result, synthesized runtime family registries still contained trainer-local artifact paths
such as `artifacts/dspy/.../program.json`, which were not present in the worker execution pod.

So a worker could:

- match a family father
- see `family_runtime_artifact` metadata
- but still fail to resolve a runnable local `program.json`

## Fix Implemented

### 1. Family-state uploads now include runtime artifacts

`src/repo_rag_lab/runtime_artifacts.py`

- `upload_remote_family_state(...)` now uploads family runtime artifacts into the family-state
  container under:
  - `versions/<family_state_version>/families/<family_id>/runtime-artifact/program.json`
  - `versions/<family_state_version>/families/<family_id>/runtime-artifact/metadata.json`
- `fetch_remote_family_state(...)` now downloads those runtime-artifact blobs into the local cache
  tree and rewrites `family_runtime_artifact.program_path` / `metadata_path` inside the cached
  `family-state.json` and cached per-family `family.json`.

Practical outcome:

- workers no longer need a published monolithic bundle just to execute an already-compiled family
  program
- if `repo-rag-training-families` contains a matched family's runtime artifact, the synthesized
  family registry can now resolve a real local `program.json`

### 2. Deploy-stage PVC sync now uses a repo-root-resolved helper path

`../dataset/aks_module_generator/templates/deployment_script/part_1.txt`

- now defines:
  - `PVC_ARTIFACT_SYNC_SCRIPT="$DISCORD_PUBLISHER_REPO_ROOT/tools/pvc_artifact_sync.sh"`
- repo-rag cache sync and bundle-store staging now invoke:
  - `bash "$PVC_ARTIFACT_SYNC_SCRIPT" ...`

That removes the shell-directory dependency introduced by `cd aks_modules`.

## Verification

Executed locally in the same turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_runtime_artifacts_azure.py tests/test_codex_proxy.py -q`
  - `36 passed`
- `pytest ../dataset/tests/unit/test_deployment_script_template_regressions.py -q`
  - `14 passed`
- `cd ../dataset && pytest tests/test_aks_module_generator_generate_modules.py::test_generate_modules_writes_bash_valid_deploy_script -q`
  - `1 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `49 passed`

## Limits Of The Fix

This fix is forward-looking for runtime artifact availability:

- future family-state upload cycles will now carry runtime-artifact files
- workers will then be able to execute matched family programs even without a published bundle

But old family-state versions that were uploaded **before** this fix do not retroactively gain
their missing runtime-artifact blobs. They need either:

- one new trainer upload cycle with the fixed code, or
- a one-time backfill/migration step

## Conclusion

The missing DSPy library activation was not caused by the helper LM call design itself.

It came from two concrete operational gaps:

1. bundle staging silently skipped because the deploy script resolved `pvc_artifact_sync.sh`
   relative to `aks_modules/`
2. family-state storage carried family metadata but not the executable runtime artifacts required
   to turn a matched father into a runnable family program

Both gaps are now fixed locally in code and covered by regression tests.
