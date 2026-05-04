# Dataset Integration Plan

This checklist tracks the path for connecting the working `repo-rag + DSPy` code in this
repository to the `../dataset` pipeline without blocking pipeline execution on training.

## Scope

- The first integration path is direct runtime execution, not MCP-first orchestration.
- Workers should use one explicitly pinned global bundle version plus repo-local RAG state.
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
- Bundle fetch call: `uv run repo-rag bundle-fetch --root <repo_path> --bundle-version <timestamp_version> --output json`
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
an explicit `--retrieval-mode lexical|idf-rerank|vector|hybrid-vector` override while keeping the
repo-local profile default available for worker-side reuse. Runtime-generated worker scaffolding
such as `prompt_artifacts/`, `_context_repos/`, and `.repo_rag_cache/` is now treated as
non-corpus data, and the worker path should persist prompt traces under execution artifacts rather
than back into the analyzed repository tree.

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
  - `vector` and `hybrid-vector` require `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME`; otherwise the
    runtime now falls back to lexical ranking and records a retrieval warning in the trace payload
- optional now: `bundle_version` when a worker wants to override the deployment-wide `DSPY_BUNDLE_VERSION` pin or annotate the selected bundle
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
- `bundle-publish` materializes a published record for one immutable bundle version under
  `artifacts/dspy/published/`
- `bundle-promote` materializes a channel state under `artifacts/dspy/channels/<channel>.json`
  that points to a specific published bundle version instead of a mutable trainer run alias
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
- [x] Mirror the promoted `stable` bundle into the artifacts PVC so workers can resolve it locally without blob credentials.
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
  bundle/trace lifecycle: they primarily consume one immutable bundle version pinned through
  `DSPY_BUNDLE_VERSION` (or an explicit prompt-side `bundle_version` override), fetch that exact
  DSPy program through `repo-rag bundle-fetch`, and only fall back to `repo-rag bundle-inspect
  --channel stable` when no version pin is configured. They then stage the exported trace into the
  global Azure Blob + Queue transport through `repo-rag trace-enqueue` or, when explicitly
  requested, import it directly through `repo-rag trace-import`, with warnings instead of hard
  failures when those sidecar steps are unavailable.
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
  `query_params.api-version` preserved in `CODEX_AZURE_CONFIG`. The newest AKS trace evidence now
  shows that this path reaches successful proxy mediation plus trace export in-cluster, and the
  follow-up trusted downstream handoff now enqueues trainer items after `execution_artifacts`
  rehydration in the deploy stage without leaking storage credentials into worker pods.
- The trainer repository now also exposes `repo-rag trainer-cycle`, which wraps queue drain,
  retrieval gating, and optional bundle publish/promotion in one background-compatible pass so the
  next iteration can schedule it as a CronJob/systemd timer before introducing a fuller trainer
  service.
- The trainer repository now also exposes `repo-rag trainer-service`, which wraps that same
  lifecycle in a long-running polling loop with persisted `artifacts/trainer/service-state.json`
  and per-cycle history records under `artifacts/trainer/history/`, so queue draining can now live
  outside the worker hot path without inventing a second orchestration contract; the current live
  AKS deployment now consumes the global `repo-rag-training` queue through Azure storage
  credentials and can remote-publish bundle versions into `repo-rag-bundles`.
