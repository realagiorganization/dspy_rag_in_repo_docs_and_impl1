# Dataset Integration Plan

This checklist tracks the path for connecting the working `repo-rag + DSPy` code in this
repository to the `../dataset` pipeline without blocking pipeline execution on training.

## Scope

- The first integration path is direct runtime execution, not MCP-first orchestration.
- Workers should use the latest stable bundle plus repo-local RAG state.
- Global optimization should be asynchronous.

## Status

- [x] Confirm that the current repository already has working baseline RAG, DSPy compile/reload, retrieval evaluation, and utility surfaces.
- [x] Confirm that `../dataset` does not yet have a repo-native adapter for this runtime.
- [x] Define the preferred architecture as `global bundle + local overlay + async trainer`.

## Phase 1. Worker Runtime Contract

- [x] Define the JSON contract between `dataset` workers and `repo-rag`.
- [x] Decide the minimal worker inputs: `repo_path`, `task/question`, `bundle_version`, `overlay_path`, and runtime provider config.
- [x] Decide the minimal worker outputs: `answer`, `sources`, `retrieval_trace`, `token_usage`, `artifacts`, and error metadata.
- [x] Keep the first execution path CLI-based through `repo-rag`, not MCP-based.

Current first-pass contract:

- Baseline call: `uv run repo-rag ask --root <repo_path> --question "..." --output json`
- DSPy call: `uv run repo-rag ask --root <repo_path> --question "..." --use-dspy --output json`
- Live call: `uv run repo-rag ask-live --root <repo_path> --question "..." --output json`
- Retrieval regression call: `uv run repo-rag retrieval-eval --root <repo_path> --output json`
- Artifact inspection call: `uv run repo-rag dspy-artifacts --root <repo_path> --output json`
- Bundle inspection call: `uv run repo-rag bundle-inspect --root <repo_path> --channel stable --output json`
- Bundle fetch call: `uv run repo-rag bundle-fetch --root <repo_path> --channel stable --output json`
- Bundle publish call: `uv run repo-rag bundle-publish --root <trainer_repo> --run-name <bundle_run> --output json`
- Bundle promote call: `uv run repo-rag bundle-promote --root <trainer_repo> --channel stable --run-name <bundle_run> --output json`
- Bundle rollback call: `uv run repo-rag bundle-rollback --root <trainer_repo> --channel stable --output json`
- Local overlay init call: `uv run repo-rag overlay-init --root <repo_path> --output json`
- Post-run trace export call: `uv run repo-rag trace-export --root <repo_path> --payload-path <ask-output.json> --output json`
- Trainer-side trace ingest call: `uv run repo-rag trace-import --root <trainer_repo> --trace-path <worker-trace.json> --outcome-path <worker-outcome.json> --output json`
- Trainer-side trace queue call: `uv run repo-rag trace-enqueue --root <runtime_root> --trace-path <worker-trace.json> --queue-name dataset --outcome-path <worker-outcome.json> --output json`
- Trainer-side queue drain call: `uv run repo-rag trace-drain --root <trainer_repo> --queue-name dataset --output json`
- Trainer-side candidate-to-bundle recompile call:
  `uv run repo-rag trainer-recompile --root <trainer_repo> --run-name <bundle-run> --output json`

The `--root` path above is now validated by repository tests against arbitrary temporary git
repositories, not only against this repository's own root. The same CLI family now also supports
an explicit `--retrieval-mode lexical|idf-rerank` override while keeping the repo-local profile
default available for worker-side reuse.

Current shared envelope fields:

- `command`
- `command_status`
- `root`
- `warnings`
- `artifact_metadata`

Current ask-family result fields:

- `question`
- `answer`
- `response_text`
- `sources`
- `context`
- `mcp_candidates`
- `mode`
- `bundle_version`
- `overlay_path`
- `trace`

Current first-pass worker inputs:

