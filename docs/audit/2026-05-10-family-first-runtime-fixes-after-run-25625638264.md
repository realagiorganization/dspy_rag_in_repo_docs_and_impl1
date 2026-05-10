# Repository audit note for 2026-05-10 family-first runtime fixes after run 25625638264

## Scope

- Follow up on the verified live gap from
  `docs/audit/2026-05-10-aks-run-25625638264-family-first-runtime-gap.md`.
- Fix the concrete causes that kept the live run on heuristic repo-RAG instead of the intended
  family-first DSPy path.
- Re-run local verification for both this repository and the linked `../dataset` worker/deployment
  surfaces.

## Gap addressed

The inspected AKS run `25625638264_20260510_100640` showed three concrete failures:

1. bundle/family runtime activation fell back to heuristic mode because bundle fetch/staging treated
   older `published.json` blobs as mandatory and did not reliably preserve family runtime artifacts
   in the local staged bundle mirror
2. queued training traces still exported a giant run-level transcript instead of compact per-turn
   family-first payloads
3. Codex session reuse remained too coarse, so resumed transcript carry-over could bloat prompt
   tokens far beyond the proxy mediation payload itself

## Fixes implemented

### 1. Bundle resolution now survives older remote bundle layouts

- `src/repo_rag_lab/runtime_artifacts.py`
  - `fetch_remote_bundle(...)` now treats `published.json` as optional
- `src/repo_rag_lab/codex_proxy.py`
  - local staged bundle lookup now runs before remote fetch fallback
  - remote fetch failures no longer block local family-registry/program resolution
- `../dataset/aks_module_generator/templates/deployment_script/part_1.txt`
  - bundle staging now requires only `bundle.json`, `metadata.json`, and `program.json`
  - `published.json` is best-effort
  - family `program.json` / `metadata.json` blobs are staged into `.repo_rag_bundle_store`

### 2. Dataset execution envelope noise is stripped before it reaches family-first lineage

- `src/repo_rag_lab/codex_proxy.py`
  - `extract_codex_turn_state(...)` now strips dataset execution scaffolding from both
    `original_prompt` and the user-facing `command_trace` step
- `../dataset/docker/prompt-executor/worker_execution_prompt.py`
  - compact trace payload building now prefers stripped prompt lineage, compact stdout, and proxy
    status fields instead of embedding the whole `codex_response.txt` transcript

### 3. Worker handoff now synthesizes compact per-turn batches when proxy persistence is absent

- `../dataset/docker/prompt-executor/worker_execution_prompt.py`
  - `_seed_codex_repo_rag_turn_trace_batch_from_proxy_status(...)` now creates a compact local
    `repo_rag_turn_traces/<batch>/` batch from `repo_rag_codex_proxy_last.json` plus final outcome
  - `_build_codex_repo_rag_trace_payload(...)` now preserves:
    - `original_prompt`
    - `reformulated_prompt`
    - `command_trace`
    - `prompt_family_id`
    - `prompt_family_similarity`
    - `prompt_family_band`
    - `family_runtime_hit_rate`
    - `family_artifact_hit_rate`
    - `family_artifact_selected`
    - `mediation_metric_hits`
    - `mediation_metric_total`

### 4. Resume-lane policy is now explicit instead of accidental

- `../dataset/docker/prompt-executor/worker_execution_prompt.py`
  - automatic session lane mode now defaults to `queue_and_slug`
- `../dataset/aks_module_generator/mixins/k8s_manifests.py`
  - worker pods now always receive `DATASET_CODEX_AUTO_SESSION_LANE_MODE=queue_and_slug` unless
    explicitly overridden
- `../dataset/.github/workflows/parallel-prompt-execution-aks.yml`
  - workflow env now exposes the same default explicitly

## Verification executed in this turn

### Current repository

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_codex_proxy.py tests/test_runtime_artifacts_azure.py -q`
  - `pass` (`26 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`45 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/codex_proxy.py src/repo_rag_lab/runtime_artifacts.py tests/test_codex_proxy.py tests/test_runtime_artifacts_azure.py`
  - `pass`

### `../dataset`

- `pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/unit/test_deployment_script_template_regressions.py tests/test_aks_module_generator_generate_modules.py tests/test_aks_module_generator_manifests.py tests/unit/test_deploy_repo_rag_trainer_script.py -q`
  - `pass` (`105 passed`)
- `python -m compileall docker/prompt-executor/worker_execution_prompt.py aks_module_generator/mixins/k8s_manifests.py .github/workflows/parallel-prompt-execution-aks.yml tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/unit/test_deployment_script_template_regressions.py tests/test_aks_module_generator_generate_modules.py`
  - `pass`

### Generated surface sync

- `UV_CACHE_DIR=/tmp/uvcache make files-sync`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache make exploratorium-sync`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache make verify-surfaces`
  - `pass`

## Verification categories not run in this turn

- UI/browser verification
- coverage
- dedicated type checking
- notebook execution
- live Azure/AKS redeploy validation after the hotfixes

## Current conclusion

The locally verified code now matches the intended hotfix direction substantially better than the
inspected live run:

- family-first bundle resolution no longer depends on legacy `published.json`
- staged bundle mirrors now carry family runtime artifacts
- prompt lineage strips dataset envelope noise before it enters trace storage
- queued handoff can synthesize compact per-turn batches instead of exporting one giant transcript
- Codex session reuse is now explicitly narrowed to `queue_and_slug`

