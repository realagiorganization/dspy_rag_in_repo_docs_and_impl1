# Repository audit note for 2026-05-10 family-first runtime fixes after AKS run 25629990035

## Scope

- Patch the three concrete regressions observed in AKS run `25629990035_20260510_134639`.
- Re-verify the affected proxy, worker, and deploy-template surfaces locally.

## Regressions addressed

### 1. Bundle activation could miss staged mirror assets

The proxy now resolves bundle and family runtime programs from the staged mirror layout even when
the bundle manifest still points at the original trainer-side `artifacts/dspy/...` paths.

Implemented in:

- `src/repo_rag_lab/codex_proxy.py`

Local behavior change:

- explicit `bundle_version` now falls back to `versions/<bundle_version>/program.json`
- matched families now fall back to
  `versions/<bundle_version>/families/<prompt_family_id>/program.json`
- when bundle-local `family_registry` is missing, the proxy synthesizes one from
  `family-state.json` and still attempts family-runtime execution

### 2. Forwarded Discord tail still leaked into prompt lineage

The prompt normalizer now strips the forwarding tail from:

- `question`
- `original_prompt`
- `reformulated_prompt`
- user-facing `command_trace` entries

Implemented in:

- `src/repo_rag_lab/codex_proxy.py`
- `../dataset/docker/prompt-executor/worker_execution_prompt.py`

### 3. Trusted deploy-stage handoff duplicated successful worker batch handoff

The deploy-stage trusted handoff now short-circuits when the worker already wrote a successful
per-turn batch summary:

- `repo_rag_turn_trace_enqueue_batch.json`
- `repo_rag_turn_trace_import_batch.json`

That means runner-side Azure upload no longer queues the same prompt again after the worker already
did the compact batch handoff.

Implemented in:

- `../dataset/aks_module_generator/templates/deployment_script/part_4.txt`
- `../dataset/aks_modules/deploy.sh`

## Checks executed in this turn

### Current repository

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_codex_proxy.py -q` → `pass` (`14 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/codex_proxy.py tests/test_codex_proxy.py` → `pass`

### Dataset repository

- `pytest ../dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py ../dataset/tests/unit/test_deployment_script_template_regressions.py -q` → `pass` (`33 passed`)
- `python -m compileall ../dataset/docker/prompt-executor/worker_execution_prompt.py ../dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py ../dataset/tests/unit/test_deployment_script_template_regressions.py` → `pass`
- `cd ../dataset && pytest tests/test_aks_module_generator_generate_modules.py tests/test_aks_module_generator_manifests.py tests/unit/test_deploy_repo_rag_trainer_script.py -q` → `pass` (`75 passed`)

## Repository-native verification executed in this turn

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` → `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` → `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test` → `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` → `pass`

## Checks not executed in this turn

- `make coverage` was **not** rerun locally.
- broad repo lint/type suites beyond the targeted `ruff` check were **not** rerun locally.
- no UI test suite exists for this repository.
- no notebook execution suite was rerun in this turn.
- no live AKS rerun was executed after these fixes.

## Current conclusion

The three concrete gaps from run `25629990035_20260510_134639` are now fixed in local code:

- staged mirror bundles can activate without depending on trainer-side path strings
- forwarded Discord tails no longer contaminate prompt lineage
- deploy-stage trusted handoff no longer re-queues a run after successful worker batch enqueue

What remains unverified is the live effect of those fixes. The next AKS rerun needs to confirm:

1. `bundle_version`, `program_path`, and `program_loaded` become non-null at runtime
2. `prompt_family_id` and related family fields appear in live turn traces
3. only the compact batch handoff remains, without the legacy duplicate queue item