- required now: `repo_path`
- required now: `question` or `task`
- required now: an execution choice that maps to baseline `ask`, DSPy `ask --use-dspy`, or `ask-live`
- required when the selected mode needs it: runtime provider config such as Azure/OpenAI or `DSPY_*`
- optional now: `retrieval_mode` when the worker wants to override the repo-local profile default
- optional now: `bundle_version` when a worker wants to pin or annotate the selected bundle
- optional now: `overlay_path` when a worker wants to persist or reuse a local overlay manifest

Current first-pass worker outputs:

- `answer`
- `sources`
- `context` or `retrieved_context` as the retrieval trace payload
- `trace` as the stable runtime-trace payload
- `artifact_metadata` as the artifact handoff payload
- `warnings`
- `error.type` and `error.message` on failures
- reserved for a later runtime pass: `token_usage`

Current DSPy ask additions:

- `retrieved_context`
- `program_loaded`
- `program_path`
- `top_k`

Current artifact-lifecycle additions:

- `bundle-inspect --channel stable|canary` returns the promoted channel state plus the current
  published bundle version, benchmark status, and related artifact paths
- `bundle-publish` materializes a published bundle record under `artifacts/dspy/published/`
- `bundle-promote` materializes a channel state under `artifacts/dspy/channels/<channel>.json`
- `bundle-rollback` re-points that channel to a previous or explicit published bundle version
- `overlay-init` materializes `artifacts/overlays/<name>/overlay.json` and returns retrieval-mode,
  lookup-index, trace-dir, and worker-adaptation-scope metadata
- `trace-export` materializes a normalized trace record under `artifacts/traces/`
- `trace-import` ingests a normalized trace record plus optional worker outcome metadata under
  `artifacts/traces/imported/`
- `bundle-fetch` downloads one promoted or explicitly versioned bundle into
  `artifacts/dspy/remote/<bundle_version>/`
- `trace-enqueue` stages a normalized trace record plus optional worker outcome metadata in the
  global Azure Blob + Queue transport when storage credentials are configured, and only falls back
  to `artifacts/traces/queued/<queue>/` in local single-repository mode
- `trace-drain` consumes queued trainer-side handoff items from Azure Queue or the local fallback
  queue and writes imported records under `artifacts/traces/imported/`

Current error contract:

- `command_status: "error"`
- `error.type`
- `error.message`

## Phase 2. Bundle And Overlay Lifecycle

- [x] Implement stable bundle fetch at worker start.
- [x] Build repo-local retrieval artifacts and local overlay state inside the worker before answering.
- [x] Persist repo-local traces after the worker run.
- [x] Ingest accepted outcomes after the worker run.
- [x] Keep worker-local adaptation lightweight until the global bundle loop is stable.

## Phase 3. `dataset` Backend Work

- [x] Add a `repo_rag_cli` backend to `../dataset`.
- [x] Teach the worker/runtime flow to recognize repositories that expose `repo-rag`.
- [x] Add post-run trace upload hooks that do not block the main pipeline result.
- [x] Store retrieval and DSPy artifacts as worker outputs when relevant.

Current implementation note:

- The local `../dataset` `PromptExecutor` now supports `execution_method="repo_rag_cli"` and
  routes `execution_method="dspy"` through the same backend.
- That backend calls `repo-rag ask --output json`, persists the JSON envelope plus trace under
  prompt artifacts, and resolves the analyzed repo root from prompt fields or
  `DATASET_REPO_RAG_TARGET_ROOT`.
- The `dspy` alias first attempts `repo-rag ask --use-dspy` and then falls back to baseline
  `repo-rag ask` when DSPy LM credentials are unavailable.
- The AKS worker path in `../dataset/docker/prompt-executor/` now uses the same backend family:
  it supports `execution_method="repo_rag_cli"` and `execution_method="dspy"`, resolves the
  analyzed repository from the prepared worker checkout, auto-initializes a local overlay through
  `repo-rag overlay-init` when no explicit overlay is supplied, persists `repo_rag_*.json`
  artifacts plus compatibility `codex_response.txt`, and exports a normalized trace through
  `repo-rag trace-export`.
