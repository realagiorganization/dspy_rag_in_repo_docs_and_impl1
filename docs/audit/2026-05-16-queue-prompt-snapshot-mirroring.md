# 2026-05-16 Queue Prompt Snapshot Mirroring

Preceding note: `2026-05-16-active-profile-summary-selectivity.md`

## Why this note exists

The latest live dataset run drained `queued/repo-rag-training/` successfully, but the exported and
processed trainer-side queue items still lost `original_prompt` and `reformulated_prompt` on the
top-level wrapper surfaces. The nested `trace_payload` still carried both fields, so the bug was a
surface-mirroring defect rather than a missing-runtime-trace defect.

## What changed

- `src/repo_rag_lab/runtime_artifacts.py`
  - added prompt snapshot mirroring for `question`, `original_prompt`, and
  `reformulated_prompt` before queue export;
  - queued trace items now persist those prompt fields on the top-level wrapper instead of only
    under `trace_payload`;
  - processed queue items inherit the corrected prompt snapshot because `drain_trace_queue()`
    uploads the mirrored queue item after import.
- `dataset`
  - `aks_module_generator/templates/deployment_script/part_4.txt`
  - `aks_modules/deploy.sh`
  now mirror `original_prompt` / `reformulated_prompt` into trusted queue wrappers and the
  rehydrated trusted payload path, instead of only preserving them inside the nested trace payload.
  - `docker/prompt-executor/worker_execution_prompt.py` now mirrors the representative prompt
    snapshot (`question`, `original_prompt`, `reformulated_prompt`) onto batch export/enqueue
    summaries as well, so `repo_rag_trace_export.json`, `repo_rag_turn_trace_export_batch.json`,
    and `repo_rag_turn_trace_enqueue_batch.json` no longer go blank on the top-level batch
    surface when the per-trace records already contain the right prompt data.

## Verification run this turn

Configured checks:

- `uv run python -m compileall src tests` -> pass
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py` -> pass
- `uv run repo-rag smoke-test` -> pass
- `cargo build --manifest-path rust-cli/Cargo.toml` -> pass

Targeted checks:

- `uv run pytest tests/test_runtime_artifacts_azure.py -k 'queue_trace_record_and_drain_trace_queue_use_azure_blob_queue'` -> pass
- `cd ../dataset && .venv/bin/pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py -k 'batches_turn_traces_for_queue_handoff'` -> pass
- `cd ../dataset && .venv/bin/pytest tests/unit/test_deployment_script_template_regressions.py -k 'trusted_trace_handoff_after_rehydration'` -> pass
- `cd ../dataset && .venv/bin/pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py -k 'stale_turn_trace_batch_when_final_proxy_reuses_family_artifact or batches_turn_traces_for_queue_handoff'` -> pass

Verification categories not exercised this turn:

- lint: not run
- type checking: no dedicated repository type-check suite run
- coverage: not run
- UI / notebook execution: not run
- live AKS deployment validation: not run

## Repository state after the fix

- queue wrappers should no longer drop `original_prompt` / `reformulated_prompt` on the
  top-level handoff payload;
- the dataset trusted handoff template now mirrors those same prompt fields in the batch and
  single-trace wrapper paths;
- batch export/enqueue summaries should now keep the representative prompt snapshot on their
  top-level surfaces instead of forcing downstream tooling to dive into individual trace records
  just to recover `question`, `original_prompt`, or `reformulated_prompt`;
- the remaining live unknown is trainer publish behavior after a fresh end-to-end rerun. This note
  fixes the broken prompt snapshot surface, but a fresh AKS run is still required to confirm that
  `repo-rag-training-families/current.json` and the next bundle version publish as expected after
  trainer drain.
