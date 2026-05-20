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
- [docs/planning/per-turn-dspy-mediation-contract.md](../planning/per-turn-dspy-mediation-contract.md)
  for the current contract that defines how DSPy is supposed to work inside the `codex exec`
  pipeline.
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
program automatically for later questions. The family-oriented trainer path now also treats
published prompt-family state as a real routing index rather than a duplicated replay snapshot:
term-level routing evidence is stored in unified `*_term_stats` mappings with both `count` and
normalized `weight`, and the post-recompile trainer path now rewrites `family-state.json` through
the same thin-index persistence layer so runtime routing can load compact summaries while the full
records stay in per-family blobs. The active family summary is now intentionally stricter than the
full term statistics: if a family has technical lookup terms, routing uses only that technical
core, keeps the active prompt summary at or below twelve terms, excludes broad narrative and
low-signal terms from the live summary surface, and publishes the final remote `family-state.json`
with explicit `family_count` and `prompt_family_count` metadata instead of leaving those summary
fields null.

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
The verification posture is now also more explicit about what the repository can currently sustain:
the global coverage gate remains enabled, but it is aligned to the observed full-suite baseline at
`80%` rather than an aspirational `85%`, while type-checking, retrieval-eval, smoke checks, and
repository-surface verification continue to act as the sharper regression detectors for ongoing
development.

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
artifacts, queue mirrors, and trainer-family state now move through repo-local durable surfaces on
purpose rather than as best-effort side effects. The trainer path specifically now treats queue
drain as a recoverable stage: once one cycle drains imported traces, it records a
`pending-cycle.json` ledger under `artifacts/trainer/` so a replacement trainer pod can resume the
same family-materialization/publish work even if the visible `queued/` directory has already been
emptied. That closes the failure mode where traces reached `processed/` but no new
`repo-rag-training-families` or `repo-rag-bundles` version was ever published after pod churn.
The next trainer correction tightens family formation itself: imported traces are no longer matched
into existing families as one-way `question -> family` probes. Instead each incoming trace is first
lifted into a temporary singleton family with its own father, prompt-profile terms, and
constraint/profile summaries, and trainer ingestion compares that singleton family against existing
families with a symmetric family-to-family score. This removes the earlier order-dependent defect
where a trace could fail to join a family, create its own singleton family, and then only
*afterward* appear obviously close to that original family once its own family summary existed.
The semantic criterion for those families is now explicit as well: the repository is not trying to
force one entire workflow into one family. A prompt family represents one stable semantic stage or
code block that can recur across many workflows. That means one workflow may legitimately produce
multiple families when it moves through different stages, while two unrelated workflows may
legitimately share one family when they enter the same stage or execute the same logical block.
Recent GIF/recorder inspection runs clarified why this distinction matters: what first looked like
over-splitting at workflow scope became well-formed stage-level clustering once the families were
interpreted as reusable steps such as repo-state validation, semantic artifact validation, rerun
decision, and constrained close-out.
The repository now also stops generating `family-state.json` as the routing index. The generated
index is `family-index.sqlite3`, while `family.json` and `records/*.json` remain the detailed
payload surfaces. Runtime lookup is now split into a coarse shortlist over the SQLite index
followed by rich family scoring only for the shortlisted families. That keeps
`repo-rag-training-families` focused on route selection while `repo-rag-bundles` remains the
surface that actually serves the DSPy runtime artifact for the selected `prompt_family_id`.
`CODEX_HOME` instances restore persisted non-credential Codex state, regenerate fresh
`auth.json` / `config.toml`, rerun guard preflight, and can switch to `codex exec resume` when
restored state is present, preferring a persisted explicit `latest_session_id` and only falling
back to `--last --all` when the snapshot lacks a usable id. That slice also writes a PVC-root
`session-index.json` plus a per-run `codex_session_state.json`, so later validation can tell
when worker execution memory resumed correctly, while the trainer side now treats remote
`repo-rag-training-families` state as authoritative for every queue-triggered baseline decision.
The PVC-backed `artifacts/` mount is only a temporary workspace for queued/imported traces, one
in-flight `pending-cycle.json` ledger, generated training surfaces, and one smart local mirror of
the active remote `family_state_version`. That local cache is allowed only when metadata proves it
already mirrors the same remote version; otherwise the trainer refreshes from remote before
applying the new queued traces. If no remote family-state version exists at all, the trainer may
bootstrap one transient local family state from the current queue cycle, but it must publish that
state remotely before later cycles can treat it as a reusable baseline.
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
PVC snapshot write. The latest local worker-artifact review now also proves one real same-lane
`fresh -> resumed` transition with `resume_command_mode=explicit-session-id`,
`resumed_run_count=1`, and a prompt-token drop from `2568062` on the fresh baseline to `103760`
on the resumed lane, so the dominant execution-memory blocker has moved from session persistence
to MCP-guided discovery quality.

That same worker line now has a second architectural correction: DSPy is no longer modeled as
“optimize the initial user prompt and hope the rest of the autonomous rollout follows”. The active
target contract is the one in
[docs/planning/per-turn-dspy-mediation-contract.md](../planning/per-turn-dspy-mediation-contract.md):
every outbound Codex turn must flow through the same proxy path, the proxy must gate DSPy
mediation on champion prompt-family support, unsupported turns must pass through unchanged but
still become candidate traces, and trainer-side champion replacement is allowed to use only
`hits / total` plus prompt-family semantic similarity thresholds `0.8` and `0.6`. A newly
clarified part of that same contract is that every outbound Codex turn must first be rewritten
from `original_prompt` into `reformulated_prompt`, and the reformulated form becomes the
prompt-family, champion, trace, and final DSPy-program surface rather than remaining hidden.
The same contract now treats the observable per-turn `command_trace` as equally important
lineage: when the sequence is available it must be preserved beside the reformulated prompt in
the trace and champion state, even though not every turn exposes a controllable command path.
The newest local family-first slice makes that contract less abstract: trainer-side family state
now persists replay members directly as `family_records`, dirty-family compilation consumes that
replay set instead of collapsing back to one runtime summary record, and the remote
`repo-rag-training-families` container now mirrors versioned `family.json`, `father.json`, and
`records/<snapshot>.json` blobs per family. That does not finish the migration yet, because the
aggregate family-state index is still carried for compatibility, but it means the storage layout
and compile input now already look like the family-replay contract rather than the older
champion-only contract.
The current trainer/proxy correction sharpens that same contract in three places. First, family
father selection is no longer “most central question wins”; it now follows the product rule that
the father is the stored trace with the best arithmetic mean across known per-trace metrics, which
keeps the routing prototype tied to the trace contract instead of to a derived centroid. Second,
trainer-side queue wrappers now mirror `question`, `original_prompt`, and `reformulated_prompt`
onto their top-level payloads instead of leaving those prompt fields only inside the nested trace
object, so queue drain, processed-ledger recovery, and dataset-side trusted handoff all preserve
the same prompt snapshot surface that runtime traces already carried.
today reduces to metric-1 `hit_rate` plus any later persisted similarity metrics. Second, local
trainer bootstrap now follows the stricter remote-baseline family contract: the active cache may
be reused only when it is already tagged as a mirror of the same remote family-state version,
otherwise trainer refreshes the local mirror from `repo-rag-training-families` before applying the
current `queued` traces, and the only allowed no-remote bootstrap is one transient family state
built from the current cycle itself. Third, proxy
trace persistence is no longer limited to one coarse turn payload: when a turn falls back to fresh
mediation, the proxy now also emits lineage traces for distinct reformulated/intermediate
prompt-like steps so trainer ingestion can observe the same prompt evolution that runtime routing
actually saw.
The same routing layer is now slightly less brittle than the original father-only contract: family
matching no longer compares a new prompt only against `family_father_question`, but against the
family's accumulated prompt profile (`question_variants` plus persisted original/reformulated trace
forms). The newest slice pushes that one step further by persisting lightweight family-profile
summaries derived from the replay set itself:

