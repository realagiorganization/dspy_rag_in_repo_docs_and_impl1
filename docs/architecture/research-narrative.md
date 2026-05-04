# Repository Research Narrative

This file is the overreaching narrative for the repository. It is meant to answer one question
that the other docs answer only in pieces: what research program is this repository actually
running, how do its parts connect, and what evidence currently supports that story?

Read this file as the top-level map. Then drop into the more specific docs:

- [README.md](../../README.md) for operator-facing entrypoints and repo layout.
- [docs/architecture/dspy-rag-guide.md](dspy-rag-guide.md) for the DSPy-specific implementation and training path.
- [docs/operations/environment.md](../operations/environment.md) for environment and secret surfaces.
- [docs/planning/repo-hardening-plan.md](../planning/repo-hardening-plan.md) and
  [docs/planning/dataset-integration-plan.md](../planning/dataset-integration-plan.md) for the
  current execution plans that turn the research lab into a reusable runtime plus `dataset`
  integration target.
- [publication/README.md](../../publication/README.md) and
  [publication/repository-rag-lab-article.pdf](../../publication/repository-rag-lab-article.pdf) for
  the publication-style walkthrough.
- [docs/audit/README.md](../audit/README.md) and the newest dated audit note for current
  verification evidence.

## Thesis

The repository treats a software project itself as a research object: a codebase is both the
corpus and the laboratory. The same checked-in sources support:

1. baseline repository-grounded retrieval,
2. DSPy runtime answering and compiled-program development,
3. notebook-based experiment playbooks,
4. operational verification and CI evidence,
5. publication-style reporting, and
6. downstream deployment handoff metadata.

The core claim is not just that repository RAG can be demonstrated. The stronger claim is that the
entire workflow can be made self-describing and reproducible when notebooks, CLI surfaces, tests,
audit notes, CI logs, and publication outputs all point at the same package helpers under
[`src/repo_rag_lab/`](../../src/repo_rag_lab).

## Research Questions

The repository is currently organized around these questions:

- How well can a repository answer questions about itself using only checked-in text and a simple
  retriever?
- How far can DSPy push that baseline when the repository also provides structured training
  examples, retrieval benchmarks, and compiled-program persistence?
- Can notebook experimentation stay honest if the real logic lives in tested Python modules instead
  of ad hoc notebook cells?
- Can verification evidence become part of the research record rather than a side channel?
- Can publication and deployment-handoff artifacts be generated from the same workflow surfaces
  instead of from parallel undocumented scripts?

## Narrative Arc

### 1. The Repository Becomes A Corpus

The first move is to treat the repository as a bounded knowledge source rather than an external
dataset. That story starts in:

- [src/repo_rag_lab/corpus.py](../../src/repo_rag_lab/corpus.py)
- [src/repo_rag_lab/retrieval.py](../../src/repo_rag_lab/retrieval.py)
- [src/repo_rag_lab/workflow.py](../../src/repo_rag_lab/workflow.py)
- [notebooks/01_repo_rag_research.ipynb](../../notebooks/01_repo_rag_research.ipynb)

The repo loads its own text-like files, chunks them into paragraph-aware slices with fixed-width
fallback, ranks them with profile-aware adjustments plus source diversity, and synthesizes a
baseline answer. The retriever now applies light lexical normalization, optional `idf-rerank`
second-stage scoring, and an Azure OpenAI embedding-backed `vector` / `hybrid-vector` path that
stores a local semantic chunk index under `artifacts/retrieval/semantic-index.json`; it still
keeps repository-root-relative source normalization plus repo-local profile overrides from
`config/retrieval-profile.json` so primary docs beat synthetic echoes from tests, training
samples, audits, generated inventories, runtime-generated `prompt_artifacts/`,
worker-scaffold `_context_repos/`, and similar meta surfaces, and it falls back to lexical
ranking with explicit warnings when the embedding runtime is unavailable.
This is the minimum honest system: before
optimization, before benchmarking, and before deployment, the repo must be able to explain itself
from its own contents instead of from its own scaffolding.

### 2. The Corpus Is Curated, Not Just Scraped

The second move is to acknowledge that not every file should count equally. Corpus planning is a
research activity in its own right, not an implementation detail. That story lives in:

- [samples/population/repository_population_candidates.yaml](../../samples/population/repository_population_candidates.yaml)
- [src/repo_rag_lab/population_samples.py](../../src/repo_rag_lab/population_samples.py)
- [notebooks/04_sample_population_lab.ipynb](../../notebooks/04_sample_population_lab.ipynb)