- The trainer repository now also exposes `repo-rag trainer-recompile`, and both
  `trainer-cycle` and `trainer-service` can invoke the same candidate-to-bundle recompilation path
  after queue drain, so imported worker traces now have a concrete route into generated DSPy
  compile inputs under `artifacts/trainer/generated-training.yaml`; the trainer now treats
  `TRAINER_RECOMPILE_RUN_NAME` as a run family such as `trainer-auto`, mints a unique immutable
  `bundle_version` such as `<timestamp>` for every successful recompile, records the imported
  trace paths plus candidate dedupe counters in bundle lineage metadata, and leaves optional
  `stable` / `canary` channel state plus rollback/promote operations pointed at those concrete
  versioned bundles instead of overwriting one mutable trainer alias. The primary worker-side
  runtime selector is now the deployment-wide `DSPY_BUNDLE_VERSION` pin rather than a mandatory
  channel lookup, while repository-local deployment defaults now promote `stable` unless an
  operator intentionally clears `TRAINER_PROMOTE_CHANNEL`. When that pin is absent or a
  placeholder such as `0`, the deploy-stage runner now mirrors `channels/stable.json` plus the
  referenced immutable bundle assets into the artifacts PVC under `.repo_rag_bundle_store/`, and
  workers resolve `stable` through `DATASET_REPO_RAG_BUNDLE_ROOT` instead of needing blob
  credentials or a shared trainer-root mount. The trainer cycle now also
  reconstructs its local compile ledger from Azure `processed/<queue>/...` blobs before candidate
  materialization, so the DSPy training input can be rebuilt after trainer PVC loss instead of
  depending on one surviving `training-candidates.yaml` snapshot. The generated training merge now
  also strips legacy worker-only `expected_sources` and collapses duplicate questions at the final
  compile-input stage, so one evolving worker prompt cannot keep re-invalidating trainer
  recompilation through stale prompt-artifact paths or answer-variant duplicate rows; unchanged
  recovered ledgers no longer count as new trainer work, and stale `failed/...` queue blobs are
  skipped instead of poisoning the next poll cycle.
- The trainer now also has a first-stage context-aware champion model instead of only
  question-level replacement. Imported traces are persisted immutably in the trace ledger, then
  grouped in `artifacts/trainer/champion-index.json` by prompt family plus soft retrieval-context
  similarity. The compile-facing `training-candidates.yaml` still materializes only one family
  champion per prompt family because the current DSPy compile contract is still
  `question -> expected_answer`; this stage removes `last write wins` churn without pretending the
  compile dataset can already hold conflicting answers for the same visible question safely.
  Repeated same-answer traces now increase explicit support for the current context-group champion,
  and gradual retrieval-source drift can stay inside one context group instead of splitting into a
  fresh group on every small source shuffle. Runtime traces now also carry snippet-level
  `evidence_fingerprints`, with `trace-export` backfilling them from stored context rows when
  needed, so trainer grouping can distinguish same-source runs that actually saw different
  retrieved snippets. Family-champion selection is now also support-aware across context groups, so
  a new low-support group with only a slight score advantage does not immediately replace the
  compile-facing champion. Trainer-cycle and trainer-service now also accept a
  `min_new_candidates_for_recompile` threshold so live deployments can batch several champion
  updates before recompiling and publishing the next bundle, and the `dataset`
  `deploy_repo_rag_trainer.sh` helper now wires that threshold through the generated AKS
  Deployment/CronJob manifests via `TRAINER_MIN_NEW_CANDIDATES_FOR_RECOMPILE`. A later live fix
  also stops those `stable`-configured trainer cycles from failing purely because an old local
  bundle manifest still misses the bundle gate when the current cycle did not actually produce a
  new bundle candidate.
- The worker-side `codex` path now attempts that mediation proxy for any repository-like prepared
  clone by default, so repo-aware augmentation no longer depends on replacing `codex` with an
  explicit `repo_rag_cli` backend. The local compatibility executor still keeps explicit
  `repo_rag_cli` auto-detection because it does not run the full worker-side Codex path.