- `family_prompt_profile_terms`
- `family_command_pattern_summary`
- `family_constraint_summary`

Runtime routing now treats that family profile as the primary routing surface rather than as a
secondary tie-breaker behind prompt-string similarity. The score still keeps prompt similarity as
one precision prior, but the dominant signal is now overlap against:

- `family_prompt_profile_terms`
- `family_command_pattern_summary`
- `family_constraint_summary`

plus the family's feedback-aware success prior and uncertainty penalty. That is still not a true
embedding centroid, but it now aligns better with the product requirement that prompt families
should follow latent task intent carried by salient keywords/constraints rather than superficial
string resemblance alone.
The newest Phase-1 correction keeps two trainer-visible signal classes in the contract, but the
current active runtime policy is intentionally simpler: successful family reuse now emits
`full_trace` directly. `full_trace` remains the replay-set exemplar that can dirty a family and
later drive BootstrapFewShot recompilation. `feedback_trace` stays reserved for future compact
feedback-only paths and historical compatibility, but the live policy no longer hides matched runs
behind feedback-only accounting. That change matters because pure “reuse means no trainer input”
had been freezing the family library: the runtime could succeed repeatedly without teaching the
trainer that the deployed family artifact was actually good. The current slice therefore keeps all
matched runs exportable and replay-visible while still forbidding trainer-side pairwise trace
comparison as the replay gate.
The live AKS inspection after that change exposed two remaining deployment-facing mismatches: the
container worker in `../dataset` still downgraded successful reused family artifacts back to
`feedback_trace`, and the `serve-codex-proxy` CLI still launched with the old `700/280/3`
mediation defaults even though the runtime constants had already moved to `420/180/2`. Those
surfaces are now aligned, so a deployed prompt-executor should preserve matched runs as
`full_trace` and launch the proxy with the compact mediation budget that the repo code expects.
The next live publish then exposed a different failure mode in the trainer itself: the execution
path was finally correct, but incremental thin-family persistence republished five carried-forward
families with empty replay payloads and no `father.json` sidecars, collapsing the published family
history from `11` replay records down to `2`. That regression happened after materialization, not
during routing or compile; the newly published bundle still reported the expected training-example
count. The persistence contract is therefore now stricter: when a carried-forward family reaches
local publish as a thin payload, the trainer must retain any existing replay sidecars and family
anchor records from the previously cached compatible version instead of overwriting them with empty
structures.
That success signal is no longer stored as a raw mean alone. Family state now persists one
`family_success_metric` posterior profile that combines replay-set evidence with compact reuse
feedback and records `posterior_mean`, `lower_bound`, and `uncertainty` for the current family
artifact.
Another immediate correction now closes a trainer-quality leak: proxy mediation no longer trusts a
matched family artifact unconditionally. When the bundle says the family artifact's validated
`hit_rate` is below the family's current conservative success baseline, the proxy now refuses
that family artifact and falls back to fresh/global mediation. In the other direction, worker-side
batch handoff now
rewrites optimistic proxy per-turn draft metrics with the final run `execution_status`,
`acceptance_status`, and real post-run `mediation_metric_hits / mediation_metric_total` before the
turn traces are exported and queued. That matters because otherwise family replay sets would keep
absorbing "proxy call succeeded" as if it were "full Codex run succeeded", which would poison the
training signal. The newest worker/runtime hardening closes a second leak in the same corridor:
the authoritative outer `trace-export`, `trace-enqueue`, and trusted-handoff payloads now preserve
the same family success profile fields that runtime used internally, including
`family_predicted_hit_rate`, `family_predicted_hit_rate_lower_bound`,
`family_prediction_uncertainty`, and `family_feedback_count`, instead of only keeping those values
inside nested runtime trace objects.
The same runtime path now also injects a much smaller developer mediation block into Codex. Instead
of repeating a long reformulated prompt plus multiple evidence snippets, the hot path now keeps one
compact execution line, an optional family id, one short summary, up to two file hints, one
evidence snippet, and at most one note. That preserves the useful grounding function of the proxy
without doubling the execution payload as aggressively as the previous mediation format did.
The next live trainer failure clarified a second boundary in the same corridor: raw proxy
mediation drafts, enriched per-turn execution traces, and the final single execution trace are
three different surfaces. The worker may still export `repo_rag_turn_traces/<batch>/...` to
preserve mediation lineage and batch-level audit history, but trainer queue/import handoff should
prefer the enriched per-turn batch traces whenever they exist. Those traces already carry the final
run outcome and are the surface that preserves "all trace steps from the run" for family
formation. The final single `repo_rag_trace.json` is only a fallback handoff when no usable batch
exists or the batch handoff itself fails. The real bug was narrower: the worker accidentally
disabled batch handoff almost all the time and then trainer only saw one final trace per worker. In
parallel, trainer also needed a defensive rule to reject raw `codex-proxy-turn-mediation` records,
because those remain valid audit artifacts but are never valid training exemplars.
The same contract is now also explicit about where replay admission decisions are allowed to live:
trainer should not perform broad trace-to-trace similarity scans or replay-set deduplication as its
main control loop. Those expensive choices belong on the runtime/Codex Exec side, before trainer
ingestion, so the trainer can stay focused on family assignment, dirty-family updates, and DSPy
compilation rather than on costly pairwise trace rejection.
very metric the family-first contract is supposed to optimize.