This stage turns the repository from a flat directory tree into a prioritized knowledge plan. The
repo can extend that plan automatically and rerank it from benchmark evidence, which is the first
step from static documentation toward adaptive system behavior.

### 3. MCP Discovery Broadens The Story

The repository does not only answer content questions. It also inspects its own MCP-adjacent
surfaces, so the research narrative includes operational structure as part of the corpus:

- [src/repo_rag_lab/mcp.py](../../src/repo_rag_lab/mcp.py)
- [docs/architecture/mcp-discovery.md](mcp-discovery.md)
- [notebooks/01_repo_rag_research.ipynb](../../notebooks/01_repo_rag_research.ipynb)

That matters because the repo is not just modeling prose. It is modeling tooling shape,
integration affordances, and the agent-facing contract of the project.

### 4. Training Examples Turn Narrative Into Measurable Work

The next stage formalizes what “good answers” should look like:

- [samples/training/repository_training_examples.yaml](../../samples/training/repository_training_examples.yaml)
- [src/repo_rag_lab/training_samples.py](../../src/repo_rag_lab/training_samples.py)
- [src/repo_rag_lab/benchmarks.py](../../src/repo_rag_lab/benchmarks.py)
- [notebooks/03_dspy_training_lab.ipynb](../../notebooks/03_dspy_training_lab.ipynb)

Training examples and expected sources convert repository self-description into a measurable
benchmark surface. This is the point where the project stops being a demo and becomes a research
instrument. The benchmark layer is now also a user-facing evaluation surface through
`make retrieval-eval`, which reports top-k sweeps, richer retrieval-quality metrics, and now fails
when minimum pass-rate or source-recall thresholds regress instead of leaving benchmark inspection
buried in notebook helpers. The benchmark corpus is also narrower than the live full corpus on
purpose: it now excludes repo-meta overlays such as `docs/architecture/research-narrative.md`, `FILES.md`, `docs/operations/environment.md`,
`TODO.MD`, `todo-backlog.yaml`, `AGENTS.md.d/`, and generated exploratorium manifests so the
quality signal stays anchored to the primary sources the retriever is supposed to surface.

### 5. DSPy Moves The Repo From Prompted Runtime To Compiled Program

The repo now has two DSPy layers:

- a runtime answer path through [src/repo_rag_lab/dspy_workflow.py](../../src/repo_rag_lab/dspy_workflow.py)
- a compile-save-reload path through [src/repo_rag_lab/dspy_training.py](../../src/repo_rag_lab/dspy_training.py)

These are exposed through:

- [src/repo_rag_lab/cli.py](../../src/repo_rag_lab/cli.py)
- [rust-cli/](../../rust-cli/)
- [Makefile](../../Makefile)
- [docs/architecture/dspy-rag-guide.md](dspy-rag-guide.md)

This is the current center of gravity of the repository. The project no longer stops at “use DSPy
at runtime if available.” It can now compile a repository-grounded program, persist it under
`artifacts/dspy/`, inspect saved runs as a first-class surface, and reuse the latest compiled
program automatically for later questions.

Before that DSPy layer runs, the Rust wrapper now exposes a repo-local SQLite FTS index and lookup
path over tracked UTF-8 files. The default `ask` flow now narrows retrieval through those native
lookup hits first and only falls back to the full corpus when the local hit set is weak. Agents are
still expected to escalate to DSPy only when they need synthesis across hits instead of direct file
evidence.

### 6. Notebooks Become Playbooks, Not Logic Dumps

The notebooks are part of the research narrative because they show how humans are expected to
interrogate the system. But they are intentionally thin:

- [src/repo_rag_lab/notebook_support.py](../../src/repo_rag_lab/notebook_support.py)
- [src/repo_rag_lab/notebook_scaffolding.py](../../src/repo_rag_lab/notebook_scaffolding.py)
- [src/repo_rag_lab/notebook_runner.py](../../src/repo_rag_lab/notebook_runner.py)
- [notebooks/](../../notebooks/)

Their role is to expose the experiment flow, not to hide untested logic in cells. The monitored
notebook runner and notebook logs under `artifacts/notebook_runs/` and
`artifacts/notebook_logs/` make notebook execution itself part of the observable research record.

### 7. Verification Evidence Is Part Of The Research Output

The repository treats verification as first-class evidence, not just build hygiene. That story is
captured in:

