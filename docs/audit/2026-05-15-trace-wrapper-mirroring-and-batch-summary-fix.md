# 2026-05-15 Trace Wrapper Mirroring And Batch Summary Fix

## Scope

This note records the follow-up after a live worker run still showed two remaining handoff defects:

- trusted queue-item wrappers dropped `prompt_family_band`, `trainer_signal_kind`, and family
  success-posterior fields at the outer payload layer even though those values already existed
  inside `trace_payload.trace`;
- worker-side batch enqueue summaries could report repeated `generated_paths` with the final
  `...-N.json` suffix because the handoff loop reused the last exported trace name for every
  queue-enqueue call.

## Changes

1. `src/repo_rag_lab/runtime_artifacts.py`
   - queued trainer-side trace items now mirror the nested runtime family/trainer signal fields
     onto the queue-item top level;
   - the stored `trace_payload` is also backfilled so command-envelope inputs keep the same
     mirrored fields before they reach trainer-side import.
2. `../dataset/docker/prompt-executor/worker_execution_prompt.py`
   - batch export/enqueue item summaries now record item-level trainer/family signal fields;
   - batch summary payloads now expose aggregate signal surfaces instead of leaving those values
     implicit inside nested trace payloads;
   - the handoff loop now uses each item's own trace name, fixing repeated `generated_paths`
     that previously collapsed onto the final batch suffix.
3. The same runtime-artifact mirroring changes were mirrored into
   `../dataset/submodules/dspy_rag_in_repo_docs_and_impl1/src/repo_rag_lab/runtime_artifacts.py`.

## Verification

Configured checks touched by this change:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_runtime_artifacts_azure.py`
- `cd ../dataset && .venv/bin/pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py`

Executed in this turn:

- `uv run python -m compileall src tests` — pass
- `uv run pytest tests/test_runtime_artifacts_azure.py -k 'queue_trace_record_and_drain_trace_queue_use_azure_blob_queue'` — pass
- `cd ../dataset && .venv/bin/python -m compileall docker/prompt-executor/worker_execution_prompt.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py` — pass
- `cd ../dataset && .venv/bin/pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py -k 'pid-codex-batch or pid-codex'` — pass
- `cd ../dataset/submodules/dspy_rag_in_repo_docs_and_impl1 && uv run python -m compileall src tests` — pass
- `cd ../dataset/submodules/dspy_rag_in_repo_docs_and_impl1 && uv run pytest tests/test_runtime_artifacts_azure.py -k 'queue_trace_record_and_drain_trace_queue_use_azure_blob_queue'` — pass

## Current Status

- Source now preserves the trainer-visible signal surface at the queue-item wrapper level instead
  of only inside nested runtime trace payloads.
- Worker-side batch export/enqueue summaries now expose item-level signal fields and no longer
  collapse `generated_paths` onto the last exported trace name.
- A new live worker/trainer run is still required before claiming the deployed pipeline already
  emits these corrected wrapper and summary surfaces in AKS artifacts.