A further local slice now supports divergent
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
`config-payload-mismatch` or `model-profile-mismatch` resets on an otherwise reusable lane. The
latest diagnostic follow-up now also writes durable root and parent continuity markers plus a
dedicated `codex_restore_probe.json` artifact, so later live runs can distinguish “worker never
saw `_codex_sessions`” from “worker saw it and still rejected resume”; the same follow-up also
suspends `_active_codex_session_spec` during guard preflight so `codex --version` checks cannot
mutate the PVC-backed session lane before the real worker run begins. The newest
storage/runtime follow-up now also preserves `_codex_sessions`, `.repo_rag_cache`, and
`.repo_rag_bundle_store` during artifacts-PVC reset operations instead of root-wiping the whole
claim, adds retrieval-corpus manifests plus retrieval-profile fingerprints to proxy cache keys so
repo-rag invalidates stale mediation entries when indexed files change, and injects a bounded
local `repo-rag` MCP server into the generated Codex config so discovery/search can prefer MCP
while exact verification still falls back to shell. Worker-side artifacts now also include a
`repo_rag_mcp_usage_summary.json` summary so later live runs can measure whether Codex actually
used `search_repo` before broad shell exploration. The newest MCP follow-up now also treats
Codex-side MCP launch as a first-class failure surface: the worker no longer points Codex at a
bare `repo-rag` token only, but writes a generated MCP launcher script under `execution_artifacts/`,
resolves the first command token to an absolute executable path when possible, raises the Codex MCP
startup/tool timeouts, and persists a dedicated `repo_rag_mcp_stderr.log` tail into the MCP usage
summary. That local hardening follows a direct Codex reproduction where `list_mcp_resources`
returned empty arrays only because the child MCP server never finished startup or was not found on
the subprocess PATH, not because `repo-rag` lacked resource definitions. The newest root-cause pass
then narrowed the remaining regression further: the bounded MCP server itself had become fast, but
the worker still launched it through the heavyweight `repo_rag_lab.cli:main` graph via
`repo-rag serve-mcp`. The repository therefore now exposes one dedicated lightweight stdio module
entrypoint (`python -m repo_rag_lab.mcp_stdio --root ...`) that imports only the bounded MCP
surface. The worker defaults its MCP launcher to that module entrypoint, writes `transport =
"stdio"` explicitly into the generated Codex config, and preflights the launcher with one bounded
`initialize -> resources/list` exchange before handing the config to Codex. If that preflight
fails, the worker omits MCP from the generated config for that run instead of letting a resumed
lane spend multiple turns retrying `resources/list` and then falling back into shell-only
exploration. The newest transport root-cause fix then identified one deeper protocol bug inside
`read_json_rpc_message()`: the old reader mixed `select()` against the raw stdin file descriptor
with `readline()` / `read()` on Python's buffered `sys.stdin.buffer`. After the first
`Content-Length` header line, Python could already hold the remaining blank line and body in its
internal buffer while the underlying pipe fd appeared empty, which produced the live debug pattern
`header-line Content-Length: ...` followed by `waiting-for-headers no-bytes-yet`. The reader now
uses `select()` only before the very first header byte and consumes remaining headers/body directly
from the buffered stream, which restores normal framed `initialize` responses for raw local stdio
clients and removes the false worker-side MCP startup timeout caused by Python buffering rather
than actual server complexity. The newest
bundle-resolution follow-up also tightens the DSPy
handoff path itself: `repo-rag` local bundle lookup now understands both the repo-local
`artifacts/dspy/...` layout and the staged worker mirror layout `channels/...` + `versions/...`,
while the `dataset` deploy path now refreshes `repo-rag-storage-config` from the active Azure
Storage environment so workers can resolve `stable` either from a staged PVC mirror or directly
from the shared Blob store when credentials are available. The newest trainer-side publish
root-cause pass then showed that a distinct new prompt family can still fail before bundle publish
if worker-originated trace records carry raw `codex_response.txt` transcripts as
`expected_answer`. Live cycle `20260506T165814Z-cycle-0171.json` did raise
`new_candidate_count = 1` and `new_prompt_family_count = 1`, but DSPy recompilation failed at
`1126031` prompt tokens because imported `answer` fields still contained `COMMAND: ...`, `STDERR`,
`exec`, `apply patch`, and large `diff --git` blocks instead of concise assistant answers. The
trainer materialization path now normalizes imported worker answers before candidate creation,
extracts the final assistant-facing Codex block when a transcript is detected, clamps imported
trainer answers to a bounded compile budget, and sanitizes persisted `champion-index.json`
champion records on load so already-stored oversized worker-derived answers do not keep poisoning
later `trainer-auto` recompilation attempts. The next MCP transport root-cause pass showed that
the remaining “RAG did not start via MCP” failure was also not a path/config problem: the worker
already generated an explicit stdio launcher and Codex did reach `initialize`. The actual break was
inside `repo_rag_lab.mcp_server.read_json_rpc_message()`, which dropped already-buffered follow-up
frames when `notifications/initialized` and `resources/list` arrived back-to-back on the same
pipe. The server would therefore log `initialize`, then `notifications/initialized`, then wait for
new headers forever even though the `resources/list` frame had already been delivered. The reader
now keeps a persistent per-stream buffer for fd-backed stdio so the bounded MCP discovery surface
can consume consecutive frames without losing the post-initialize discovery request.

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
  acting as the primary global transport instead of a namespace-local PVC; that Azure-backed queue
  handoff now also mirrors the same queued and batch payloads into local
  `artifacts/traces/queued/...` and `artifacts/traces/batches/...` paths so trainer PVCs preserve
  one first-class local audit/debug surface instead of exposing only remote blobs
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
- those trainer-visible per-turn trace records must stay prompt-specific and lightweight: each
  proxy turn still forms its own trace, but those files must not be bloated by duplicating one
  shared full-run `command_trace`, one shared full-run `outcome`, or one nested full execution
  snapshot across many traces in the same run, because that makes distinct prompts look
  artificially similar during family formation
- more generally, generated repo-rag artifacts now follow a one-owner serialization rule:
  one datum should have one canonical owner, and wrapper layers must not mirror the same prompt
  strings, routing metrics, or full records again unless that duplication is required for the
  artifact to stay self-sufficient. In practice this means command envelopes should not repeat the
  prompt surface already owned by nested runtime traces, queue items should not mirror the same
  fields already inside `trace_payload`, `family.json` should not inline records already persisted
  in `father.json` or `records/*.json`, and bundle family registries should stay compact instead of
  embedding full family records they do not need for runtime routing. Historical compatibility is
  not sufficient justification for new duplication: compatibility must be handled at read/translation
  boundaries instead of by mirroring the same data into every newly generated artifact.
- that rule also now applies explicitly to the published SQLite family index: one family gets one
  canonical routing question, not a three-way mirror of `question`, `normalized_question`, and
  `family_father_question` when those values are materially identical, and compact father sidecars
  must still be published whenever the thin index advertises `father_path`
- queued trainer-side trace handoff is now implemented and exposed through `make trace-enqueue`
  and `make trace-drain`, so worker hot paths can stage optimization data without waiting for
  synchronous trainer-side import
- a single-pass background trainer entrypoint is now implemented and exposed through
  `make trainer-cycle`, so queue drain, retrieval gating, and optional bundle promotion can run as
  a cron/Kubernetes job before a longer-lived trainer service exists
- a long-lived background trainer loop is still available through `make trainer-service` for local
  debugging, but the live AKS trainer deployment now prefers a single cron-driven
  `make trainer-cycle` path so the same queue drain, gating, publish, and promotion workflow runs
  once per schedule window instead of racing between two orchestrators while recording
  trainer-side state/history artifacts under `artifacts/trainer/`; the current live AKS trainer
  deployment now drains the Azure queue, uses
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
  by prompt family and then by soft retrieval-context groups instead of using question-level `last
  write wins`; prompt-family assignment is no longer intended to mean “exact normalized question
  only”, because the trainer now treats prompt identity as a delta-aware surface and can keep close
  prompt variants inside one family while still splitting larger prompt deltas into a new family
  path; the compile-facing `training-candidates.yaml` file is now materialized from one family
  champion per prompt family, so replaying many worker traces for the same evolving prompt no
  longer necessarily creates recompile churn unless the effective family champion actually changes;
  trainer-cycle summaries now also expose
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
  when the incumbent group already has stronger support; trainer-cycle now also exposes a
  `min_new_candidates_for_recompile` batching gate so one or two fresh champion
  updates can be accumulated before the next DSPy recompilation instead of forcing a new bundle on
  every single cycle, and the trainer Kubernetes/deploy helpers now thread that threshold through
  generated ConfigMaps plus the cron-driven `trainer-cycle` command line so live AKS deployments
  can honor the same batching policy as the local CLI
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
  as an optional side checkout; the same build path now mirrors the required public Python base
  images into the target Azure Container Registry first, so ACR Tasks no longer depend on
  unauthenticated Docker Hub pulls during cloud builds, and if those mirror imports still hit
  Docker Hub 429 limits the build script now falls back to the newest already-published
  ACR-hosted `repo-rag-runtime` / `queue-initializer` images as base layers