- The worker-side default `codex` path now no longer switches execution methods to get repo-RAG
  help. Instead it launches a local `repo-rag serve-codex-proxy`, rewrites Codex Azure config to
  target that local Responses-compatible endpoint, and lets the proxy inject `RAG + DSPy`
  mediation into the live Codex request with fallback to heuristics or direct pass-through when the
  mediation layers are unavailable. That proxy path is now also token-budgeted, source-pruned,
  low-signal-aware, and backed by a filesystem cache so the default `codex` loop does not pay for
  unbounded repeated prompt inflation.
- The explicit local executor and worker `repo_rag_cli` / `dspy` paths now support a first-pass
  bundle/trace lifecycle: they can resolve a stable bundle version from the global bundle store
  through `repo-rag bundle-inspect --channel stable`, fetch the actual DSPy program through
  `repo-rag bundle-fetch`, and then stage the exported trace into the global Azure Blob + Queue
  transport through `repo-rag trace-enqueue` or, when explicitly requested, import it directly
  through `repo-rag trace-import`, with warnings instead of hard failures when those sidecar steps
  are unavailable.
- Those explicit `repo_rag_cli` / `dspy` runtime paths now also persist `repo_rag_outcome.json`
  and pass it to `repo-rag trace-import --outcome-path ...` or
  `repo-rag trace-enqueue --outcome-path ...`, so trainer-side imported or queued trace records now
  carry accepted/candidate/rejected execution outcome metadata instead of only raw retrieval traces.
- Those explicit `repo_rag_cli` / `dspy` runtime paths now default to
  `DATASET_REPO_RAG_TRACE_HANDOFF_MODE=queue` semantics when either a trainer root or global Azure
  Blob + Queue storage is available, persist `repo_rag_trace_enqueue.json` beside the other worker
  artifacts, and keep direct `trace-import` available as an explicit compatibility mode via
  `DATASET_REPO_RAG_TRACE_HANDOFF_MODE=import`.
- The default worker `codex` proxy path now also closes the trainer-handoff gap: it can resolve
  bundle provenance for mediation, persist `repo_rag_codex_proxy_last.json`, export a normalized
  repo-rag trace after `codex exec`, and hand that trace off through `trace-enqueue` or
  `trace-import` with the same outcome metadata contract used by the explicit repo-rag runtime
  paths. The worker/container wiring now also forwards explicit non-secret
  `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME`, `AZURE_OPENAI_API_VERSION`, and
  `AZURE_OPENAI_MODEL_NAME` values to the proxy subprocess, derived from either worker env or
  `CODEX_AZURE_CONFIG`, so Azure-auth mediation can bootstrap without a repo-local `.env`; the
  same downstream worker/runtime path now also defaults missing Azure Responses API versions to
  `2025-03-01-preview` and lets explicit `AZURE_OPENAI_API_VERSION` override any stale
  `query_params.api-version` preserved in `CODEX_AZURE_CONFIG`. The newest AKS trace evidence shows
  that this path now reaches successful proxy mediation plus trace export in-cluster, but the
  global trainer handoff still stops at `trace_handoff_status = "skipped"` because the
  `Generate AKS modules` workflow step creates `repo-rag-storage-config` before Blob credentials
  are exported into the generator environment. The current downstream remediation now avoids
  solving that by leaking storage credentials into worker pods; instead it performs trusted
  post-processing trace enqueue after `execution_artifacts` rehydration in the deploy stage, where
  Azure storage credentials already exist and Codex cannot read them from its own environment.
- The trainer repository now also exposes `repo-rag trainer-cycle`, which wraps queue drain,
  retrieval gating, and optional bundle publish/promotion in one background-compatible pass so the
  next iteration can schedule it as a CronJob/systemd timer before introducing a fuller trainer
  service.
- The trainer repository now also exposes `repo-rag trainer-service`, which wraps that same
  lifecycle in a long-running polling loop with persisted `artifacts/trainer/service-state.json`
  and per-cycle history records under `artifacts/trainer/history/`, so queue draining can now live
  outside the worker hot path without inventing a second orchestration contract.
