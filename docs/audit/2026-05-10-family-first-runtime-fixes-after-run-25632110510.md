# Repository audit note for 2026-05-10 family-first runtime fixes after AKS run 25632110510

## Scope

- Fix the remaining local causes behind `2026-05-10-aks-run-25632110510-handoff-fixed-runtime-still-heuristic.md`.
- Focus on three gaps:
  - live bundle/family artifact activation still falling back to heuristic mode
  - raw `codex exec` prompt still carrying Discord/dataset scaffolding
  - repeated `queue_and_slug` resume lanes inflating prompt-token usage across reruns

## Implemented local fixes

### 1. Proxy bundle resolution now falls back to the staged local mirror

`src/repo_rag_lab/codex_proxy.py` now:

- enumerates staged bundle versions directly from `versions/<bundle>/...` and
  `artifacts/dspy/remote/<bundle>/...`
- resolves the latest staged bundle version even when `channels/stable.json` or older manifest
  surfaces are missing
- loads `family_registry` directly from staged `bundle.json` when the channel/published path is
  unavailable
- resolves `program.json` from the latest staged bundle version before dropping all the way to the
  runtime fallback

This directly targets the live symptom where `bundle_version`, `program_path`, and
`program_loaded` stayed null even though the worker already staged `.repo_rag_bundle_store`.

### 2. The worker now builds a clean Codex input prompt before `codex exec`

`../dataset/docker/prompt-executor/worker_execution_prompt.py` now separates:

- the rich prompt trace persisted into artifacts
- the slim prompt body actually passed to `codex exec`

The live Codex input now strips:

- `Discord channel: ...`
- `Channel ID: ...`
- `Messages with required reaction:`
- forwarded Discord tails
- attachment location dump noise

and keeps only:

- the cleaned task prompt
- one concise repository line
- one concise attachment hint when attachments exist

This directly targets the run artifact where `codex_response.txt` still showed the full Discord
execution envelope at the start of the Codex session.

### 3. The worker now resolves bundle versions directly from the staged bundle root

`../dataset/docker/prompt-executor/worker_execution_prompt.py` now:

- falls back to `artifacts/.repo_rag_bundle_store` when no explicit bundle root is provided
- resolves the staged stable bundle version directly from local channel/version files before trying
  `repo-rag bundle-inspect`
- reuses the same local bundle-version fallback in the `repo_rag_cli` path when an explicit bundle
  pin is invalid

That means the Codex proxy no longer depends exclusively on a successful live `bundle-inspect`
subprocess to learn the active staged bundle version.

### 4. AKS defaults now bound resumed-lane growth

`../dataset/.github/workflows/parallel-prompt-execution-aks.yml` and
`../dataset/aks_module_generator/mixins/k8s_manifests.py` now export default session policy envs:

- `DATASET_CODEX_MAX_RESUMED_RUNS=3`
- `DATASET_CODEX_PROMPT_TOKEN_GROWTH_RESET_RATIO=2.0`

Those defaults turn on the already-implemented reset logic in `worker_codex_cli_exec.py` for live
pods, so repeated verification reruns do not keep compounding the same resumed transcript without
bound.

## Local verification executed in this turn

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_codex_proxy.py -q` → `pass` (`16 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` → `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/codex_proxy.py tests/test_codex_proxy.py` → `pass`
- `cd ../dataset && pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/test_aks_module_generator_generate_modules.py -q` → `pass` (`60 passed`)
- `cd ../dataset && pytest tests/unit/test_worker_codex_cli_exec_small.py tests/test_aks_module_generator_manifests.py tests/unit/test_deploy_repo_rag_trainer_script.py -q` → `pass` (`84 passed`)
- `cd ../dataset && python -m compileall docker/prompt-executor/worker_execution_prompt.py aks_module_generator/mixins/k8s_manifests.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/test_aks_module_generator_generate_modules.py` → `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` → `pass` (`45 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test` → `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` → `pass`

## Checks not executed in this turn

- no new live AKS rerun was executed from this shell after these fixes
- no direct Azure Blob inspection was performed in this turn
- `make coverage` was not rerun
- no UI or notebook execution suite exists/reran for this turn

## Current conclusion

The three remaining local causes from the last run are now addressed in code:

- bundle activation no longer depends solely on channel/published lookup success
- the real `codex exec` input is now task-first and stripped of Discord scaffolding
- live pods will now reset oversized resumed lanes by default instead of letting the same lane
  grow indefinitely

What remains unverified is only the next live rerun:

- whether the deployed proxy now reports a non-null `bundle_version`
- whether runtime now fills `prompt_family_id` / family hit-rate fields instead of staying in
  heuristic mode
- whether prompt-token usage stays bounded after the new reset defaults and clean prompt body land