- `../dataset` now also carries explicit submodule metadata for this repository and
  `dataset_website`, but the runtime-image and trainer-deploy helpers now prefer the sibling
  `../dspy_rag_in_repo_docs_and_impl1` checkout when it is present locally and fall back to the
  repo-RAG submodule only when no sibling checkout is available; this avoids baking stale
  champion-era code into `repo-rag-runtime` after the active repository has advanced past the
  submodule pin
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
  run; after that proof landed, the remaining bottleneck moved one layer lower into Codex-side MCP
  transport. Worker-side preflight can now complete `initialize -> resources/list`, but the actual
  Codex-launched MCP child still stalls before the first recorded `initialize` frame. The current
  repo state therefore adds two guardrails: a stable `mcp_contract_signature` in persisted Codex
  lane metadata so MCP launch-contract changes force one clean reset, and low-level MCP transport
  diagnostics (`repo_rag_mcp_debug.log` plus richer launcher stderr traces) so the next live run
  can distinguish `stdin closed`, `no bytes received`, and malformed-frame cases instead of
  flattening them all into one generic handshake timeout. The newest discovery follow-up narrows
  the remaining failure again: the old post-`initialize` transport loss is now gone, but Codex
  still burns tokens when it treats empty `list_mcp_resources` results as proof that repo-rag is
  unusable. The worker prompt and bounded MCP guidance therefore now pivot from
  resources-first/template-first discovery to tools-first discovery: Codex is instructed to call
  `search_repo` immediately for repository narrowing, then `ask_repo` for one concise
  repo-grounded answer, while resource URIs become optional supporting surfaces rather than the
  primary gate for MCP use. The next narrowing pass now also aligns the bounded MCP server with
  OpenAI's documented tool-selection heuristics: `tools/list` exposes action-oriented “Use this
  when…” descriptions, per-parameter descriptions, and explicit MCP tool annotations such as
  `readOnlyHint=true` for `search_repo`, `ask_repo`, `bundle_status`, and `dspy_artifacts`, while
  `publish_trace` is explicitly marked non-read-only. Before this pass the same `tools/list`
  payload exposed no tool annotations at all, which left Codex free to treat bounded discovery
  tools conservatively and skip MCP discovery entirely during `codex exec`. The next local control
  probes then used both the older `tap-mcp.mjs` wrapper from `../dataset` and a tap wrapper in
  front of `python -m repo_rag_lab.mcp_stdio` to inspect the actual stdio wire bytes. Those probes
  showed that current `codex exec` MCP traffic is newline-delimited JSON-RPC
  (`{"jsonrpc":"2.0",...}\n`) instead of classic `Content-Length` framing. That explained the
  earlier contradiction: `codex mcp list` could see the configured stdio server, the child process
  really was launched, and the child still timed out because `src/repo_rag_lab/mcp_server.py` kept
  waiting for header bytes that would never arrive. The repository now accepts both framing styles
  and mirrors the detected input mode on responses. After that dual-mode transport fix, local
  `codex exec` probes finally complete `initialize -> tools/list -> resources/list` against
  `repo_rag`, and direct `search_repo` MCP tool calls now appear in the transcript even with
  apps/plugins enabled. The newest live AKS artifact set now confirms that this is no longer only
  a local probe result: the actual Codex-launched MCP child in the worker answered `tools/list`
  and multiple `tools/call` requests, with `search_repo` called three times and `ask_repo` once
  during one resumed prompt run. The remaining issue is no longer “why doesn't MCP discovery start
  at all”, but “how do we reduce the still-large shell/doc churn after MCP has already narrowed
  the repo”. On the trainer side, another live-state bug also became concrete: the current stable
  bundle in Azure Blob still points to the older `20260502T122127191445Z` lineage and therefore
  does not contain later families such as `prompts_goat_labs-p00000-298625`. The root cause is no
  longer only DSPy compile overflow. After the first `goat_labs` cycle failed during recompile,
  the champion index kept the new family, but later cycles saw `new_candidate_count = 0` and
  skipped recompilation forever even though the published bundle still lagged behind the current
  champion set. The repository now contains a local trainer-side drift detector that compares the
  current family champion set against the published stable bundle lineage and forces a recompilation
  whenever the published bundle is stale, even if no additional fresh traces arrived in that cycle
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

## Current Trainer Publication Constraint

The live trainer now successfully resumes recompilation when the unpublished champion set drifts
past the current stable bundle lineage, so the dominant publication blocker has moved downstream.

The current bottleneck is trainer-side retrieval quality under live `hybrid-vector` conditions:

- lexical and `idf-rerank` retrieval already surface the expected inspired-document paths for the
  benchmark question `Where are inspired implementation summaries stored?`
- but the semantic branch inside the trainer pod can over-rank broad semantic neighbors such as
  publication or utility documents
- this can make `hybrid-vector` fail benchmark gates even when the lexical path is correct

The repository now guards that blend by adding one normalized lexical-score term into the hybrid
combiner, so strong path-aware lexical hits are no longer discarded by semantic noise. That change
matters both for the standalone retrieval gate and for DSPy bundle publication, because the trainer
reuses the same retrieval path while evaluating whether a compiled bundle may be published or
promoted. The next live trainer cycle then exposed one more layer below retrieval: the trainer was
compiling from the merged `artifacts/trainer/generated-training.yaml` corpus and also using that
same merged file as the publish-gate benchmark bank. That made the publication gate structurally
wrong for a global bundle, because imported `trainer-candidate` examples about external prompt
families such as `prompts_shards_of_lokar_game`, `prompts_goat_labs`, and `prompts_debt_relief`
were being scored by forcing live retrieval against the current repository.

The repository now keeps the benchmark path global while changing what each benchmark row carries.
Imported trainer-candidate rows can preserve:

- `benchmark_context`
- `benchmark_context_sources`

and DSPy evaluation can answer those cases from the stored benchmark context instead of forcing the
compiled program to re-retrieve evidence from the current repo. Trainer recompilation therefore now
works like this:

- compile/trainset input comes from `artifacts/trainer/generated-training.yaml`
- publish-gate benchmarking also evaluates the current generated champion set
- repo-local benchmark rows still use live retrieval
- external or cross-family champion rows may carry their own benchmark context, so the publish gate
  can evaluate them without depending on repo/branch replay identity

This is much closer to the intended contract for one global universal bundle. The standing product
requirement is that publication should be family-aware and delta-aware:

- compare candidate prompts against prior champions by request delta
- compare retrieved evidence against prior champions by context delta
- treat repo identity, branch identity, or any other fixed replay-repository surface as optional
  supporting metadata, not the primary validation contract

In other words, the target publication logic is “global champion evolution by prompt/context
deltas,” not “repo-local gate forever.”

There is also one important implementation clarification: incremental learning here does not mean
the trainer must patch an existing DSPy bundle in place forever. The current and intended pattern
is:

- keep a durable candidate pool
- maintain champion state incrementally across runs
- materialize the compile-facing dataset from the current champion set
- then compile a fresh bundle candidate from that reduced champion set

So bundle recompilation from champions is expected; what should not happen is recompiling directly
from the entire raw candidate pool or treating every replayed candidate as a fresh publish event.
Likewise, a large request/context delta should first create a new context-group or prompt-family
champion path, and only then compete at the family/bundle level. The code now reflects that in two
places:

- prompt-family assignment is no longer exact-question-only, but uses prompt similarity to keep
  close variants together and split larger prompt deltas into a new family path
- trainer-candidate rows can preserve benchmark context so global bundle benchmarking follows the
  champion set instead of collapsing back to repo-local evaluation

One additional trainer-side edge case has now been closed locally: when a later trace lands in the
same prompt family and carries the same question/answer/status key as the existing champion, that
trace can still materially improve the champion if it brings richer retrieved benchmark context.
The trainer now treats that as a real champion refresh instead of a mere support-count increment.
That matters because global bundle publication depends on the compile-facing champion set carrying
the freshest benchmark context, not just the freshest family/question identity.

