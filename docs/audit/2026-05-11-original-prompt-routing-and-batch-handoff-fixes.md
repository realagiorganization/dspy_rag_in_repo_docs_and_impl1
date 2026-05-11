# 2026-05-11 Original Prompt Routing And Batch Handoff Fixes

## Context

The latest inspected execution artifacts still showed two gaps after the run completed successfully:

1. family lookup created a new family instead of reusing an existing father-backed family artifact
2. authoritative queue handoff still used one coarse single-trace payload instead of the captured
   per-turn batch

The user asked for those gaps to be fixed before the next live rerun.

## Changes Made

Repository-side routing now follows the family-first contract more closely:

- prompt-family routing now prefers `original_prompt` over `reformulated_prompt`
- persisted family fathers are refreshed from the same routing surface
- training-candidate materialization now preserves `question` as the routing prompt surface instead
  of overwriting it with the reformulated variant
- bundle passthrough metadata now retains the resolved bundle version even when no family match is
  found

Deployment-side handoff now prefers the worker batch contract:

- deploy-stage trusted handoff still stands down when the worker already wrote a successful
  `repo_rag_turn_trace_enqueue_batch.json` or `repo_rag_turn_trace_import_batch.json`
- if worker-side batch handoff did **not** complete but
  `repo_rag_turn_trace_batch_manifest.json` exists, deploy-stage now attempts a trusted
  batch-aware enqueue from the exported per-turn trace records under `artifacts/traces/`
- only when no valid worker batch is present does deploy-stage fall back to the old coarse
  `repo_rag_codex_proxy_payload.json` path

## Why This Matters

The latest artifact review showed that:

- DSPy reformulation was already working
- prompt-family assignment existed
- but the runtime still missed family reuse because routing compared against the wrong prompt
  surface
- and trainer ingestion still saw a coarse single trace because deploy fallback ignored the worker
  batch manifest

These fixes do not prove live success by themselves, but they remove the two code paths that were
still violating the intended family-first contract.

## Local Verification In This Turn

Executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_training_samples.py tests/test_codex_proxy.py -q`
  - `48 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/codex_proxy.py src/repo_rag_lab/training_samples.py tests/test_codex_proxy.py tests/test_training_samples.py`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `49 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`
- `make files-sync`
  - `pass`
- `make verify-surfaces`
  - `pass`
- `cd ../dataset && pytest tests/unit/test_deployment_script_template_regressions.py tests/test_aks_module_generator_generate_modules.py::test_generate_modules_writes_bash_valid_deploy_script -q`
  - `15 passed`

## Not Verified In This Turn

- live AKS rerun
- live bundle activation with father-backed family reuse
- live per-turn batch queue upload
- coverage
- format / mypy / basedpyright

## Conclusion

The repository now matches the intended family-first contract better than the last inspected run:

- family lookup should route by `original_prompt`
- deploy-stage trusted handoff should prefer batch traces over the coarse fallback

But the fix is still only locally verified. One new live rerun is still required to confirm:

1. existing fathers are reused instead of synthesizing a new family
2. family runtime artifacts are selected when similarity exceeds the `0.8` gate
3. authoritative queue ingestion uses per-turn batch traces instead of the coarse single trace