- [docs/audit/](../audit/)
- [samples/logs/](../../samples/logs/)
- [src/repo_rag_lab/verification.py](../../src/repo_rag_lab/verification.py)
- [tests/](../../tests/)

Audit notes capture local verification runs. GitHub Actions logs capture post-push CI status. The
combination creates a chain of evidence from local claims to remote execution.

### 8. Publication And Deployment Are Explicit Downstream Consumers

The repository does not blur experimentation with deployment. Instead it keeps the handoffs
explicit:

- [publication/](../../publication/)
- [src/repo_rag_lab/azure.py](../../src/repo_rag_lab/azure.py)
- [docs/operations/azure-deployment.md](../operations/azure-deployment.md)
- [docs/operations/trainer-deployment.md](../operations/trainer-deployment.md)

The publication surface turns the technical work into a readable article. The Azure manifest and
tuning metadata surfaces turn experimental outputs into deployment-oriented metadata without
pretending that deployment itself happens inside this repo.

The publication bundle now also includes a bilingual exploratorium subdocument that inventories the
state of referenced papers and documentation, summarizes all tracked files, and summarizes every
authored explicit URL in English and Russian. That turns repository self-inventory into a
publication surface rather than leaving it as hidden maintenance glue.

The newest worker-cost investigations also sharpen one deployment boundary that the repository had
previously blurred: stateless repo-RAG mediation is not the same thing as Codex execution memory.
The current pipeline still starts fresh `codex exec` sessions, so repo-grounded snippets improve
the first request but do not stop Codex from re-reading broad repository context later in the run.
That evidence now motivates a separate execution-memory track based on persistent
`codex exec resume` sessions backed by PVC-cached Codex state, recorded in
[docs/planning/codex-exec-resume-plan.md](../planning/codex-exec-resume-plan.md). In that design,
the global DSPy bundle stays immutable and universal, while Codex session continuity becomes a
local worker concern. The first dataset-side implementation slice now exists: worker temp
`CODEX_HOME` instances restore persisted non-credential Codex state, regenerate fresh
`auth.json` / `config.toml`, rerun guard preflight, and can switch to `codex exec resume` when
restored state is present, preferring a persisted explicit `latest_session_id` and only falling
back to `--last --all` when the snapshot lacks a usable id. That slice also writes a PVC-root
`session-index.json` plus a per-run `codex_session_state.json`, so later validation can tell
which lane resumed and which latest Codex session-file hint was preserved. The same slice now
refuses to resume when the
persisted working-directory, repo-root / branch, model-profile, or auth/config digest contract no
longer matches the current worker, and the AKS worker manifest now pins
`DATASET_CODEX_SESSION_STATE_DIR` explicitly to `/app/artifacts/_codex_sessions` on the artifacts
PVC while leaving prompt-scoped execution artifacts under `/tmp/artifacts`. A second local slice now narrows the persisted Codex state to a current minimal durable
allowlist, records repo/model lane metadata, distinguishes `fresh`, `reset`, `resumed`, and
`resumed-then-reset` worker outcomes, validates restored snapshots against an explicit snapshot
manifest before attempting resume, and adds explicit reset controls plus repeated-resume-failure
cooldown through `DATASET_CODEX_SESSION_RESET` / `DATASET_CODEX_FORCE_FRESH`,
`DATASET_CODEX_MAX_RESUME_FAILURES`, and a tunable same-lane repo drift reset threshold via
`DATASET_CODEX_REPO_DRIFT_RESET_THRESHOLD`. The same worker artifact surface now also reports
`restore_status`, `persist_status`, and `pvc_sync_health`, so later AKS validation can tell the
difference between a true restored lane, a reset caused by compatibility guards, and a degraded
PVC snapshot write. Local worker coverage now also proves the basic `fresh -> resumed` lane
transition rather than only seeded restore fixtures. A further local slice now supports divergent
task-family forks: operators or prompts can supply `DATASET_CODEX_SESSION_LANE`,
`codex_session_lane`, or `session_lane`, and when that lane is new but the base repository lane
already has a durable snapshot the worker restores from the base lane, resumes Codex, and records
`forked`, `lane_hint`, `fork_origin_lane_key`, and `forked_from_base` in
`codex_session_state.json`. The same worker artifact now also persists `usage_metrics`,
`usage_delta_vs_previous`, and `usage_delta_vs_last_fresh`, so later AKS validation can measure
whether resumed or forked lanes are actually reducing prompt-token spend rather than only proving
that the restore path ran. The same lane metadata now also persists transcript-level path/read
summaries plus deltas versus the prior run and the lane's last fresh baseline, so live AKS
validation can quantify whether repeated file-reading behavior dropped without manually grepping
`codex_response.txt`. The latest slice also threads `codex_session_mode` plus the session state
summary into repo-RAG trace/outcome payloads, so downstream DSPy training and queued-trace
analysis can correlate candidates with `fresh`, `resumed`, or `forked` Codex execution lanes. The
same lane metadata now also tracks run counts and rollover timestamps, and the worker can force
`reset` instead of another resume when one lane exceeds configured age, resumed-run, or
prompt-token growth thresholds. Those session-policy env knobs are now also wired through the AKS
worker manifest so live pods can enforce the same rollover policy as the local worker tests. The
latest local slice also adds `DATASET_CODEX_AUTO_SESSION_LANE_MODE`, which can derive task-family
lanes automatically from `queue_label` and/or `prompt_slug` when no explicit lane hint is set, so
unrelated queue families stop sharing one increasingly broad Codex lane. Persisted lane metadata
now records `lane_source`, allowing later live validation to distinguish explicit operator forks
from automatic task-family routing. The newest restore-debug slice now also treats
`session-index.json` and persisted `*/session_state.json` files as explicit restore fallbacks
instead of relying only on the direct current `lane_dir`, and it writes a `restore_probe` block
into `codex_session_state.json` so the next live AKS run can report whether startup actually saw
the PVC root, the direct lane directory, the session index, or only a filesystem-discovered lane
match before deciding between `fresh`, `reset`, `resumed`, or `forked`. The same local hardening
pass now also normalizes repo-rag localhost proxy origins to the stable sentinel
`repo-rag-proxy://local` before deriving the session config digest or comparing persisted
`model_profile.base_url_origin`, so a normal ephemeral proxy-port change does not force
`config-payload-mismatch` or `model-profile-mismatch` resets on an otherwise reusable lane. The newest
bundle-resolution follow-up also tightens the DSPy
handoff path itself: `repo-rag` local bundle lookup now understands both the repo-local
`artifacts/dspy/...` layout and the staged worker mirror layout `channels/...` + `versions/...`,
while the `dataset` deploy path now refreshes `repo-rag-storage-config` from the active Azure
Storage environment so workers can resolve `stable` either from a staged PVC mirror or directly
from the shared Blob store when credentials are available.