Another publication-edge correction follows from the same universal-bundle contract: external
trainer-candidate champions are only fair benchmark cases when they carry preserved benchmark
context. If a historical champion row has neither repo-local expected sources nor stored benchmark
context, it is champion state but not a replayable benchmark. The bundle gate now treats those rows
as skipped rather than failed, while context-backed external rows may pass through a
context-grounded answer match instead of needing to mimic the old worker execution answer verbatim.

One more upstream contamination edge also matters: some imported trainer-candidate rows do carry
stored benchmark context, but that context still does not support the preserved expected answer.
Those rows are now pruned during trace import, champion-index reload, and combined training-example
materialization so that the compile-facing champion set keeps only replayable context-backed cases,
while older contextless historical rows still remain trainer state and are skipped later by the
bundle benchmark contract.

Another contract correction is now in flight locally: the target runtime/trainer model is no
longer “one family champion is the single universal DSPy truth object.” The active design is now
family-first:

- prompt families remain the durable trainer state
- each family gets one routing `father`
- each family gets one runtime DSPy artifact produced offline
- the published bundle stays monolithic, but internally should carry a family registry

This changes two things immediately even before the full storage/runtime rollout is finished.

First, runtime prompt-family routing is no longer supposed to use an extra soft-band branch once
the system already pays the cost of scanning every family. The correct routing rule is:

- compute prompt similarity against all family fathers
- take the maximum
- if the best score is at least `0.8`, route into that family
- otherwise treat the prompt as a new-family candidate

Second, the DSPy compile object itself can no longer drop prompt lineage. The repository now
preserves `original_prompt`, `reformulated_prompt`, and `command_trace` through trainer-candidate
materialization and composes them into the DSPy-facing question prompt used by
`BootstrapFewShot` / `MIPROv2`, so the optimizer sees more than the stripped final reformulated
question text alone.

This is still only the first transition stage. The current compatibility code keeps the old
`champion-*` names alive in several persisted paths and helper functions because live dataset /
AKS wiring still expects them. But the product direction is now explicit: compatibility champions
are an alias layer, while the intended runtime truth is `family state -> father -> family runtime
artifact`.

That alias layer is no longer only conceptual. The local repository now prefers `family_state`
surfaces across proxy lookup, trainer summaries, remote fetch/upload wrappers, and bundle drift
lineage, while still mirroring those same values back through `champion_*` keys so older live
dataset / AKS wiring can keep running during the migration.

The monolithic bundle also now carries its own internal `family_registry` built from the current
family-state file. That means runtime family lookup is beginning to move where it belongs: into
the published bundle itself. The proxy now checks that embedded registry first and only falls back
to the external family-state file when the current bundle does not yet provide one.

That family-registry step is no longer only metadata. The local trainer now compiles one
family-scoped DSPy artifact per persisted family, stores those paths in
`family_artifact_registry`, and the bundle upload/fetch path now moves those family
`program.json` / `metadata.json` files beside the global compiled program. The proxy can therefore
route into a family and execute that family's compiled artifact directly instead of always
falling back to the global bundle program.

Runtime prompt lineage is also carried further than before. Once a family match exists, the proxy
now invokes the matched family artifact with `original_prompt`, `reformulated_prompt`, and the
current `command_trace`, so the family runtime path sees the same lineage dimensions that already
survive trainer-candidate materialization and DSPy compile input composition.

The trainer side is now more faithful to the intended family lifecycle too. Family state carries
an explicit `family_needs_recompile` flag, new imported traces mark the touched family dirty, and
successful family compilation clears that flag again. That lets the compile step stop pretending
that every family changed every cycle: dirty families are recompiled, while clean families carry
their previous runtime-artifact references forward into the next monolithic bundle.

The remote state contract has also moved one step closer to the intended storage model. Local
Azure config resolution and remote family-state fetch/upload now treat
`REPO_RAG_FAMILY_STATE_CONTAINER` / `repo-rag-training-families` as the primary container
contract, and versioned uploads now write only the primary `family-state.json` blob. Older
remote snapshots that still point at `champion-index.json` remain readable through fallback logic,
but the family-first path no longer republishes that mirrored champion blob on new writes.

That remote family-state contract is no longer only an index-level mirror either. Each upload now
also writes one versioned `family.json` blob per prompt family under
`versions/<family_state_version>/families/<prompt_family_id>/`, and remote fetch reconstructs a
matching local cache tree for those family records. The container is therefore starting to expose
the family-directory shape we actually want, even though the full replay-set layout is still not
there yet.

That same container is now also less redundant operationally. Earlier iterations mirrored
`family-state.json` plus `families/<prompt_family_id>/...` at the container root even though the
runtime only needed `current.json` and the immutable versioned history. The active contract now
keeps only `current.json` at the root and stores all family payloads under
`versions/<family_state_version>/...`, which preserves a cheap “what is current?” lookup without
duplicating the entire family tree one level higher.

The local trainer contract now mirrors that naming more honestly too. The primary persisted local
state file is `artifacts/trainer/family-state.json`, remote fetch caches live under
`artifacts/trainer/remote-family-state/`, and `champion-index.json` now remains only as a
fallback read source for older local snapshots that have not been migrated yet.

That naming correction now reaches the operator-facing diagnostics too. Pending-recompile reasons,
trainer-cycle warnings, and related state summaries now describe the active object as a family set
and family drift, instead of continuing to present champion wording as the primary runtime/trainer
contract.

The deployment handoff now follows that same contract too. Dataset-side workflow env,
repo-rag-storage secret generation, trainer deploy bootstrap, and the generated deployment-script
templates now export `REPO_RAG_FAMILY_STATE_CONTAINER` /
`DATASET_REPO_RAG_FAMILY_STATE_CONTAINER` as first-class storage inputs. That deployment-facing
layer no longer emits champion-named container env vars at all; only the repo-side runtime/config
readers still accepted those old names as fallbacks so older live environments could continue to
boot during the transition.

That reader-side compatibility has now narrowed one layer further too. Azure artifact config
resolution no longer treats `REPO_RAG_CHAMPION_CONTAINER` /
`DATASET_REPO_RAG_CHAMPION_CONTAINER` as valid family-state inputs. The only active env contract
for remote family-state storage is now the family-state naming itself; champion naming remains
only in mirrored local files, compatibility wrappers, and older machine payload fields.

The remote family-state machine payloads have now been tightened in the same direction. Upload and
fetch responses for remote family-state snapshots no longer emit `champion_container`,
`champion_version`, `champion_found`, or `champion_index_path` as active fields. New uploads no
longer write a mirrored `champion-index.json` beside `family-state.json`, and the API contract now
advertises the family-state path as the only first-class result.

The same cleanup now reaches newly written `current.json` blobs too. Fresh family-state snapshots
no longer record `champion_state_kind` or `current_champion_index_blob`; those names remain only
in fallback read logic so older snapshots can still be restored during the migration window.

That cleanup now reaches trainer-side machine summaries too. `training-candidates` materialization,
the JSON returned by `trainer-candidates`, and pending-recompile summaries no longer advertise
`champion_index_path` or the mirrored `champion_*` family-hash/path counters as active fields.
The active local/output path now writes only `family-state.json`, while older
`champion-index.json` snapshots remain readable as migration input. The machine contract points
callers only at `family_state_path` plus the family-state counters.

The trainer ingest loop is now closer to the intended incremental cost model too. The original
durable-recovery path mirrored every `processed/...` queue item back into local trainer storage on
every cycle and then let candidate materialization fall back to the full imported-trace ledger
when the recovered list was empty. That replayed historical traces even when no new queue items
arrived. The current path restores only not-yet-mirrored processed blobs and treats explicit
`trace_paths=[]` as “ingest nothing new,” so trainer work now scales with new queue arrivals
instead of the full accumulated ledger.

