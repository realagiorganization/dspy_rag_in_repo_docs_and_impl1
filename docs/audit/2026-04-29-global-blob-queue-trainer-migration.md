# 2026-04-29 Global Blob And Queue Trainer Migration

## Summary

- Migrated the repo-RAG trainer lifecycle away from the namespace-local shared-PVC queue contract
  and onto Azure Blob + Azure Queue as the primary cross-namespace transport.
- Added repo-native Azure artifact helpers in `src/repo_rag_lab/azure_artifacts.py` so `repo-rag`
  can:
  - upload queued trace records into a global Blob container
  - emit Azure Queue messages for trainer-side ingestion
  - publish promoted bundle assets into a global bundle container
  - fetch globally promoted bundles back into a worker-local cache
- Added a new `repo-rag bundle-fetch` surface and taught `repo-rag ask --use-dspy` to resolve a
  remote bundle version or channel before falling back to local bundle manifests.
- Reworked `trace-enqueue` / `trace-drain` so Azure Blob + Queue is the first-class transport when
  storage credentials are configured, while retaining the filesystem queue as a local fallback.
- Updated `../dataset` so both the local executor and the container worker path can:
  - fetch the stable bundle from global Blob storage without a shared trainer root
  - enqueue traces and outcome metadata into the global Blob + Queue transport without a shared PVC
  - treat `DATASET_REPO_RAG_TRAINER_ROOT` as a compatibility path instead of a mainline
    requirement
- Reworked AKS manifest generation and trainer deployment wiring so:
  - worker jobs receive a storage secret for Blob + Queue transport
  - worker-side shared repo-RAG PVC mounting is disabled by default
  - the trainer PVC remains, but only as a trainer-local cache/history volume
  - the deploy script bootstraps the trace container, bundle container, and queue automatically

## Why This Turn Happened

The prior queue-first implementation still assumed that worker pods and the trainer could share the
same namespace-local filesystem queue and bundle directory. That blocked the desired topology:

- guild-specific worker namespaces keep their own existing PVCs for local execution state
- one global trainer ingests traces from every namespace
- one promoted DSPy bundle is readable by workers in every namespace

Blob + Queue makes that topology possible without changing the existing guild-local PVC model.

## Current Contract

- Worker-local PVCs remain guild-specific and are not part of the global DSPy learning bus.
- Cross-namespace sharing now happens through Azure storage:
  - traces and outcomes upload into the global trace Blob container
  - an Azure Queue message notifies the trainer about each queued trace
  - promoted bundle assets publish into the global bundle Blob container
  - workers fetch the current stable bundle via `bundle-inspect` + `bundle-fetch`
- The trainer no longer depends on sharing a namespace-local PVC with worker jobs for the main DSPy
  learning loop.
- The trainer PVC is retained only for trainer-local cache/state/history material such as:
  - generated training candidates
  - service state
  - downloaded bundle cache
  - trainer history
- Worker-side repo-RAG shared-PVC support remains in `../dataset` only as an explicit
  compatibility path for local/file-backed workflows.

## Verification

Repo-local:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_runtime_artifacts_azure.py tests/test_utilities.py tests/test_cli_and_dspy.py`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Dataset-targeted:

- `python -m compileall src tests docker/prompt-executor aks_module_generator`
- `pytest tests/unit/test_prompt_executor_repo_rag_cli.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/test_aks_module_generator_manifests.py tests/unit/test_aks_volume_and_base_fallbacks.py tests/unit/test_deploy_repo_rag_trainer_script.py`
- `bash -n deploy_repo_rag_trainer.sh`

Repository surfaces:

- `make files-sync`
- `make exploratorium-sync`
- `make exploratorium-build`
- `make paper-build`
- `make verify-surfaces`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

## Remaining Boundary

- The global trainer story now depends on Azure storage credentials and container/queue provisioning
  rather than on namespace-local shared PVCs. That is the intended production direction.
- The local filesystem queue and local bundle manifests remain supported as fallbacks so the repo
  can still run without Azure storage during local development or isolated verification work.
- This turn does not introduce a separate Azure Queue consumer service beyond the existing
  `trainer-service` / `trainer-cycle` loop. The trainer still owns drain, materialization,
  recompilation, and publish/promote logic.