- The trainer repository now also exposes `repo-rag trainer-recompile`, and both
  `trainer-cycle` and `trainer-service` can invoke the same candidate-to-bundle recompilation path
  after queue drain, so imported worker traces now have a concrete route into generated DSPy
  compile inputs under `artifacts/trainer/generated-training.yaml`.
- The worker-side `codex` path now attempts that mediation proxy for any repository-like prepared
  clone by default, so repo-aware augmentation no longer depends on replacing `codex` with an
  explicit `repo_rag_cli` backend. The local compatibility executor still keeps explicit
  `repo_rag_cli` auto-detection because it does not run the full worker-side Codex path.
- Remaining AKS follow-up work is now about the background trainer/publisher service and
  promotion-policy rollout rather than about basic backend availability.

## Phase 4. Global Training Loop

- [x] Stage worker traces into a trainer-side queue so the worker hot path no longer depends on synchronous trainer-side import.
- [x] Add a single-pass trainer cycle that can drain the queue and apply bundle gates in a cron/Kubernetes-job-friendly way.
- [x] Stand up an asynchronous trainer/publisher service outside the worker hot path.
- [x] Ingest worker traces, accepted edits, failures, retrieval misses, and benchmark outcomes into that service.
- [x] Recompile and validate new bundles without forcing the originating pipeline run to wait.
- [x] Publish only versions that clear the selected benchmark and safety gates.

## Phase 5. Deployment Model

- [x] Use one shared runtime image family rather than Docker-in-Docker.
- [x] Separate worker runtime responsibilities from trainer responsibilities.
- [x] Store bundles and promotion metadata in shared storage or registry-backed artifacts.
- [x] Decide whether central inference stays external or becomes a shared internal service.

Current implementation note:

- The repository now exposes `repo-rag trainer-k8s-manifests` plus `make trainer-k8s-manifests`,
  which materialize a ServiceAccount, ConfigMap, example Secret, `trainer-service` Deployment, and
  `trainer-cycle` CronJob under `artifacts/kubernetes/`.
- For the `dataset` path the intended queue example is `TRACE_QUEUE_NAME=dataset`; the runtime
  surface stays generic, but the documented manifests now show that queue explicitly.
- Those manifests assume one shared repo-RAG runtime image, a PVC-backed `/workspace/repo-rag/artifacts`
  trainer-local cache/state mount, global Azure Blob + Queue storage for traces/bundles, and
  separate worker vs. trainer roles rather than Docker-in-Docker.
- The current central inference choice is now explicit: keep inference external first through Azure
  OpenAI or Azure AI Inference, reuse that same provider contract across workers and trainer-side
  recompilation, and defer any shared internal model-serving tier until economics or compliance
  pressures justify replacing the proven external contract.

## Phase 6. Optional MCP Layer

- [x] Add MCP only for short bounded calls such as status, artifact listing, trace publish, or lightweight ask surfaces.
- [x] Do not route heavy DSPy training or long retrieval evaluations through a single MCP request lifecycle.
- [x] Document where MCP adds value and where direct runtime execution remains the correct path.

Current implementation note:

- The repository now exposes `repo-rag serve-mcp` plus `make serve-mcp`, a bounded stdio MCP
  server that advertises exactly four short-running tools:
  - `ask_repo`
  - `bundle_status`
  - `dspy_artifacts`
  - `publish_trace`
- The MCP surface deliberately excludes `dspy-train`, `trainer-recompile`, `trainer-cycle`,
  `trainer-service`, `retrieval-eval`, and notebook execution, so the primary integration path for
  `dataset` remains direct CLI execution with JSON envelopes rather than long-lived work tunneled
  through one MCP request lifecycle.

## Exit Criteria

- [x] A `dataset` worker can pull a stable bundle, build a repo-local overlay, answer through `repo-rag`, and upload traces.
- [x] The main pipeline run never blocks on global retraining.
- [x] New bundles are published asynchronously and become available to later workers.
- [x] The integration path is documented well enough to move from local runs to Kubernetes worker pools.