The remaining risk is deployment validation, not local code shape: a fresh AKS run is still needed
to prove that the hotfixed family-first runtime path activates in the live environment and actually
reduces prompt-token growth.

## Follow-up live verification: run `25627552229_20260510_114446`

### What improved

- Prompt-token usage dropped from `102024` in the previous inspected run to `25803` in this run
  (`-76221`, `-74.7%`).
- The worker now persisted a compact per-turn batch under
  `repo_rag_turn_traces/20260510T114308Z/` with:
  - `manifest.json`
  - `turn-000.json`
  - `repo_rag_turn_trace_export_batch.json`
  - `repo_rag_turn_trace_enqueue_batch.json`
- `turn-000.json` carries:
  - compact `answer`
  - stripped `original_prompt`
  - compact `command_trace`
- `codex_response.txt` is no longer mirrored wholesale into the queued trace payload. The compact
  answer is `671` characters while the raw transcript still exists separately as an execution
  artifact.
- Session reuse narrowed correctly:
  - `codex_session_state.session_mode = "forked"`
  - `codex_session_state.lane_source = "auto:queue_and_slug"`

### What still did not activate

- The live proxy still did not resolve a compiled family-aware bundle:
  - `bundle_resolved = false`
  - `bundle_version = null`
  - `program_path = null`
  - `dspy_status = "heuristic"`
- The family-first runtime fields are still absent from the live payload:
  - `prompt_family_id`
  - `family_runtime_hit_rate`
  - `family_artifact_hit_rate`
  - `family_artifact_selected`
  - `mediation_metric_hits`
  - `mediation_metric_total`
- No bundle-store or family-state runtime surface appeared in the exported execution artifacts.

### What still behaved incorrectly

- The payload still carries the full dataset execution envelope in the wrong fields:
  - `question`
  - `reformulated_prompt`
  - exported `trace.question`
- Only `original_prompt` was stripped down to the actual user task. The oversized execution
  contract is therefore still leaking into family matching and exported training data.
- Batch export succeeded, but batch enqueue failed:
  - `repo_rag_turn_trace_export_batch.json`: `command_status = "success"`
  - `repo_rag_turn_trace_enqueue_batch.json`: `command_status = "fail"`
- The failure reason is a CLI contract mismatch:
  - `repo-rag: error: unrecognized arguments: --batch-name 20260510T114308Z`
- Queue handoff still completed only because the worker fell back to the legacy single-trace
  `trusted-trace-handoff` path, which queued
  `queued/repo-rag-training/20260510T114444Z-prompts_debt_relief-p00000-cfc990.json`.

### Live conclusion after the follow-up run

The hotfixes clearly improved token behavior and compact trace persistence, but the live system is
still not on the intended family-first DSPy path. The remaining live gaps are now narrower and more
specific:

1. fix bundle activation in the deployed image so the proxy resolves a compiled family bundle
   instead of heuristic-only mediation
2. strip the dataset execution envelope from `question` and `reformulated_prompt`, not only from
   `original_prompt`
3. repair the `trace-enqueue-batch` CLI contract so batch handoff no longer falls back to legacy
   single-trace queueing

## Follow-up code fixes after run `25627552229_20260510_114446`

### Fixes implemented

1. `src/repo_rag_lab/codex_proxy.py`
   - `_resolve_bundle_family_registry(...)` now performs a remote bundle fetch when
     `bundle_version` is explicit but the local staged bundle mirror does not already contain the
     requested family registry. This removes one live activation gap where explicit-version DSPy
     lookups could silently skip family metadata.
2. `../dataset/docker/prompt-executor/worker_execution_prompt.py`
   - `_resolve_codex_repo_rag_turn_state(...)` now strips the dataset execution envelope from
     `reformulated_prompt` and from user steps inside `command_trace`, not just from
     `original_prompt`.
   - `_normalize_codex_repo_rag_proxy_status(...)` now rewrites sparse proxy status payloads into
     a compact lineage form before the worker seeds or exports traces.
   - `_build_codex_repo_rag_trace_payload(...)` now prefers the normalized proxy-side
     `bundle_version` when the top-level Codex result omitted it.
   - `_build_codex_repo_rag_proxy_spec(...)` now pre-resolves the promoted stable bundle version
     with `bundle-inspect` before launching the proxy when runtime pinning was not explicit.
   - `_build_repo_rag_trace_enqueue_command(...)` no longer appends `--batch-name` to individual
     `trace-enqueue` calls, preserving compatibility with live images where that CLI surface is not
     yet available.

### Verification executed in this follow-up

#### Current repository

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_codex_proxy.py -q`
  - `pass` (`12 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`45 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/codex_proxy.py tests/test_codex_proxy.py`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache make verify-surfaces`
  - `pass`

#### `../dataset`

- `pytest ../dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py -q`
  - `pass` (`18 passed`)
- `python -m compileall ../dataset/docker/prompt-executor/worker_execution_prompt.py ../dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py`
  - `pass`

### Current status after the fixes

Local code now covers the three concrete failures seen in run `25627552229_20260510_114446`:

1. explicit-version family bundle lookup can fall back to remote fetch
2. sparse proxy status no longer forces the full dataset execution envelope into `question` and
   `reformulated_prompt`
3. batch queue handoff no longer depends on `trace-enqueue --batch-name`

The remaining unknown is live deployment parity. A fresh AKS run is still required to confirm that
the new image really emits the normalized proxy status and that the proxy actually activates the
family-first DSPy bundle in production.
