# 2026-05-15 Family Profile Routing And Handoff Hardening

## Summary

This turn closed two live defects and advanced the next DSPy family-routing slice.

Closed defects:

- runtime/exported trace records were still dropping the outer family success-profile fields
  (`family_predicted_hit_rate`, `family_predicted_hit_rate_lower_bound`,
  `family_prediction_uncertainty`, `family_feedback_count`) even though worker payloads already
  knew them;
- trusted AKS handoff was reconstructing `repo_rag_trusted_handoff_payload.json` from a stale
  field list, so live queue payloads still exposed the older family-runtime surface only.

New routing slice:

- prompt-family matching now persists and uses lightweight family-profile summaries:
  - `family_prompt_profile_terms`
  - `family_command_pattern_summary`
  - `family_constraint_summary`
- routing score now blends prompt similarity, family-profile overlap, success prior, and
  uncertainty penalty instead of staying a father-text-only comparison.

## Repository State Changed

Main repo and mirrored dataset submodule:

- `src/repo_rag_lab/runtime_artifacts.py`
- `src/repo_rag_lab/codex_proxy.py`
- `src/repo_rag_lab/training_samples.py`
- `tests/test_codex_proxy.py`
- `tests/test_training_samples.py`
- `tests/test_utilities.py`

Dataset top-level:

- `aks_module_generator/templates/deployment_script/part_4.txt`
- `aks_modules/deploy.sh`
- `tests/unit/test_deployment_script_template_regressions.py`

## Verification

Configured checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_training_samples.py` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_codex_proxy.py -k 'feedback_trace_for_successful_family_reuse'` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`
- `cd ../dataset && .venv/bin/pytest tests/unit/test_deployment_script_template_regressions.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py -k 'trusted_trace_handoff_after_rehydration or codex_proxy_path_exports_and_queues_repo_rag_trace or stale_turn_trace_batch_when_final_proxy_reuses_family_artifact'` — `pass`
- `cd ../dataset/submodules/dspy_rag_in_repo_docs_and_impl1 && UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` — `pass`
- `cd ../dataset/submodules/dspy_rag_in_repo_docs_and_impl1 && UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_training_samples.py` — `pass`
- `cd ../dataset/submodules/dspy_rag_in_repo_docs_and_impl1 && UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_codex_proxy.py -k 'feedback_trace_for_successful_family_reuse'` — `pass`

Configured checks not rerun in this turn:

- `make quality`
- `make coverage`

Verification categories still missing or not proven by this turn:

- UI checks — not found/run
- integration tests beyond the targeted dataset handoff path — not run
- lint/type-checking beyond `compileall` — not run
- coverage status — not run
- deployment/live AKS validation — not run

## Remaining Gap

The source-level contract is stronger now, but two end-to-end questions still require a new live
artifact review:

- whether the next worker run now preserves the richer family success profile all the way from
  runtime to queued/imported trainer input;
- whether the new family-profile routing actually reduces family over-splitting in live traces
  instead of only in local tests.