The remaining public helper surface has narrowed too. The repo no longer exposes separate
`repo_rag_champion_container(...)`, `upload_remote_champion_index(...)`,
`fetch_remote_champion_index(...)`, or champion-named blob-name helpers. Compatibility now stays
where it actually matters: fallback reads for older stored state, not mirrored active files or
parallel public helper APIs.

The global compile path is also starting to lose obviously unnecessary work. When the latest
global DSPy artifact still matches the current training, benchmark, optimizer, retrieval, and LM
surface, and its persisted training/benchmark example signatures still match the newly materialized
compile-facing dataset, the new run now carries that previous global `program.json` forward
instead of recompiling it. That means dirty-family cycles can now skip the global compile when
they only changed family-local runtime artifacts. The remaining transition caveat is older global
metadata that predates these signatures: that older metadata still forces one full global compile
before later dirty-family cycles can reuse the global object safely.

That also clarifies the role of `MIPROv2`. It is not supposed to sit inside the proxy as an
online per-turn selector. It belongs in the offline trainer path:

- collect family replay sets
- recompile only dirty families
- publish one bundle whose internal registry points from family id to father and family runtime
  artifact

The remaining implementation gap is therefore not “add more DSPy somewhere.” It is: finish the
family-state storage surfaces in their final remote container shape, remove the remaining
repo-side compatibility `champion-*` aliases, and keep feeding post-run real `hits / total` back
into trainer ingestion and live AKS validation.

The first post-gap hotfix set on `2026-05-10` tightens that story in four concrete places. Bundle
resolution now prefers the locally staged mirror and no longer treats legacy `published.json` as a
hard requirement, so older published bundles do not force the proxy back into heuristic mode when
`bundle.json`, `metadata.json`, and `program.json` are present. The AKS bundle staging script now
also mirrors family `program.json` / `metadata.json` blobs into `.repo_rag_bundle_store`, which is
the missing local substrate the family-first runtime path actually needs to execute matched family
artifacts instead of only the global program.

The same hotfix pass also addresses the trace-shape and token-growth failures that showed up in the
downloaded AKS artifacts. Dataset-specific execution scaffolding is now stripped not only from the
proxy's `original_prompt`, but also from the user-facing `command_trace` step before that lineage
is persisted or exported. When the proxy did not already persist a local `repo_rag_turn_traces/`
batch, the worker now synthesizes one compact per-turn batch from `repo_rag_codex_proxy_last.json`
plus the final execution outcome, instead of exporting the entire `codex_response.txt` transcript
as the trainer-facing answer payload.

The next trainer-side hardening pass closes the bundle-version storm that the user observed on
`2026-05-11`: idle `trainer-service` cycles could previously keep minting fresh timestamped bundle
versions whenever `pending_recompile` stayed true from old lineage drift, even if the current
cycle had imported no new traces. Automatic recompilation now requires current-cycle queue input,
and processed-ledger recovery no longer contributes active trace paths to the recompile path.
The next local service hardening pass closes the remaining operational gap in that same area:
even after the version-storm fix, the long-lived `trainer-service` still entered
`run_trainer_cycle()` on every poll interval and only discovered the empty queue from inside the
cycle. Repo-rag now performs an explicit preflight before each service iteration, measuring queue
visibility alone for cycle authorization, and it skips `trainer-cycle` entirely when `queued/`
contains no fresh trace input. Unrecovered processed traces remain visible diagnostically, but they
no longer start work or augment an active cycle. The current Kubernetes deployment is still
poll-based rather than queue-event-driven, but after this fix the service only starts a real
trainer cycle when queue input is actually present.

Finally, the session-resume contract is now explicit rather than accidental. The worker-side default
for automatic Codex session lanes is `queue_and_slug`, and the generated AKS pod env now exports
that same value explicitly unless an operator overrides it. That does not yet prove a live token
drop on its own, but it removes the earlier repo-wide resume-lane default that allowed unrelated
prompt runs in one repository to keep inflating the same resumed conversation state.

The next hotfix pass on `2026-05-10` closes the remaining local gaps from AKS run
`25629990035_20260510_134639`. The proxy now treats the staged worker mirror as a first-class
bundle store: if `bundle.json` still references the original trainer-side `artifacts/dspy/...`
paths, the runtime can still activate `versions/<bundle_version>/program.json` and
`versions/<bundle_version>/families/<family_id>/program.json` directly. When the bundle-local
`family_registry` is missing, the proxy now synthesizes one from `family-state.json` so family
lookup can still proceed instead of collapsing straight into heuristic-only mediation. The same
pass also strips the Discord forwarding tail from every prompt-lineage field and teaches the
deploy-stage trusted handoff to stand down once the worker already emitted a successful per-turn
batch enqueue/import summary, so the family-first compact trace path is no longer doubled by the
runner-side legacy queue upload.

The follow-up local fix set after AKS run `25632110510_20260510_152621` addresses the last three
execution-stage gaps that were still visible in downloaded artifacts. First, bundle activation no
longer depends on channel metadata alone: both the proxy and the worker can now recover the latest
staged bundle version directly from `.repo_rag_bundle_store/versions/<bundle>/...` or
`artifacts/dspy/remote/<bundle>/...` when `stable.json` or older published-manifest surfaces are
missing. Second, the worker now builds a task-first `codex exec` prompt body, so Discord channel
headers, forwarded tails, and attachment-dump noise stay in persisted artifacts instead of being
sent to the model as live context. Third, the generated AKS pod env now enables the already
implemented resumed-lane reset policy by default through `DATASET_CODEX_MAX_RESUMED_RUNS=9` and
`DATASET_CODEX_PROMPT_TOKEN_GROWTH_RESET_RATIO=2.0`, which should cap the repeated
`queue_and_slug` rerun pattern that previously drove prompt-token usage back into six figures.

The next local fix on the same date closes the remaining deploy/runtime blind spot that left live
execution pods in heuristic mode even after trainer-side family compilation started to work.
Remote bundle fetch now falls back to the latest immutable bundle version in Azure Blob when the
stable channel blob is absent, and the dataset deploy-stage bundle mirror now performs that same
lookup before it stages `.repo_rag_bundle_store`. When that fallback path resolves a version, the
staged worker mirror also synthesizes a minimal local `channels/stable.json` pointer to the
resolved bundle so the execution-side proxy can activate compiled family artifacts without relying
on a separately published channel record.

The newest live inspection on `2026-05-10` sharpened the remaining gap again. The
`repo-rag-training-families` container is no longer empty in live AKS; it already carries
`current.json`, container-root `family-state.json`, and per-family `family.json`, `father.json`,
and `records/<snapshot>.json` payloads. The execution-stage blocker moved upstream of storage:
trainer-side family materialization was still persisting polluted father questions that included
`Repository checkout:` and `Attachment mount:` scaffolding, so runtime family matching compared a
clean prompt against dirty stored fathers and kept classifying the turn as a new family. The same
inspection also exposed one old champion-era policy that no longer fits the family-first design:
bundle publication was still being blocked by an implicit `minimum_bundle_pass_rate = 1.0`. The
current local fix set therefore sanitizes trainer-side prompt lineage with the same rules as the
execution proxy, removes that implicit publish gate unless an operator explicitly requests one,
and keeps `trace-export` artifacts out of the target repository worktree so Codex does not spend
tokens diffing its own exported traces.

The next local correction on `2026-05-11` tightens the family-first contract in the two places
where the latest live artifacts were still drifting from intent. First, family routing now
compares fathers against `original_prompt`, not the helper-produced `reformulated_prompt`, so
runtime reuse is keyed off the raw task surface that the trainer also persists in `father.json`.
Second, deploy-stage trusted handoff now prefers the worker's turn-trace batch manifest plus the
exported per-turn trace records, and only falls back to the coarse single proxy payload when no
valid worker batch exists. That keeps trainer ingestion aligned with the per-turn traces that
actually produced the family decision instead of silently collapsing back into one coarse ledger
item.