## Current State

At the time of this document:

- baseline repository-grounded RAG is implemented and exposed through `make ask`, which now
  performs Rust SQLite lookup-first narrowing before falling back to broader retrieval
- live Azure-backed repository answering is implemented and exposed through `make ask-live`
- the baseline ask path, DSPy ask path, and live ask path now also expose an explicit
  machine-readable `--output json` contract for worker-side consumption
- Azure runtime contract probes are implemented and exposed through
  `make azure-openai-probe` and `make azure-inference-probe`
- env-gated live Azure integration coverage now exists in CI for the Azure OpenAI probe, live ask,
  and LM-configured DSPy runtime path when the repository secrets and variables are present
- bounded local Azure OpenAI validation is now also confirmed against a real `gpt-5.4`
  deployment: `make azure-openai-probe` succeeds, `make ask-live` returns a live repository answer,
  `tests/test_live_azure_integration.py` passes when the Azure runtime contract is present, and
  `make trainer-recompile` now produces a real live-compiled bundle under `artifacts/dspy/`
- the same live Azure validation now also proves the trainer-side bundle gate works as intended:
  `make trainer-cycle` can run a real live recompilation and still block publish/promotion when the
  resulting bundle benchmark pass rate does not meet the configured threshold
- tracked-file inventory sync is implemented and exposed through `make files-sync`
- retrieval-quality evaluation is implemented and exposed through `make retrieval-eval`
- utility JSON surfaces now emit a normalized command envelope with `command`, `command_status`,
  `warnings`, and `artifact_metadata` instead of making downstream callers infer command identity
  or artifact paths out of free-form output
- retrieval regressions now fail `make quality`, the pre-push hook, and CI through the same
  threshold-aware `make retrieval-eval` gate
- full-corpus retrieval now has explicit regression coverage against test/training/audit/meta-file
  leakage for the tracked repository questions
- local SQLite lookup over tracked files is implemented and exposed through `make rust-lookup-index`
  plus `make rust-lookup`, and the same native narrowing path now works against arbitrary git
  repository roots when worker-style `--root` execution is used
