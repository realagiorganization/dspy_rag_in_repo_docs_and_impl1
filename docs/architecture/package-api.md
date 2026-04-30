# Package API Notes

This repository keeps notebook logic in small Python modules under `src/repo_rag_lab/` so
notebooks stay readable, testable, and aligned with CLI and automation entrypoints.

## Core Workflow Modules

- `workflow.py`: baseline repository-grounded retrieval and deterministic answer rendering with
  explicit question, answer, evidence, and MCP-candidate sections.
- `dspy_workflow.py`: DSPy-shaped retriever and response flow when DSPy is installed.
- `dspy_training.py`: DSPy compile, artifact persistence, latest-run inspection, and LM resolution.
- `runtime_artifacts.py`: versioned bundle manifests, worker-local overlay manifests, and stable
  runtime-trace payload construction.
- `corpus.py`: repository text discovery and document loading with source paths normalized
  relative to the selected repository root.
- `retrieval.py`: paragraph-aware chunking, profile-aware lexical ranking, optional `idf-rerank`
  second-stage scoring, and source-diversified retrieval helpers.
- `retrieval_profile.py`: generic retrieval defaults plus repo-local config loading from
  `config/retrieval-profile.json`.
- `mcp.py`: repo-local MCP server candidate discovery.
- `mcp_server.py`: bounded stdio MCP server that wraps only short-running repo-RAG operations.

## Notebook-Facing Modules

- `notebook_support.py`: repository-root resolution, notebook assertions, and notebook run logging.
- `notebook_runner.py`: monitored batch execution, `.env` loading, and report generation for all tracked notebooks.
- `notebook_scaffolding.py`: high-level training, workflow, population, and fixture-specific scaffolds used directly by notebooks.
- `training_samples.py`: training sample loading, summarization, and validation.
- `population_samples.py`: population candidate loading, extension, validation, and empirical re-ranking.
- `benchmarks.py`: retrieval benchmark assertions derived from training samples.

## Utility Surfaces

- `repo-rag ask --question "..."`: run the baseline or DSPy-shaped RAG workflow; the baseline
  path prints `Question:`, `Answer:`, and `Evidence:` sections, while `--output json` returns a
  machine-readable envelope with `command`, `command_status`, `warnings`,
  `artifact_metadata`, `sources`, `context`, and `mcp_candidates`. The same surface now accepts
  `--retrieval-mode lexical|idf-rerank` for worker-side overrides.
- `repo-rag dspy-train --run-name ...`: compile and persist a repository-grounded DSPy program.
- `repo-rag dspy-artifacts`: inspect saved DSPy runs and the latest compiled program path through a
  shared JSON command envelope; when no compiled runs exist yet, the command still succeeds and
  reports that state through `warnings`.
- `repo-rag bundle-inspect`: inspect the latest or named versioned DSPy bundle manifest with
  bundle version, provenance, benchmark status, and related artifact paths, or inspect a promoted
  `stable` / `canary` channel state through `--channel`.
- `repo-rag bundle-publish`: persist a compiled DSPy bundle into the local published-bundle
  registry under `artifacts/dspy/published/`.
- `repo-rag bundle-promote`: point a persisted `stable` or `canary` channel at one published DSPy
  bundle version and record channel history under `artifacts/dspy/channels/`.
- `repo-rag bundle-rollback`: move one persisted bundle channel back to an earlier published DSPy
  bundle version without deleting the published record history.
- `repo-rag bundle-fetch`: download one promoted or explicitly versioned bundle from the global
  Azure Blob bundle store into `artifacts/dspy/remote/` so workers can run DSPy against a
  globally published program.
- `repo-rag overlay-init`: create or refresh a worker-local overlay manifest under
  `artifacts/overlays/` so downstream workers can record retrieval-mode and trace-dir state before
  answering.
- `repo-rag trace-export`: persist a normalized runtime trace record under `artifacts/traces/`
  from an ask-family JSON payload or an equivalent raw runtime trace.
- `repo-rag trace-import`: validate and ingest an external runtime trace record under
  `artifacts/traces/imported/` for later optimization or trainer-side aggregation; optional
  outcome metadata can be attached during import so trainer-side ingestion sees both the trace and
  the worker outcome in one record.