- Remaining AKS follow-up work is now specifically trainer-side:
  - feed the live service a genuinely new accepted/candidate trace that survives dedupe so
    auto-recompile can be observed end-to-end
  - pivot the worker hot path from fresh `codex exec` starts to PVC-backed `codex exec resume`
    sessions so repo-RAG is no longer asked to emulate Codex execution memory through stateless
    prompt injection alone; the dedicated plan for that shift now lives in
    [docs/planning/codex-exec-resume-plan.md](codex-exec-resume-plan.md)
  - the first local implementation slice for that pivot now exists in `../dataset`: worker temp
    `CODEX_HOME` instances can restore persisted non-credential Codex state, regenerate fresh
    credential/config files, rerun guard preflight, and prefer an explicit persisted
    `latest_session_id` when a persisted session snapshot is available, only falling back to
    `codex exec resume --last --all` when older snapshots do not record a usable id; the same
    slice now also writes a PVC-root
    `session-index.json` plus per-run `codex_session_state.json` metadata so later AKS validation
    can confirm which lane resumed and which latest session hint survived pod turnover, and it now
    skips restore automatically when the persisted working-directory, repo-root / branch,
    model-profile, or auth/config contract no longer matches the current worker run; the generated
    worker manifest now pins
    `DATASET_CODEX_SESSION_STATE_DIR=/app/artifacts/_codex_sessions` so that state lives on the
    actual artifacts PVC mount by explicit contract instead of by path coincidence. A second local slice now
    narrows that persisted state to a current minimal durable allowlist, records repo/model lane
    metadata, and distinguishes `fresh`, `reset`, `resumed`, and `resumed-then-reset` worker
    outcomes in `codex_session_state.json`, while validating restored snapshots against an explicit
    manifest before attempting resume; the same worker slice now also exposes explicit reset
    controls (`DATASET_CODEX_SESSION_RESET` / `DATASET_CODEX_FORCE_FRESH`) and a
    repeated-resume-failure threshold (`DATASET_CODEX_MAX_RESUME_FAILURES`) plus a tunable
    same-lane repo drift reset threshold (`DATASET_CODEX_REPO_DRIFT_RESET_THRESHOLD`) so a bad
    or overly drifted session lane can rebuild itself without manual PVC surgery, and it now
    reports `restore_status`, `persist_status`, and `pvc_sync_health` so AKS validation can tell
    whether a lane truly resumed, reset cleanly, or degraded while writing session state back to
    the artifacts PVC; the local worker suite now also covers a true two-run `fresh -> resumed`
    cycle instead of only synthetic seeded-restore fixtures. A further local slice now adds one
    explicit divergent-lane trigger through `DATASET_CODEX_SESSION_LANE` or prompt fields
    `codex_session_lane` / `session_lane`, so a new task-family lane can restore from the base
    repository lane, continue as `forked`, and persist its own durable snapshot plus fork
    provenance in `codex_session_state.json`. The same artifact surface now records
    `usage_metrics`, `usage_delta_vs_previous`, and `usage_delta_vs_last_fresh`, so later live AKS
    validation can compare paid token usage between fresh, resumed, and forked lanes without
    diffing raw worker logs by hand. The same lane state now also persists transcript-level
    path/read summaries plus deltas versus the previous run and the last fresh baseline, so later
    validation can compare repeated file-reading behavior without hand-grepping `codex_response`
    artifacts. The latest worker slice also copies `codex_session_mode` and `codex_session_state`
    into repo-RAG trace/outcome payloads, keeping downstream DSPy training compatible with resumed
    and forked Codex lanes instead of hiding that provenance in a worker-only side artifact. The
    same session metadata now tracks lane run counters and rollover timestamps, and the worker can
    force `reset` when one lane exceeds configured age, resumed-run, or prompt-token growth
    thresholds; the AKS worker manifest now also passes those session-policy env vars through to
    live pods. The newest local slice also adds
    `DATASET_CODEX_AUTO_SESSION_LANE_MODE`, so workers can derive task-family lanes automatically
    from `queue_label` and/or `prompt_slug` when no explicit lane hint is present; persisted lane
    metadata now records `lane_source`, making it possible to distinguish explicit operator/prompt
    forks from automatic prompt-family routing in later AKS validation. The current local
    restore-debug follow-up now also consults `session-index.json` plus persisted
    `*/session_state.json` files as restore fallbacks instead of relying only on the direct
    current `lane_dir`, and it writes a `restore_probe` block into `codex_session_state.json` so
    the next live run can reveal whether startup actually saw the PVC root, the direct lane
    directory, the session index, or only a filesystem-discovered fallback before deciding to
    resume or reset. That same local hardening pass now also normalizes repo-rag localhost proxy
    origins to the stable sentinel `repo-rag-proxy://local` before deriving session config
    digests or comparing persisted `model_profile.base_url_origin`, so a normal ephemeral proxy
    port change no longer forces `config-payload-mismatch` / `model-profile-mismatch` resets. The
    newest diagnostic follow-up now also persists durable root and parent continuity markers plus
    a dedicated `codex_restore_probe.json` artifact, so the next live run can distinguish
    “startup never saw `_codex_sessions`” from “startup saw the snapshot but still rejected it”;
    the same follow-up also keeps guard preflight out of the session lifecycle itself so
    `codex --version` checks cannot overwrite a lane before the real worker exec starts. The current local
    bundle-resolution follow-up also closes one worker-side contract gap: `repo-rag` now treats
    both `artifacts/dspy/...` and staged mirror `channels/...` + `versions/...` layouts as valid
    local bundle stores, and the `dataset` deploy path now refreshes `repo-rag-storage-config`
    from the active Azure Storage environment so the worker can reach the shared bundle/trace bus
    directly when Blob credentials are available. The subsequent live trainer redeploy on image
    `20260503-160343` also confirms that stable-configured no-op trainer cycles now finish with
    `command_status=success`, `publish_requested=false`, and `promotion_status=not-requested`
    instead of false-failing on an old local bundle gate. The latest worker-artifact analysis then
    isolated the resume blocker to a path mismatch: prompt-scoped execution artifacts intentionally
    live under `/tmp/artifacts`, but the durable session snapshot root must target the actual PVC
    mount at `/app/artifacts/_codex_sessions`. That fix is now live in the worker image; the first
    run on the corrected root still started `fresh` and seeded the durable snapshot, so the next
    same-lane run is the one that should prove `resumed`. The newest local hardening slice now
    also fixes two orchestration details around the shared artifacts PVC: worker restore reads
    `latest_session_id` back out of persisted lane metadata before deciding how to resume, and
    `tools/pvc_artifact_sync.sh` now auto-cleans helper pods on script exit while explicit
    `cleanup` also deletes by `app=artifacts-sync,claim=<claim>` label so older `artifacts-sync-run`
    pods created without `--guild-id` no longer linger indefinitely
  - confirm whether the new default `TRAINER_PROMOTE_CHANNEL=stable` should remain enabled in live
    AKS or be overridden explicitly for manual-only promotion
  - validate that later worker runs can resolve and consume a trainer-published bundle via `DSPY_BUNDLE_VERSION`

## Phase 4. Global Training Loop

- [x] Stage worker traces into a trainer-side queue so the worker hot path no longer depends on synchronous trainer-side import.
- [x] Add a single-pass trainer cycle that can drain the queue and apply bundle gates in a cron/Kubernetes-job-friendly way.
- [x] Stand up an asynchronous trainer/publisher service outside the worker hot path.
- [x] Ingest worker traces, accepted edits, failures, retrieval misses, and benchmark outcomes into that service in the live AKS deployment.
- [ ] Recompile and validate new bundles without forcing the originating pipeline run to wait in the live AKS deployment.
- [x] Publish only versions that clear the selected benchmark and safety gates in the live AKS deployment.

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

- [x] A `dataset` worker can build a repo-local overlay, answer through `repo-rag`, and upload traces.
- [ ] A `dataset` worker can resolve and pull one explicit `DSPY_BUNDLE_VERSION` bundle from the global bundle store during live AKS runs.
- [x] The main pipeline run never blocks on global retraining.
- [x] New bundles are published asynchronously into the shared global bundle store.
- [ ] Those shared bundles are demonstrably consumed by later live AKS worker runs.
- [x] The integration path is documented well enough to move from local runs to Kubernetes worker pools.