- the broader retrieval layer now also supports a profile-selected `idf-rerank` mode and keeps
  corpus source paths relative to whichever repository root is selected, including nested fixture
  repos and worker-local temporary clones
- the downstream `../dataset` integration now has two distinct repo-RAG entry modes:
  the local `PromptExecutor` still offers an explicit `repo_rag_cli` / `dspy` backend family for
  compatibility, while the container worker path keeps `codex` as the primary executor and routes
  its Azure Responses traffic through a local `repo-rag serve-codex-proxy` mediation layer
  instead of replacing Codex with a second backend; that mediation path now classifies trivial vs
  deep tasks, enforces a bounded developer-block token budget, caches prior mediation results on
  disk, and suppresses low-signal injections instead of always inflating the Codex prompt
- the explicit downstream `repo_rag_cli` / `dspy` worker path now auto-initializes a local overlay
  through `repo-rag overlay-init` when no explicit overlay is supplied, exports a normalized worker
  trace through `repo-rag trace-export`, persists worker outcome manifests, and can stage those
  records into a trainer-side queue through `repo-rag trace-enqueue`, with Azure Blob + Queue now
  acting as the primary global transport instead of a namespace-local PVC
- that Codex mediation proxy now tries `RAG + DSPy` together first, degrades only the failed layer
  to heuristics when DSPy or retrieval is weak, and finally falls back to direct pass-through so
  an untrained bundle cannot block task execution
- the explicit downstream `repo_rag_cli` / `dspy` runtime path now treats one explicit immutable
  bundle version as the primary runtime selector: workers can pin `DSPY_BUNDLE_VERSION` to one
  published timestamped bundle such as `20260501T135609Z`, fetch that exact program through
  `repo-rag bundle-fetch`, and only fall back to `bundle-inspect --channel stable` when no
  explicit version pin is configured; exported traces still stage through `repo-rag trace-enqueue`,
  and those records can include accepted/candidate outcome metadata, giving the global trainer a
  cross-namespace source of DSPy recompilation inputs
- the worker-side codex path now tries that mediation proxy for any repository-like prepared clone
  by default, so repo-aware augmentation no longer depends on switching execution methods away from
  `codex`; explicit `repo_rag_cli` remains available when a caller wants repo-RAG answers without
  Codex edits, and the current Codex proxy path now reports mediation status plus bundle
  provenance, exports normalized repo-rag traces, and hands them off with outcome metadata through
  the same queue/import trainer surfaces used by the explicit repo-rag runtime path; that same
  path now also derives and forwards non-secret `AZURE_OPENAI_*` runtime settings for the local
  `repo-rag serve-codex-proxy` subprocess so Azure-auth workers no longer depend on the proxy
  rediscovering those values from a repository-local `.env`, and the downstream worker/runtime
  defaults now also pin Azure Responses-compatible API-version fallbacks at
  `2025-03-01-preview` or later instead of backfilling stale `2023-12-01-preview` values when
  `CODEX_AZURE_CONFIG` omits an explicit `query_params.api-version`; the newest AKS evidence now
  shows that this proxy/export path is live in production-like runs; the downstream remediation
  now moves Azure Blob + Queue trace handoff out of the worker boundary and into the trusted
  post-processing stage after `execution_artifacts` rehydration, so worker pods can stay free of
  trainer storage secrets while the deploy runner still emits `repo_rag_trace_enqueue.json` and
  queued Blob/Queue items, and the separately deployed live trainer service now consumes that same
  Azure queue/blob backend through its own secret boundary instead of a filesystem fallback
- DSPy runtime answering is implemented and exposed through `make ask-dspy` after the same
  lookup-first narrowing pass
- DSPy compile-save-reload is implemented and exposed through `make dspy-train`
- DSPy artifact inspection is implemented and exposed through `make dspy-artifacts`
- versioned DSPy bundle manifests are now implemented and exposed through `make bundle-inspect`
- worker-local overlay manifests are now implemented and exposed through `make overlay-init`
- ask-family JSON outputs now carry a stable runtime trace schema so a later asynchronous trainer
  loop can persist retrieval evidence without reverse-engineering free-form output
- trace export and trace import are now implemented and exposed through `make trace-export` and
  `make trace-import`, so local workers and a future global trainer can exchange normalized trace
  records plus optional worker outcome metadata instead of raw command logs
