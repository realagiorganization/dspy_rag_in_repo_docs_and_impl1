# AKS Run `25212955759`: Trace Handoff Skipped Because `repo-rag-storage-config` Lacks Blob Credentials

- Date: `2026-05-01`
- Scope: downstream `../dataset` AKS execution run `25212955759`
- Evidence sources:
  - local artifacts copied to `../dataset/artifacts`
  - live Kubernetes secret inspection in namespace `prompt-exec-1353735964635435100`
  - downstream workflow source in `../dataset/.github/workflows/parallel-prompt-execution-aks.yml`

## Summary

The latest AKS run proves that the worker-side repo-RAG proxy path is now alive:

- `backend_used = "codex_cli_repo_rag_proxy"`
- `repo_rag_codex_proxy_last.json` reports `mediation_mode = "rag_heuristic_dspy"`
- `rag_status = "success"`
- `trace_exported = true`

The remaining blocker is no longer Azure Responses API versioning or proxy bootstrap. The trace
handoff to the trainer-side Azure Blob + Queue transport is skipped because the generated
`repo-rag-storage-config` secret contains only the trace/bundle container names and queue name, but
no Azure Blob credentials.

As a result:

- `repo-rag-training-traces` stays empty because `trace-enqueue` never runs
- `repo-rag-bundles` also remains empty, which is still expected until a trainer publish/promote
  cycle is introduced or exercised

## Artifact Evidence

From `../dataset/artifacts/redis_results.json`:

- `success = true`
- `backend_used = "codex_cli_repo_rag_proxy"`
- `trace_handoff_status = "skipped"`
- `warnings = ["DSPy mediation was unavailable; using heuristic synthesis instead. (No compiled DSPy bundle is available.)"]`

From `all_artifacts.tar.gz`:

- `repo_rag_backend.json` reports:
  - `trace_exported = true`
  - `trace_queued = false`
  - `trace_handoff_mode = "queue"`
  - `trace_handoff_status = "skipped"`
  - `mediation_mode = "rag_heuristic_dspy"`
  - `rag_status = "success"`
  - `dspy_status = "heuristic"`
- `repo_rag_trace_export_command.txt` exists
- `repo_rag_trace.json` exists
- `repo_rag_trace_enqueue.json` does not exist
- `repo_rag_trace_enqueue_command.txt` does not exist

This shows that trace export succeeded, but the worker never reached the `trace-enqueue` command.

## Worker Code Path

The downstream worker only queues a trace when Blob/Queue storage is configured:

- `../dataset/docker/prompt-executor/worker_execution_prompt.py`
  - `_repo_rag_blob_storage_credentials_configured()`
  - `_repo_rag_trace_store_configured()`
  - queue handoff branch guarded by `if trace_import_root is not None or self._repo_rag_trace_store_configured():`

Because the run ended with `trace_handoff_status = "skipped"` and did not emit any
`repo_rag_trace_enqueue*` artifacts, that storage-configured check evaluated to false.

## Live Cluster Secret Evidence

Inspecting the live secret:

- `kubectl -n prompt-exec-1353735964635435100 get secret repo-rag-storage-config -o json`

Decoded payload:

- `DATASET_REPO_RAG_BUNDLE_CONTAINER = repo-rag-bundles`
- `DATASET_REPO_RAG_TRACE_CONTAINER = repo-rag-training-traces`
- `DATASET_REPO_RAG_TRACE_QUEUE_NAME = repo-rag-training`

Missing keys:

- `AZURE_STORAGE_ACCOUNT`
- `AZURE_STORAGE_KEY`
- `AZURE_STORAGE_CONNECTION_STRING`
- `REPO_RAG_AZURE_STORAGE_ACCOUNT`
- `REPO_RAG_AZURE_STORAGE_KEY`
- `REPO_RAG_AZURE_STORAGE_CONNECTION_STRING`

So the worker knows where traces should go, but not how to authenticate to Blob/Queue.

## Workflow Gap

The downstream workflow currently creates that mismatch itself:

- `Generate AKS modules` runs `python generate_aks_modules.py ...`
- that step does not export `AZURE_STORAGE_ACCOUNT`, `AZURE_STORAGE_KEY`, or
  `AZURE_STORAGE_CONTAINER`
- the later `Deploy with enhanced debugging` step does export those variables, but by then the
  repo-RAG secret YAML has already been generated

That means `create_repo_rag_storage_secret()` only serializes the container names/queue name during
module generation, because the credentials are not yet in the generator environment.

## Current Status

- Proxy bootstrap: pass
- Azure Responses API compatibility: pass
- RAG retrieval: pass
- DSPy mediation: degraded to heuristic because no compiled bundle is available
- Trace export: pass
- Trace enqueue to Azure Blob + Queue: blocked by workflow secret-generation gap

## Follow-Up

The next downstream fix should be in `../dataset`:

1. Export `AZURE_STORAGE_ACCOUNT`, `AZURE_STORAGE_KEY`, and `AZURE_STORAGE_CONTAINER` into the
   `Generate AKS modules` workflow step, not only the later deploy step.
2. Optionally fail fast when repo-RAG trace/bundle container names are configured but Blob
   credentials are missing at secret-generation time.