That handoff contract needed one more correction on `2026-05-19`. The proxy emits
`repo_rag_turn_traces/<batch>/...` before the upstream Codex response finishes, so the raw batch
records contain mediation-time summaries rather than the final execution answer. The worker now
rewrites those batch traces with the final execution answer/evidence before queue handoff, and the
trainer rejects any `codex-proxy-turn-execution` record that still carries the proxy fallback text
`No father-backed prompt-family support was found ...`. In the same fix, empty-baseline trainer
cycles stopped pre-seeding a temporary family index from the current cycle traces before the real
materialization pass. That restores the intended invariant: whether or not a previous remote
library exists, the trainer sees the same class of valid execution-stage traces and applies the
same family-assignment logic.

One more deployment-side defect surfaced immediately after that handoff refactor. A generated
Python heredoc inside the dataset deploy script carried an unmatched `)` in the trusted-handoff
helper, so worker execution could finish, Redis could receive the final result, and inline
artifact rehydration could even succeed locally, yet the script would still abort before the Azure
upload stage. The practical symptom was an empty latest `execution-artifacts` blob upload even
though the worker had already finished its Codex run. The current local hotfix removes that syntax
error from both the deployment template and the checked-in generated script, restoring the
post-run path from rehydrated worker artifacts to Azure blob upload.

The next execution-stage fix addressed the remaining reason DSPy family reuse was still absent even
after family-state population started to work. Two separate gaps were responsible. First, the
dataset workflow enters `cd aks_modules` before invoking `./deploy.sh`, but the generated deploy
script still looked for `tools/pvc_artifact_sync.sh` relative to the current shell directory. That
silently disabled `.repo_rag_bundle_store` staging even though the helper script existed in the
dataset repository. Second, `repo-rag-training-families` carried `family.json`, `father.json`, and
`records/...` but not the executable `runtime-artifact/program.json` / `metadata.json` files for
each family, so a worker could match a father yet still have no runnable local program to load.
The current local fix therefore makes remote family-state uploads carry those runtime-artifact
files, rewrites `family_runtime_artifact` paths onto the local worker cache when family-state is
fetched, and resolves the PVC sync helper from the dataset repository root instead of the current
working directory. After the next trainer upload cycle, a worker can execute a matched family
artifact directly from `repo-rag-training-families` even when `repo-rag-bundles` is still empty
or unpublished.

One last bridge bug remained even after that transport work: a worker could match a family father
from bundle-local registry data yet still fall back to heuristic execution because the registry's
recorded `program_path` was stale. The proxy now keeps bundle-local registry priority when those
paths are valid, but lazily synthesizes a replacement registry from fetched `family-state.json`
when the matched family entry has no runnable local `program.json`. That same fix also normalizes
the selected `program_path` to a repo-relative path when the runtime artifact lives under the
family-state cache instead of the staged bundle mirror, and exported trainer-facing trace records
now surface `prompt_family_id`, `prompt_family_similarity`, `family_artifact_selected`,
`bundle_version`, `program_path`, and mediation metric fields directly. The family-first runtime
contract is therefore locally coherent end-to-end again: father match can now resolve into a
family-state-backed DSPy runtime artifact instead of stopping at heuristic mode.

The next trainer-side redesign closes the other half of the version-storm problem. The intended
contract is no longer “copy the previous version into blob again and then mutate it remotely”; it
is “maintain one active local family cache, apply only current queued traces, and publish only the
resulting updated state once.” The local trainer now follows exactly that lifecycle. If
`artifacts/trainer/family-state.json` plus `artifacts/trainer/families/<id>/...` already exist,
that cache is reused in place. If the local cache is absent, trainer adopts the latest remote
`repo-rag-training-families` version into the same local cache. Only when neither local nor remote
state exists does trainer rebuild its cache from `repo-rag-training-traces/processed`, and that
bootstrap rebuild stays local until the current `queued` traces are applied. This removes the old
failure mode where one trainer run could first materialize a remote family-state snapshot from
historical traces and then immediately publish a second version after applying the current queue.

That redesign also finally makes `family-state.json` fit its intended role. It is no longer a full
aggregate replay buffer duplicated beside `family.json`, `father.json`, and `records/*.json`, and
it no longer embeds inline `family_father_record`, `family_runtime_artifact`, `family_records`, or
`context_groups` payloads. The top-level file is now a thin index with routing summaries, score
metadata, dirty flags, counts, and per-family paths, while the full transformed family payloads
live only under `artifacts/trainer/families/<prompt_family_id>/`. In other words, the durable
local cache is the per-family directory tree; `family-state.json` is the manifest that points at
it.

One more live bug remained after that redesign: replaying the same processed queue item into a
fresh local cache still produced a new imported trace filename, and the trainer treated that new
filename as a brand-new snapshot. In practice that meant a later trainer cycle could take the same
logical 25-turn batch and inflate one family from 25 replay records to 50 without ever seeing a
new worker run. The fix is now explicit in code: imported trace records persist their original
queued-item identity, trainer snapshot IDs prefer that stable source token over the transient
imported path, and family-state hydration plus replay upserts dedupe logical replays instead of
double-counting them. The same pass also stops writing a new remote family-state version when a
cycle loaded no accepted/candidate records, so empty no-op versions no longer appear as if they
were meaningful training outputs.

The newest runtime bridge correction addresses the last mismatch between the user's intended
metric contract and what the worker actually used in live runs. Forwarded Discord cleanup is now
line-based in both the dataset worker and the proxy, so the forwarded marker and its immediate
attachment companion line disappear without deleting later user-authored task lines. That closes
the bug where a trailing instruction such as “This is a test run, no development or installation
required.” survived in the aggregated prompt artifact but vanished before `codex exec` saw it. The
same patch also stops treating bundle `benchmark_pass_rate` as if it were the same thing as the
family trace `hit_rate`. Persisted family runtime artifacts now carry their own metric-1
`hit_rate`, benchmark pass-rate remains diagnostic only, and family-artifact selection can finally
decide “matched family artifact vs heuristic fallback” on the same semantic quantity the trainer
stores in family state.

The next runtime hardening pass fixes two more worker-side leaks that the family-first trace
contract could not tolerate. First, the local proxy no longer spawns a fresh request-handling
thread per Codex turn; it now serves the worker-side mediation path on one dedicated HTTP server
thread, which keeps `dspy.settings.configure(...)` on a single DSPy thread and removes the
live-only fallback that previously emitted `dspy.settings can only be changed by the thread that
initially configured it.` Second, the proxy now stops exporting trainer-facing traces when a
matched family artifact already ran successfully and dedupes repeated same-prompt snapshots within
one rollout even if the visible `command_trace` keeps growing. That shifts trace generation back
toward the intended contract: new trainer traces should come from genuinely new mediation misses,
not from later snapshots of one unchanged outer prompt.

The next operational bug was not about routing correctness but about hidden Azure spend. Even
after GitHub Actions variables were switched to `gpt-4o`, live AKS traffic still burned mostly on
`gpt-5.4` because two stale-default paths preserved the expensive model: trainer deployment
defaults in `../dataset/deploy_repo_rag_trainer.sh` and the `CODEX_AZURE_CONFIG` secret consumed
by Azure Codex workers. The dataset-side fix now rewrites Azure Codex config payloads to the
configured default model (`AZURE_OPENAI_MODEL_NAME` / `AZURE_OPENAI_DEPLOYMENT_NAME`) before the
secret is created or worker auth normalizes it, while keeping explicit prompt `model_hint`
overrides as the highest-priority Codex path. That preserves the intended split of responsibilities:
`codex exec` follows `CODEX_AZURE_CONFIG(+model_hint)`, whereas trainer/helper DSPy calls continue
to follow `DSPY_*` first and then `AZURE_OPENAI_*`.