- queued trainer-side trace handoff is now implemented and exposed through `make trace-enqueue`
  and `make trace-drain`, so worker hot paths can stage optimization data without waiting for
  synchronous trainer-side import
- a single-pass background trainer entrypoint is now implemented and exposed through
  `make trainer-cycle`, so queue drain, retrieval gating, and optional bundle promotion can run as
  a cron/Kubernetes job before a longer-lived trainer service exists
- a long-lived background trainer loop is now implemented and exposed through
  `make trainer-service`, so the same queue drain, gating, publish, and promotion workflow can
  run continuously while recording trainer-side state/history artifacts under `artifacts/trainer/`;
  the current live AKS trainer deployment now drains the Azure queue, uses
  `TRAINER_RECOMPILE_RUN_NAME=trainer-auto` as a run-family label, mints a unique timestamped
  bundle version such as `20260501T135609Z` for each successful recompile, records imported trace
  paths plus candidate dedupe counters in bundle lineage metadata, and can remote-publish those
  immutable bundle versions into `repo-rag-bundles`; worker deployments can now pin one of those
  versions globally through `DSPY_BUNDLE_VERSION`, while optional `stable` / `canary` promotion
  and rollback remain available as alias/fallback mechanics instead of the primary runtime
  selection path; repository-local deployment defaults now promote `stable` unless an operator
  explicitly clears `TRAINER_PROMOTE_CHANNEL` for manual-only promotion; the trainer cycle now also
  restores a durable local trace ledger from Azure `processed/<queue>/...` blobs before
  materializing candidates, so losing the trainer PVC no longer implies losing the accumulated
  example set used to build the next DSPy program
- trainer-side queue drain is now also summarized into first-pass ingestion counters for accepted
  vs. rejected outcomes, execution status, retrieval mode, bundle version, and empty
  source/context cases, so imported traces are no longer only stored but also surfaced as
  operational signals
- imported traces can now also be materialized into cumulative YAML candidate examples under
  `artifacts/trainer/training-candidates.yaml`, which gives the future global trainer a concrete
  bridge from worker traces to DSPy review/compile inputs
- that trainer materialization path now also persists a separate
  `artifacts/trainer/champion-index.json` state surface, where imported traces are grouped first
  by prompt family (normalized question) and then by soft retrieval-context groups instead of
  using question-level `last write wins`; the compile-facing `training-candidates.yaml` file is now
  materialized from one family champion per prompt family, so replaying many worker traces for the
  same evolving prompt no longer necessarily creates recompile churn unless the effective family
  champion actually changes; trainer-cycle and trainer-service summaries now also expose
  `prompt_family_count`, `context_group_count`, and `champion_index_path`, so that grouping
  behavior is visible without reopening the raw JSON state by hand; repeated same-answer traces now
  increase explicit champion support inside one context group, and the group summary now merges
  gradual retrieval-source drift so `README.md -> README.md + docs/USAGE.md -> docs/USAGE.md`
  can remain one training context instead of fragmenting on every small repository change; the
  runtime trace schema now also exports snippet-level `evidence_fingerprints`, and `trace-export`
  backfills them from stored `context` / `retrieved_context` rows for older command envelopes, so
  same-source retrievals that actually used different snippets can still separate into different
  trainer context groups; family-champion selection now also has a stability gate across those
  context groups, so a small score-only edge is not enough to flip the compile-facing champion
  when the incumbent group already has stronger support; trainer-cycle and trainer-service now
  also expose a `min_new_candidates_for_recompile` batching gate so one or two fresh champion
  updates can be accumulated before the next DSPy recompilation instead of forcing a new bundle on
  every single cycle, and the trainer Kubernetes/deploy helpers now thread that threshold through
  generated ConfigMaps plus `trainer-cycle` / `trainer-service` command lines so live AKS
  deployments can honor the same batching policy as the local CLI
- those cumulative candidates can now also be merged back into
  `artifacts/trainer/generated-training.yaml` and compiled into a fresh DSPy run through
  `make trainer-recompile`, so the trainer path now has an explicit bridge from worker traces to
  generated compile inputs instead of stopping at raw candidate accumulation; that merge step now
  also strips legacy worker-only `expected_sources` from trainer-candidate-tagged records and
  enforces one question-level record in the final generated training set, so stale worker prompt
  artifacts and answer-variant duplicates do not reappear as invalid DSPy compile inputs
- the background trainer path now also enforces a trainer-side DSPy benchmark gate before
  publish/promotion, so an automatically recompiled bundle cannot advance purely because the
  retrieval gate passed