- `repo-rag trace-enqueue`: stage that same trace record, plus optional outcome metadata, either
  into the global Azure Blob + Queue transport or, when storage is not configured, into
  `artifacts/traces/queued/<queue>/`, so a trainer loop can pick it up later without forcing a
  synchronous import inside the worker hot path.
- `repo-rag trace-drain`: consume queued trainer-side handoff items from Azure Queue or the local
  filesystem queue and write the normalized imported trace records under
  `artifacts/traces/imported/`.
- `repo-rag trainer-candidates`: convert imported trace records into cumulative trainer-side YAML
  candidate examples plus a JSON summary under `artifacts/trainer/`.
- `repo-rag trainer-recompile`: merge the base YAML training set with those cumulative
  trainer-side candidates, write `artifacts/trainer/generated-training.yaml`, and compile a fresh
  DSPy run from the generated corpus.
- `repo-rag trainer-cycle`: run one background-compatible trainer pass that drains queued traces,
  evaluates retrieval gates, and optionally publishes/promotes a bundle when the selected quality
  thresholds pass. The cycle payload now also includes an `ingestion_summary` over the imported
  trace records for acceptance status, execution status, retrieval mode, bundle version, and empty
  source/context counts, plus `training_candidates` metadata for the cumulative trainer-side YAML
  and optional `recompile` metadata when the cycle also materializes a merged trainset and compiles
  a fresh DSPy run. When recompilation is in play, the cycle now also emits a `bundle_gate`
  payload and blocks publish/promotion until the selected DSPy benchmark pass-rate threshold is met.
- `repo-rag trainer-service`: run a long-lived trainer/publisher loop that repeatedly executes
  the same queue-drain and gate workflow, while persisting service state and per-cycle history
  under `artifacts/trainer/`. The service payload also aggregates those ingestion counters across
  all executed cycles, tracks how many cycles produced or skipped trainer-side recompilation, and
  records how many cycles were blocked by trainer-side bundle benchmark gates.
- `repo-rag trainer-k8s-manifests`: materialize AKS/Kubernetes manifests for the trainer-side
  Deployment and CronJob roles under `artifacts/kubernetes/`, including a shared ConfigMap,
  ServiceAccount, and example Secret for Azure-backed DSPy recompilation plus Blob/Queue-backed
  global training transport.
- `repo-rag ask-live --question "..."`: run baseline retrieval locally, then synthesize a live
  answer through Azure OpenAI or Azure AI Inference; `--output json` returns the same shared
  machine-readable envelope shape as `ask`.
- `repo-rag retrieval-eval`: emit the retrieval benchmark suite as JSON with shared command
  metadata, threshold-aware `command_status`, and artifact metadata for downstream runners.
- `repo-rag discover-mcp`: inspect MCP discovery candidates.
- `repo-rag serve-mcp`: expose the bounded stdio MCP server for lightweight `ask_repo`,
  `bundle_status`, `dspy_artifacts`, and queued `publish_trace` calls only. Trainer-side
  recompilation, notebook execution, and retrieval-eval sweeps intentionally stay off this MCP
  surface.
- `repo-rag smoke-test`: run a compact workflow smoke test.
- `repo-rag verify-surfaces`: validate the repository utility and notebook contract surfaces.
- `repo-rag run-notebooks`: execute all tracked notebooks with monitored progress and report artifacts.
- `repo-rag azure-manifest`: write Azure deployment metadata for downstream deployment workflows.
- `repo-rag azure-openai-probe`: normalize and validate the Azure OpenAI runtime contract.
- `repo-rag azure-inference-probe`: normalize and validate the Azure AI Inference runtime contract.

The ask-family JSON payloads now also include:

- `bundle_version` and `overlay_path` as explicit worker-facing fields.
- `trace`, a stable runtime payload that records mode, retrieval mode, top-k, source list, context
  count, and optional DSPy/live-provider metadata for later asynchronous optimization.

Persisted trace records intentionally separate command metadata from source payload metadata:

- the command envelope still owns top-level `artifact_metadata`
- persisted trace records store source payload details under `source_artifact_metadata`,
  `source_warnings`, and `source_error`