The next runtime hardening pass closed three more live leaks that showed up only in AKS artifact
inspection. First, bundle lookup now treats the remote Azure `stable` channel as authoritative
whenever blob-backed bundle storage is configured; workers no longer silently fall back to an old
local `.repo_rag_bundle_store` mirror after the remote bundle channel or version was deleted.
Second, trusted trace handoff now prefers the final `repo_rag_trace.json` surface and mirrors the
selected prompt-family/runtime fields onto the outer queue payload, so queued traces no longer
report `prompt_family_id = null` while the local runtime trace in the same run says a family
artifact was matched and executed. Third, Codex reset-on-rollover is now a real lifecycle reset:
when a lane is reset because of resumed-run caps, session age, prompt-token growth, operator
reset, or resume-failure thresholds, the worker clears the persisted lane counters and prior
session identifiers before the next snapshot is written instead of continuing the old lane's
metadata under a nominal `reset`.

One more wrapper-level follow-up remained after that fix. Batch trace export/enqueue summaries and
trusted queue items now also mirror the nested trainer-family signal surface
(`prompt_family_band`, `trainer_signal_kind`, and the family success-posterior fields) onto the
outer payload instead of leaving that state only inside `trace_payload.trace`. The same handoff
pass also fixes one stale batch-name bug where every generated queue-path summary could inherit the
last `...-N.json` suffix from the export loop even though the underlying queue items were distinct.

The next trainer-cycle fix closed a separate publish deadlock. A cycle that drained fresh traces
but still observed queue backlog would defer recompile and remote publish, yet the first later
idle cycle still exited down the `no-queued-input` fast path before it could compile the pending
family-state. That left both `repo-rag-training-families` and `repo-rag-bundles` empty even
though the queue had already been processed. `run_trainer_cycle(...)` now treats a pending family
state as sufficient reason to continue past that idle fast path, recompile on the first backlog-
free cycle, and upload the resulting family-state/bundle instead of stranding them locally.

The prompt-family anti-drift pass stayed intentionally conservative. Rather than splitting or
merging families after the fact, the trainer now keeps term-frequency maps for prompt, command,
and constraint signals and derives the active routing summaries from only the stable top-k terms.
The stability threshold scales with family size, so young families still get a usable profile
immediately while larger families stop promoting one-off trace vocabulary into the live routing
surface.

That profile state is now also normalized into one per-term statistics payload instead of being
spread across separate count and weight structures. Each prompt/command/constraint term can carry
its raw count plus normalized weight inside one `*_term_stats` mapping, while the legacy
`family_*_terms` lists remain only as derived routing summaries for fast lookup and human
inspection. The active prompt-profile summary is also capped at 12 terms and filters recurring
conversational filler such as `just`, `really`, `whether`, and `needed`, so the published family
surface stays biased toward technical artifacts, tools, paths, and repo-specific task vocabulary
instead of narrative boilerplate. The term extraction logic now lives in its own
`repo_rag_lab.term_extraction` module, where multiple themed technical-term `frozenset`
collections feed one flattened O(1) hash lookup. Those categories now span repository workflow,
Git, CI/deployment, cloud/runtime orchestration, frontend media, browser automation, programming
languages, databases, APIs, data science, neural-network terminology, research/publication work,
infrastructure/devops, Linux/Windows command surfaces, explicit Kubernetes vocabulary, cloud
service names, and game-development terminology. The active family summary is no longer chosen by
an open-ended term bag: the contract is now explicit that `family_prompt_profile_terms` must be
the top 12 surviving terms after garbage-word filtering, with technical-dictionary terms taking
priority over generic helper phrasing. If published family profiles are led by narrative filler
such as `add`, `any`, `changes`, `commands`, `completed`, `ensure`, `files`, `required`, `steps`,
or `tasks`, that is a contract violation rather than an acceptable quality trade-off.
raw count ordering alone: a dedicated selector now prefers technical lookup hits, suppresses broad
narrative terms such as `already`, `contains`, `does`, and `fields`, and is allowed to publish
fewer than 12 active prompt terms when the remaining candidates are only low-value filler. Prompt
routing still falls back to filtered general tokens when the technical lookup alone does not yield
a usable profile, but the active routing surface is now intentionally narrower and more technical
than the underlying full `*_term_stats` store.

The latest live trainer debug pass exposed one more cron-only publish trap. Worker export,
trusted queue handoff, and queue drain were all healthy, but a cron-only trainer cycle could still
drain `queued/` into `processed/` and stop there if no explicit `recompile_run_name` had been
passed into the cycle command. In that state `run_trainer_cycle(...)` observed fresh imported
traces and even built training candidates, yet it never crossed into the recompile/publish branch,
so `repo-rag-training-families/current.json` and `repo-rag-bundles/channels/stable.json` stayed
missing after an otherwise successful drain. The trainer deployment defaults now pin the cron path
to `TRAINER_RECOMPILE_RUN_NAME=trainer-auto`, and the cycle itself now auto-adopts that same run
family whenever fresh candidates or a pending unpublished family-state are present but no explicit
run family was provided. That makes the compile/publish path resilient both to stale manifests and
to manual one-shot cycle invocations that omit the recompile flag.

The next live inspection narrowed the remaining queue-layer issues to duplicate logical imports
and thin batch summaries. The deployment-side trusted handoff could still requeue one worker batch
when `repo_rag_backend.json` already said `trace_queued=true` but the older worker-side
`repo_rag_turn_trace_enqueue_batch.json` surface was missing or incomplete, and trainer queue
drain treated those duplicate queue items as distinct because their Azure blob names differed.
The current fix therefore makes trusted handoff stand down on successful worker backend status as
well as explicit batch-summary files, mirrors prompt snapshots into trusted batch summaries, passes
`--batch-name` through worker-side `trace-enqueue`, and suppresses duplicate logical queue items
inside one drain cycle before they can create extra `processed/...` blobs.

The next trace-handoff correction is stricter about family reuse itself. A successful DSPy family
match is allowed to change routing, but it is not allowed to hide trace lineage from the trainer.
The runtime therefore no longer short-circuits helper/lineage trace persistence when
`family_artifact_selected=true`, and worker-side synthetic batch seeding no longer skips fallback
turn-trace creation merely because the reused family artifact already answered the prompt.

## Tensions And Open Work

The narrative is coherent, but not complete. The main open tensions are:

- retrieval is still relatively simple compared with the sophistication of the DSPy training path
- notebook execution is well observed, but notebook conclusions still depend on the quality of the
  underlying corpus and benchmarks
- deployment handoff is documented, but live remote deployment is intentionally outside repo scope
- the runtime now has a first-class split between `DSPY_HELPER_*` and `DSPY_TRAINER_*`, with
  default helper/trainer model selectors pinned to `azure/gpt-5.4-nano` and
  `azure/gpt-5.4-mini` respectively, while shared `AZURE_OPENAI_*` values remain transport
  fallback only and are mirrored through the dataset worker manifest plus GitHub Actions env path
- verification evidence is strong, but the index docs must be kept synchronized so the narrative
  does not drift behind the latest audit and CI state; the current CI contract is stricter than
  the local MCP/debug loop alone and now explicitly depends on `uv run mypy src tests`,
  `uv run basedpyright`, `uv run ruff check src tests`, and `make pages-build` staying green
  after each repo-sync or audit-surface change

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