- the repository now also materializes Kubernetes Deployment and CronJob manifests for those
  trainer-side roles through `make trainer-k8s-manifests`, so the current deployment story is no
  longer only “you could wrap this in AKS later” but “here is the generated service/CronJob
  surface that uses one shared image family, Azure Blob + Queue for global transport, and a
  trainer-local PVC for cache/state/history”
- that trainer manifest surface still emits a first-class PVC manifest, but it is now a
  trainer-local artifact cache and history store rather than the primary cross-namespace bus
- the repository now also ships its own runtime image definition in the root `Dockerfile`, keeping
  an editable checkout under `/workspace/repo-rag` so `repo-rag` can be preinstalled into worker
  and trainer containers without breaking path-sensitive runtime features such as the Rust lookup
  wrapper
- the downstream `../dataset` deployment story now assumes a real repo-RAG runtime image named
  `repo-rag-runtime`, built from this repository through `../dataset/build_and_push_images.sh`,
  with `prompt-executor` using that runtime image as its base layer instead of treating repo-RAG
  as an optional side checkout
- `../dataset` now also carries explicit submodule metadata for this repository and
  `dataset_website`, so the orchestration repository can show those relationships directly and use
  the repo-RAG submodule as the preferred build context when it is initialized
- the central inference story is now explicit instead of implied: workers and trainer-side live
  recompilation currently target an external Azure/OpenAI inference layer first, while any shared
  internal model-serving tier remains a later cost/compliance optimization rather than a hidden
  prerequisite of the current runtime
- the repository now also exposes a bounded stdio MCP server through `make serve-mcp`, but only
  for short calls such as lightweight baseline ask, bundle status, DSPy artifact listing, and
  queued trace publish; heavy trainer and evaluation workflows intentionally remain on direct CLI
  surfaces
- published bundle records and explicit `stable` / `canary` promotion state are now implemented
  through `make bundle-publish`, `make bundle-promote`, and `make bundle-rollback`, so worker
  startup no longer has to guess “latest run” when a promoted runtime is required
- bundle inspection/fetch/publish/promotion and queued trace handoff now speak a global Azure
  Blob + Queue contract when storage credentials are present, while retaining the older local
  filesystem registry/queue only as a single-repository fallback
- trainer-side change detection now treats the durable processed-trace ledger as the source of
  truth but only publishes a new immutable bundle when the effective materialized candidate set
  changes relative to the existing snapshot; stale `failed/...` queue pointers are skipped as
  queue noise instead of counting as fresh work
- the downstream `../dataset` worker path now also has a safe promoted-bundle distribution
  contract: the deploy-stage runner mirrors `channels/stable.json` plus the referenced immutable
  bundle assets into the artifacts PVC under `.repo_rag_bundle_store/`, worker pods read that
  non-secret local mirror through `DATASET_REPO_RAG_BUNDLE_ROOT`, and placeholder bundle pins
  such as `0` fall back to `stable` without requiring blob credentials inside the worker or Codex
  subprocess; trainer-side no-op cycles now also avoid false-failing on the historical
  bundle-manifest gate when no new bundle candidate exists to publish or promote, and that
  no-op-cycle behavior is now verified live on the `20260503-160343` trainer image through the
  first post-redeploy service-cycle `20260503T161713Z-cycle-0001.json`; the remaining live
  Codex-resume blocker was narrowed to a storage-path mismatch between
  `/tmp/artifacts/_codex_sessions` and the durable `/app/artifacts` PVC mount; the rebuilt worker
  image now reports `persistent_root=/app/artifacts/_codex_sessions` live, so the path fix itself
  is present in AKS, but the first run on that corrected root still started as `fresh` and only
  seeded the durable snapshot. The newest local hardening pass now also reloads
  `latest_session_id` from persisted lane metadata before command assembly and adds a safer
  `--last --all` fallback only when older snapshots do not carry a usable id. The same pass
  finally explains the long-lived `artifacts-sync-run` pods seen beside the artifacts PVC:
  `tools/pvc_artifact_sync.sh` created helper pods with `guild=unknown` whenever callers passed an
  explicit claim but no `--guild-id`, while explicit `cleanup` only deleted one derived pod name.
  The script now auto-cleans helper pods on exit and explicit cleanup also deletes by
  `app=artifacts-sync,claim=<claim>` label, so future PVC helper pods should not linger after
  deploy/workflow sync steps complete. Actual `resumed` proof still depends on the next same-lane
  run
