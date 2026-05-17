# 2026-05-17 CI And Dataset Repair

- Scope: clear the known post-push breakages in `dspy_rag_in_repo_docs_and_impl1` and the sibling
  `dataset` repository, then verify the repaired paths locally.
- Preceding note: `2026-05-17-family-trace-count-publish-repair.md`

## Issues Addressed

### `dspy_rag_in_repo_docs_and_impl1`

- `CI / Python Quality, Tests, And Build` failed because `ruff format --check` wanted to rewrite
  `src/repo_rag_lab/training_samples.py`.
- `Publication PDF` failed because `samples/logs/...md` contained literal control characters that
  leaked into `publication/exploratorium_translation/generated/exploratorium-content.tex`.
- `make quality` additionally exposed three unused local variables in
  `tests/test_training_samples.py`.

### `dataset`

- The previously failing worker/test cluster covered deployment script rendering, Discord webhook
  resolution, prompt execution metadata handling, Codex CLI test-mode guard behavior, repo-rag
  bundle fallback, worker finalize branch restoration, and queue attachment token resolution.

## Source Fixes Landed

### In `dspy_rag_in_repo_docs_and_impl1`

- `src/repo_rag_lab/exploratorium_translation.py`
  - strips control characters while reading tracked text before LaTeX generation
- `tests/test_exploratorium_translation.py`
  - regression coverage added for control-character stripping
- `src/repo_rag_lab/training_samples.py`
  - formatter-normalized to satisfy `ruff format --check`
- `tests/test_training_samples.py`
  - removed/used the unused locals that blocked `ruff check`

### In `dataset`

- `aks_module_generator/mixins/deployment_script.py`
  - optional PVC/volume attributes are now resolved via `getattr(...)` so dummy deployment objects
    used in tests do not explode on missing attributes
- `docker/prompt-executor/execute_worker_prompts_impl.py`
  - summary generation skips Codex guard preflight in `EXECUTOR_TEST_MODE`
  - worker authentication setup now respects test mode instead of requiring live auth
- `docker/prompt-executor/worker_codex_cli_exec.py`
  - Codex CLI guard preflight no longer blocks test-mode execution paths
- `docker/prompt-executor/worker_execution_prompt.py`
  - `_build_final_prompt(...)` again receives the full metadata-rich prompt body
  - the actual Codex execution path still gets the runtime-sanitized body
  - explicit invalid bundle-version fallback now prefers staged local bundle state before channel
    lookup
- `docker/prompt-executor/worker_repo_finalize.py`
  - remote branch existence checks are now guarded for minimal dummy workers
- `docker/queue-initializer/init_queue_core.py`
  - attachment token resolution now reuses the root-resolution helper and reports the resolved
    filename correctly
- `src/notifications/discord_publisher/webhook_resolution_core.py`
  - string thread channel types now preserve `thread_id` resolution

## Verification

Checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run ruff format --check src tests` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_exploratorium_translation.py tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — `pass` (`62 passed`)
- `make exploratorium-build` — `pass`
- `make paper-build` — `pass`
- `make quality` — `pass` (`366 passed`, `3 skipped`, coverage `81.36%`)
- `python -m pytest tests/unit/test_deployment_script_mixins.py tests/unit/test_deployment_script_missing_templates.py tests/bdd/test_discord_publisher.py tests/unit/test_discord_publisher_webhook_resolution_core_more.py tests/unit/test_execute_worker_prompts_impl_codex_logging.py tests/unit/test_worker_execution_prompt_more.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/unit/test_worker_repo_finalize_more.py tests/unit/test_init_queue_core_helpers.py -q` — `pass` (`301 passed`)

Checks not executed in this turn:

- No fresh GitHub Actions run was observed yet after these local repairs
- No live Azure/pipeline rerun was executed for the `dataset` worker stack

## Current Status

- The known `dspy_rag_in_repo_docs_and_impl1` local breakages are cleared: formatter, quality, and
  publication build all pass locally.
- The known `dataset` regression cluster that had been failing in CI now passes locally.
- Remaining operational confirmation is external: a fresh push/run is still required to confirm the
  repaired state in GitHub Actions for both repositories.