- notebook batch execution and reporting are implemented and exposed through
  `make notebook-report`
- TODO and publication backlog synchronization are implemented and exposed through
  `make todo-sync`
- bilingual file, link, and fetch-state publication sync is implemented and exposed through
  `make exploratorium-sync`
- verification and CI logging are part of the repository contract, not optional cleanup

The main bottlenecks are now quality and coverage of retrieval, training examples, and benchmark
signal, not the lack of a DSPy or notebook execution surface.

## Evidence Surfaces

Use these files when you need to defend the current repository story quickly:

| Question | Best starting point | Supporting surfaces |
| --- | --- | --- |
| What is the repo for? | [README.md](../../README.md) | [publication/repository-rag-lab-article.pdf](../../publication/repository-rag-lab-article.pdf) |
| How is retrieval quality measured? | [docs/architecture/dspy-rag-guide.md](dspy-rag-guide.md) | [src/repo_rag_lab/benchmarks.py](../../src/repo_rag_lab/benchmarks.py), [docs/audit/2026-03-18-zzzzzzzzzzzz-retrieval-regression-gate.md](../audit/2026-03-18-zzzzzzzzzzzz-retrieval-regression-gate.md) |
| How are live Azure runtime calls validated? | [docs/operations/azure-deployment.md](../operations/azure-deployment.md) | [src/repo_rag_lab/azure_runtime.py](../../src/repo_rag_lab/azure_runtime.py), [docs/audit/2026-03-18-azure-runtime-surfaces.md](../audit/2026-03-18-azure-runtime-surfaces.md) |
| How does DSPy work here? | [docs/architecture/dspy-rag-guide.md](dspy-rag-guide.md) | [src/repo_rag_lab/dspy_training.py](../../src/repo_rag_lab/dspy_training.py), [src/repo_rag_lab/dspy_workflow.py](../../src/repo_rag_lab/dspy_workflow.py) |
| How do agents do cheap file lookup before DSPy? | [AGENTS.md](../../AGENTS.md) | [AGENTS.md.d/RUST_LOOKUP.md](../../AGENTS.md.d/RUST_LOOKUP.md), [rust-cli/src/main.rs](../../rust-cli/src/main.rs), [Makefile](../../Makefile) |
| How do notebooks fit in? | [notebooks/](../../notebooks/) | [src/repo_rag_lab/notebook_scaffolding.py](../../src/repo_rag_lab/notebook_scaffolding.py), [src/repo_rag_lab/notebook_runner.py](../../src/repo_rag_lab/notebook_runner.py) |
| How is the repository inventory summarized? | [FILES.md](../../FILES.md) | [FILES.csv](../../FILES.csv), [src/repo_rag_lab/file_summaries.py](../../src/repo_rag_lab/file_summaries.py), [AGENTS.md.d/FILES.md](../../AGENTS.md.d/FILES.md) |
| What currently passes? | [docs/audit/README.md](../audit/README.md) | newest dated note in [docs/audit/](../audit/), plus [samples/logs/](../../samples/logs/) |
| What environment is required? | [docs/operations/environment.md](../operations/environment.md) | [docs/operations/azure-deployment.md](../operations/azure-deployment.md) |
| How does the publication relate? | [publication/README.md](../../publication/README.md) | [publication/repository-rag-lab-article.pdf](../../publication/repository-rag-lab-article.pdf), [publication/exploratorium_translation/exploratorium_translation.pdf](../../publication/exploratorium_translation/exploratorium_translation.pdf) |

## Tensions And Open Work

The narrative is coherent, but not complete. The main open tensions are:

- retrieval is still relatively simple compared with the sophistication of the DSPy training path
- notebook execution is well observed, but notebook conclusions still depend on the quality of the
  underlying corpus and benchmarks
- deployment handoff is documented, but live remote deployment is intentionally outside repo scope
- verification evidence is strong, but the index docs must be kept synchronized so the narrative
  does not drift behind the latest audit and CI state

## Maintenance Contract

This file is supposed to move as the repository moves. Update it whenever a turn materially
changes any of these:

- the central research question or thesis
- the narrative stages of the workflow
- the repo-native surfaces in `README.md` or `Makefile`
- DSPy training/runtime capabilities
- notebook responsibilities or observability
- verification evidence expectations
- publication or deployment-handoff scope

If a turn changes one of those and does not update this file, the repository narrative is drifting.
