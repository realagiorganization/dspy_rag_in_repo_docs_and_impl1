# Family-First DSPy / MIPROv2 Contract

Date: `2026-05-09`

This document supersedes
[docs/planning/per-turn-dspy-mediation-contract.md](per-turn-dspy-mediation-contract.md)
where the two contracts disagree.

## Goal

Keep `codex exec` as the only orchestrator, keep one published bundle, but move the DSPy system to
a family-first model:

- prompt families stay
- champion-only compile compression goes away as the target design
- each family gets one routing `father`
- each family gets one runtime DSPy artifact produced by `MIPROv2`
- the published bundle stays monolithic, but internally carries a registry of those families

The critical semantic rule is:

- a prompt family is a **stable semantic stage / code block**
- it is **not** required to equal one whole end-to-end workflow
- the same family may be reused by different workflows when they arrive at the same stage
- one workflow may legitimately contribute traces to multiple families when it passes through
  multiple distinct stages

Examples of stage-level families include:

- declaring or reframing the root objective
- checking whether a repo artifact already exists
- validating whether an existing artifact is semantically real rather than merely present
- deciding whether regeneration is necessary
- producing a constrained close-out when rerun is intentionally skipped

## Runtime Contract

1. Every outbound request to the model passes through the local proxy.
2. The proxy extracts `original_prompt` for the current turn.
3. The helper DSPy model reformulates that prompt into `reformulated_prompt`.
4. The proxy compares the incoming prompt against **every family father** and computes one
   similarity score per family.
   That routing comparison must use `original_prompt`; `reformulated_prompt` belongs to the DSPy
   mediation surface, not to father matching.
5. `metric 3` is the maximum of those scores.
6. `metric 2` is the binary family-membership decision derived from that maximum:
   - if `metric 3 >= 0.8`, the prompt belongs to the best-matching family
   - if `metric 3 < 0.8`, the prompt does not belong to any existing family and must create a new
     family later through trainer ingestion
7. When a family is found, the proxy uses that family's precomputed DSPy runtime artifact from the
   latest bundle.
8. When no family is found, the proxy does a fresh meditation path and still records the turn as a
   new training trace.
9. `command_trace` is first-class lineage and must be preserved beside `original_prompt` and
   `reformulated_prompt`.

There is **no active soft-band branch** on the runtime routing path. The expensive part is already
the full-family scan, so the decision is:

- compute similarity to all fathers
- take `argmax`
- apply the single `0.8` gate

## Metrics

Only these metrics belong on the active path:

1. `metric 1`: `hit_rate = hits / total`
2. `metric 2`: binary belongs / does-not-belong decision
3. `metric 3`: best father similarity across all families

No additional weighted scoring, hidden deltas, blended replacement math, or trainer-side magic
numbers are allowed on the active decision path.

## Family State

Each family has two different roles and they must not be collapsed into one object:

- `father`
  - routing prototype
  - chosen mathematically as the most central family record
- `family_runtime_artifact`
  - the precomputed DSPy artifact used at runtime for that family
  - produced offline from the family's replay set

The repository still carries compatibility aliases named `champion` in some code paths, but the
target contract is:

- families, not champions, are the durable trainer state
- fathers are for routing
- family runtime artifacts are for execution

Family correctness is judged against the stage-level semantic contract above:

- traces from one workflow do **not** need to collapse into one family
- traces from different workflows **may** belong to the same family when they represent the same
  reusable stage
- trainer should prefer stable stage reuse over workflow-local bundling

## Term-Profile Contract

The active `family_prompt_profile_terms` surface is intentionally narrow and must be built by a
fixed filtering pipeline.

Required contract:

1. Start from the real prompt text carried by the trace surface being routed or trained.
2. Remove previously defined garbage words, stopwords, and narrative filler first.
3. Prefer technical terms from the explicit repository term dictionary over generic narrative
   wording.
4. Rank the surviving candidates and keep only the top `12` terms for the active prompt-profile
   surface.

This means:

- `family_prompt_profile_terms` must be a top-12 surface, not an unbounded bag of words
- the active profile must be produced after garbage-word filtering, not before it
- technical terms from the explicit dictionary have priority over broad narrative words
- generic helper wording must not dominate the active family profile

Examples of words that must not dominate the active prompt profile include:

- `add`
- `any`
- `cannot`
- `changes`
- `commands`
- `completed`
- `ensure`
- `files`
- `required`
- `steps`
- `tasks`

If published `family_prompt_profile_terms` are dominated by words like the list above instead of
technical task vocabulary, that is a contract violation rather than a subjective quality issue.

## MIPROv2 Contract

`MIPROv2` is offline optimizer compute, not online per-turn routing compute.

For each dirty family:

1. Trainer loads that family's replay set.
2. Trainer runs `MIPROv2` on the family replay set, not on one single exemplar.
3. The result becomes the family's updated DSPy runtime artifact.
4. Only dirty families are recompiled in one trainer cycle.

The bundle remains one published object, but it should contain a family registry with at least:

- family id
- father
- validated family hit rate
- family runtime artifact

## Trace Contract

Every saved turn trace must keep:

- `original_prompt`
- `reformulated_prompt`
- `command_trace`
- `metric_hits`
- `metric_total`

Those traces accumulate locally during the run, then move together as one batch into the trainer
queue and the durable trace store.

Per-trace payload discipline is strict:

- every prompt that reaches the proxy forms its own separate trace
- the main `codex exec` flow is a trace
- every auxiliary helper-LM flow is also a separate trace
- successful DSPy family reuse must not suppress helper or lineage traces; reuse changes routing,
  not trace visibility
- per-trace files must contain only prompt-relevant lineage and outcome fields
- per-trace files must **not** embed shared full-run payload that belongs to the whole execution
  rather than to that specific prompt
- forbidden shared payload in per-trace files includes:
  - one common full-run `command_trace` copied into many traces
  - one common full-run `outcome` blob with full session/token/debug state copied into many traces
  - one common nested execution transcript or proxy payload copied into many traces
- trainer-visible trace files should stay thin enough that different prompts remain distinguishable
  by their own relevant fields rather than by a duplicated shared run tail

## No-Dup Serialization Contract

Generated artifacts must have one canonical owner per datum.

- if one nested runtime `trace` already owns `question`, `original_prompt`,
  `reformulated_prompt`, `sources`, `command_trace`, or routing metrics, outer envelopes must not
  mirror those same values again
- command envelopes, queue items, processed items, and stored trace records may keep only fields
  that are not recoverable from the canonical nested owner
- `family.json` must not inline full `family_father_record` when the same record is already
  persisted in `father.json` or in `records/*.json`
- `family.json` must not inline full `family_runtime_record` when one stable record reference is
  sufficient to resolve it from `records/*.json`
- `bundle.json` / bundle family registries must not carry full replay records when runtime routing
  only needs compact family summaries plus the runtime artifact surface
- derived scalars like `normalized_question` or `question_variant_count` should not be persisted in
  JSON payloads when they can be recomputed exactly from the canonical stored fields
- the published SQLite `family-index` must use one canonical routing question per family; it must
  not persist `question`, `normalized_question`, and `family_father_question` together when the
  latter two add no information beyond the canonical `question`
- remote family-state sidecars must stay structurally aligned with the index: if the index exposes
  `father_path`, the corresponding `father.json` must actually be published rather than dropped by
  a compact-write path

Duplication is allowed only when removing it would lose information or would make one artifact
non-self-sufficient for its declared role.

Legacy or historical compatibility is not by itself a valid reason to mirror fields into newly
generated artifacts. If one surface still needs an older shape, the compatibility shim must be
kept at read time or at a dedicated translation boundary rather than by bloating every newly
written trace, family, or bundle file.

## Trainer Ingestion Contract

Trainer-side family assignment is intentionally stricter than runtime father lookup:

1. Each imported trace is normalized into one trainer candidate record.
2. Before matching, trainer lifts that record into one temporary **singleton family** with:
   - one father question
   - one prompt-profile summary
   - one command-pattern summary
   - one constraint summary
3. Trainer compares that singleton family against every persisted family with one **symmetric**
   family-to-family score.
4. If the best symmetric score is `>= 0.8`, the trace joins that family.
5. Otherwise trainer creates a new family.

This is different from the older directional `trace -> family` logic. The family-first target
contract requires matching objects of the same kind during ingestion; otherwise trace assignment
becomes order-dependent and one trace can fail to join a family even though the singleton family
created from that same trace would have matched it later.

This ingestion pass must evaluate traces against the **stage-level** family definition:

- if two traces belong to the same repeatable semantic stage, they should converge even when they
  came from different workflows
- if two traces came from the same workflow but represent different semantic stages, they may stay
  in different families
- therefore trainer quality should not be evaluated by asking whether one workflow produced one
  family; it should be evaluated by asking whether stable stages were grouped consistently

## Storage Contract

Target blob/container layout:

- `repo-rag-training-traces`
  - append-only raw turn traces, grouped by run/batch timestamp
  - append-only final execution traces, mirrored into queue/import surfaces for trainer ingestion
- `repo-rag-training-families`
  - durable family state and replay sets
- `repo-rag-bundles`
  - published monolithic bundles with family registry inside

Active family-index rule:

- do not generate `family-state.json`
- generate `artifacts/trainer/family-index.sqlite3`
- keep full family payloads in `families/<prompt_family_id>/{family.json,father.json,records/*.json}`

The SQLite file is now the only generated routing index. Legacy JSON family-state paths may still
be accepted as compatibility inputs during migration, but they are no longer the generated
source-of-truth.

Runtime routing rule:

- `repo-rag-training-families` exists to find the correct `prompt_family_id`
- `repo-rag-bundles` exists to execute the DSPy program for that selected family
- lookup is now two-stage:
  - coarse shortlist from `family-index.sqlite3`
  - rich family scoring only for the shortlisted families
- the family index must not store compiled DSPy programs
- the Codex mediation block should stay compact:
  - one short execution line
  - optional `prompt_family_id`
  - one short summary
  - at most two file hints
  - at most one evidence snippet
- runtime, not trainer, owns the expensive replay-admission decision:
  - every run may emit a trainer-visible trace
  - but the decision `feedback_trace` vs `full_trace` must be made before trainer ingestion
  - trainer must not perform broad trace-to-trace similarity scans just to reject near-duplicates
- worker-side turn-trace batches are audit-only:
  - raw proxy mediation drafts are audit/debug artifacts only
  - but enriched per-turn batch traces from `repo_rag_turn_traces/<batch>/...` are the preferred
    trainer-ingestion surface when a real batch exists
  - the final single exported execution trace is a fallback handoff surface only when no usable
    per-turn batch exists or batch handoff fails
  - enrichment must overwrite proxy fallback summaries with the final execution answer/evidence so
    from-scratch family formation never depends on preexisting family support
- trainer ingestion must reject mediation-only traces as non-training inputs:
  - `source_command = codex-proxy-turn-mediation`
  - or `trace.mode = codex-proxy-turn-mediation`
  - those records remain valid audit/debug artifacts, but must not seed or rebuild prompt families
  - trainer must also reject `codex-proxy-turn-execution` traces if their answer still equals the
    proxy fallback string `No father-backed prompt-family support was found ...`

## Trainer Cache Contract

Trainer may keep one local internal cache, but that cache is never authoritative.

- The only durable baseline is the latest remote version in `repo-rag-training-families`.
- The trainer PVC is for temporary execution artifacts in the current Codex Exec / trainer run:
  - queued and imported trace files
  - the current in-flight `pending-cycle.json` ledger
  - one local mirror of the active remote family-index version
  - generated candidate/training surfaces for the current cycle
- Trainer must not treat a PVC-local family state as source-of-truth just because it already
  exists on disk.
- A smart local cache is allowed only when it is explicitly known to be a mirror of the same
  remote `family_state_version`.
- If the remote version changes, trainer must discard the active local family cache and adopt the
  new remote version.
- If no remote version exists, trainer starts from an empty local family cache and materializes the
  current cycle traces exactly once; it must not pre-seed a temporary family state from those same
  traces before the real candidate-materialization pass.
- Trainer recompiles only dirty families created or updated by the current queued traces. It does
  not reprocess every family on every cycle and it does not rebuild from `processed/...` as an
  active baseline path.

## Current Stage

This repository is still transitional.

Implemented locally in this stage:

- father-based prompt-family routing now uses `argmax` similarity and a single `0.8` gate
- prompt-lineage fields (`original_prompt`, `reformulated_prompt`, `command_trace`) now survive
  into the DSPy compile object instead of being dropped before `BootstrapFewShot` / `MIPROv2`
- bundle lineage can now point back to the family-state file that drove compilation
- proxy, trainer summaries, and remote family-state fetch/upload now prefer `family_state` naming
  while preserving `champion_*` aliases for live compatibility
- bundle drift detection now compares family-state lineage first and only falls back to
  `champion_*` lineage fields for older bundle manifests
- each published bundle now carries an internal `family_registry`, and the proxy now treats that
  registry as its primary family lookup source before falling back to the external family-state
  file
- trainer compilation now emits one family-scoped DSPy artifact per persisted family and records
  those artifacts in bundle metadata as `family_artifact_registry`
- successful family reuse now emits `full_trace` directly so matched runs always remain eligible
  for replay-driven family improvement
- the user contract now explicitly forbids trainer-side replay deduplication-by-comparison as the
  main control loop; if replay growth must be limited, that limit should be decided on the
  runtime/Codex Exec side instead
- remote bundle publish/fetch now includes family runtime `program.json` / `metadata.json` assets
  beside the global compiled program
- proxy DSPy execution now loads the matched family runtime artifact when available and invokes it
  with `original_prompt`, `reformulated_prompt`, and `command_trace` instead of collapsing runtime
  back to the global bundle program
- family state now tracks `family_needs_recompile`, trainer-side family artifacts are recompiled
  only for dirty families, and clean families carry their previous runtime artifact references
  forward into the next monolithic bundle
- incremental publish must preserve existing replay sidecars for clean carried-forward families;
  a thin materialized family payload is not allowed to erase historical `family_records`,
  `family_father_record`, or family runtime/champion anchors from the last compatible cached
  version
- the generated routing index is now `artifacts/trainer/family-index.sqlite3`; the older
  `family-state.json` is no longer written on the active path
- trainer pending-recompile detection now treats dirty-family flags as first-class recompile
  triggers instead of waiting only for lineage drift against the published bundle
- Azure remote family-state fetch/upload now treats `REPO_RAG_FAMILY_STATE_CONTAINER` /
  `repo-rag-training-families` as the primary contract, while legacy `champion_*` env vars,
  helper names, and older `champion-index.json` snapshots remain read-only compatibility inputs
- that remote family-state contract now also mirrors one `family.json` blob per prompt family under
  `versions/<family_state_version>/families/<prompt_family_id>/`, so the container already starts
  to look like family directories instead of one flat state object
- dataset / AKS deployment wiring now propagates `REPO_RAG_FAMILY_STATE_CONTAINER` /
  `DATASET_REPO_RAG_FAMILY_STATE_CONTAINER` through workflow env, generated storage secrets, and
  trainer deploy bootstrap, and those deploy/bootstrap surfaces no longer emit champion-named env
  aliases
- trainer now carries the latest compatible global DSPy program forward when the compile-facing
  training and benchmark example signatures still match the previous metadata, so even dirty-family
  cycles can skip the global compile when only family-local runtime artifacts changed
- family state now persists a first-class replay set under `family_records`, candidate
  materialization upserts each supported imported trace into that replay set, and dirty-family
  compilation consumes those replay records before falling back to runtime/father compatibility
  records
- the remote `repo-rag-training-families` mirror now writes one `family.json`, one `father.json`,
  and one `records/<snapshot>.json` payload per family, so the versioned family directory already
  contains the concrete replay objects that family-scoped `MIPROv2` is supposed to optimize
- the remote family-state machine contract is now versioned-only: `current.json` points at
  `versions/<family_state_version>/family-state.json`, and the per-family replay objects live only
  under `versions/<family_state_version>/families/<prompt_family_id>/...`; the earlier root-level
  `family-state.json` / `families/<id>/...` aliases were removed because they duplicated the same
  state without helping runtime resolution
- proxy family routing now also checks the validated family runtime-artifact `hit_rate` against the
  current family baseline and refuses to run a degraded family artifact, falling back to
  fresh/global mediation instead
- worker-side batch handoff for proxy turn traces now overwrites the optimistic proxy draft metrics
  and outcomes with the final run `execution_status`, `acceptance_status`, and real post-run
  `mediation_metric_hits / mediation_metric_total` before `trace-export` / `trace-enqueue`
- prompt-family routing now prefers `original_prompt` during father matching, while the
  reformulated prompt remains the runtime mediation surface that the matched family artifact sees
- deploy-stage trusted handoff now prefers the worker turn-trace batch manifest plus exported
  per-turn trace records before it falls back to the old coarse single-trace payload
- local trainer state now uses `artifacts/trainer/family-state.json` as the primary persisted
  filename, falls back to `artifacts/trainer/champion-index.json` only when older local snapshots
  have not been migrated yet, and caches remote family state under
  `artifacts/trainer/remote-family-state/`
- trainer-cycle diagnostics and pending-recompile reasons now describe the active state as
  `family-*` instead of `champion-*`, while mirrored alias fields remain available in machine
  payloads for compatibility
- dataset / AKS deploy/bootstrap surfaces now emit only family-state container env vars in their
  generated secrets and shell exports; repo-side readers can still accept champion-named env vars
  as compatibility fallbacks, but the deployment contract no longer publishes them
- repo-side Azure artifact config resolution now also ignores champion-named container env vars and
  resolves family-state storage only from family-state env names plus the family-first default
- remote family-state upload/fetch payloads now advertise only family-state fields; older
  `champion-index.json` snapshots remain readable for compatibility, but the active write path no
  longer republishes that mirrored file on disk or in blob storage
- newly written remote `current.json` family-state snapshots now also omit
  `champion_state_kind` and `current_champion_index_blob`; fallback reads for older snapshots are
  still preserved
- trainer-candidate summaries and pending-recompile payloads now emit family-state fields only;
  older `champion-index.json` snapshots can still seed the family state, but the active output
  path no longer mirrors that file on disk
- explicit `champion_*` Azure/blob wrapper helpers have now been removed from the repo API surface;
  compatibility continues through fallback reads instead of separate public champion-named helper
  functions
- trainer-side prompt-family assignment now treats each new imported trace as a temporary
  singleton family and matches it to existing families with one symmetric family-to-family score
  instead of the older asymmetric `question -> family` routing probe
- bundle activation now also falls back to the latest discoverable staged version directory when a
  local mirror exists but `channels/stable.json` or older published-manifest surfaces are missing
  or stale
- remote bundle fetch and AKS deploy-stage bundle staging now also fall back to the latest remote
  immutable bundle version when `channels/stable.json` is absent, and the staged worker mirror
  synthesizes a minimal local `channels/stable.json` pointer to that resolved version so execution
  pods can still activate the compiled family-first bundle
- the dataset worker now resolves bundle versions directly from the staged
  `.repo_rag_bundle_store` mirror before it depends on `bundle-inspect`, which reduces one more
  live failure mode where proxy startup knew the bundle root but never learned a concrete bundle
  version
- the live `codex exec` prompt body is now task-first and stripped of Discord channel metadata,
  forwarded tails, and attachment-dump noise; rich prompt metadata stays in artifacts instead of
  being sent to the model
- live trainer evidence now confirms that `repo-rag-training-families` is no longer empty once a
  trainer cycle completes: `current.json` points at a populated
  `versions/<family_state_version>/family-state.json`, per-family state lives under
  `versions/<family_state_version>/families/<prompt_family_id>/...`, and the trainer pod persists
  the same family-state snapshot locally under `artifacts/trainer/`
- trainer-side family materialization now sanitizes prompt lineage with the same rules as the
  execution-side proxy, stripping `Discord channel:`, `Messages with required reaction:`,
  `Repository checkout:`, `Attachment mount:`, and forwarded Discord tails before those values can
  become stored fathers or replay-set records
- trainer-cycle publish logic no longer injects an implicit `minimum_bundle_pass_rate = 1.0`
  whenever recompile/publish is requested; the family-first path now publishes unless an operator
  explicitly asks for a bundle gate
- trainer-side durable recovery now applies only to the current in-flight queue cycle through
  `artifacts/trainer/pending-cycle.json`; the active trainer baseline no longer replays
  `processed/...` into `artifacts/trainer/recovered-imported-traces/`
- worker-side `trace-export` now writes under the execution directory instead of the target
  repository root, so Codex no longer risks diffing or re-editing its own exported trace files
- AKS defaults now enable the existing resumed-lane rollover logic through
  `DATASET_CODEX_MAX_RESUMED_RUNS=9` and
  `DATASET_CODEX_PROMPT_TOKEN_GROWTH_RESET_RATIO=2.0`, so repeated verification reruns of one
  queue/slug lane do not keep compounding the same Codex transcript without bound
- local trainer state now follows a remote-baseline lifecycle:
  - trainer first resolves the latest remote `repo-rag-training-families` version
  - a PVC-local family cache may be reused only when metadata proves it already mirrors that same
    remote `family_state_version`
  - otherwise trainer refreshes the local mirror from remote before applying current `queued`
    traces
  - only when no remote family-state version exists at all may trainer bootstrap one transient
    local family state from the current queue cycle before publishing the first remote version
- `family-state.json` is now a thin index over the local family cache instead of a replay-buffer
  aggregate; full family payloads live under `artifacts/trainer/families/<prompt_family_id>/`
  (`family.json`, `father.json`, `records/*.json`), while the top-level index keeps only routing,
  dirty-flag, score, and path metadata

Not implemented yet:

- removal of all compatibility `champion-*` naming from repo and dataset wiring
- older local snapshots or tests can still enter through `champion-index.json`, but that file is
  now read-only migration input instead of an active mirrored state surface
- older global DSPy metadata that predates training/benchmark example signatures still forces one
  transitional full global compile before later dirty-family cycles can reuse the global object
- live AKS confirmation that the worker-side final turn-metric enrichment survives the full export
  and queue path
- live AKS confirmation that the staged bundle mirror plus synthesized family registry now activate
  the family runtime artifact without falling back to heuristic mediation

## Work Plan

1. Keep the old champion-named state only as compatibility alias, not as product truth.
2. Move trainer state from champion-first to family-first storage surfaces.
   Stage 2 locally: `family_state_path` and remote family-state wrappers now exist, but the
   underlying persisted filename and Azure container contract are still compatibility-backed.
3. Compile dirty families separately with `MIPROv2`.
4. Publish one bundle that carries the family registry and family runtime artifacts.
   Stage 4 locally: bundle upload/fetch now moves family runtime assets, and the proxy now
   executes the matched family artifact when it exists.
5. Split recompilation down to dirty families only instead of recompiling every family in one
   trainer run.
   Stage 5 locally: family state now marks dirty families, trainer compile reuses clean family
   runtime artifacts from the previous registry, and successful family compile clears the dirty
   flag back to `false`.
6. Move the remote family-state store to a family-first container contract while keeping champion
   compatibility aliases alive.
   Stage 6 locally: Azure config/fetch/upload now prefers `repo-rag-training-families` and
   `family-state.json`, but still mirrors `champion-index.json` and accepts old champion-named
   env vars during the migration.
7. Start mirroring each family into its own versioned blob directory inside the remote
   family-state container.
   Stage 7 locally: each remote family-state upload now also writes
   `versions/<family_state_version>/families/<prompt_family_id>/family.json`, and remote fetch
   reconstructs a matching local cache tree even when only the aggregate index is available.
8. Propagate the new family-state container contract through dataset / AKS deployment wiring.
   Stage 8 locally: workflow env, storage-secret generation, deploy bootstrap, `.env.example`, and
   generated deployment-script templates now export family-state container names as the primary
   contract and mirror champion aliases to the same container value.
9. Carry forward the global DSPy program when no dirty family requires a fresh compile.
   Stage 9 locally: if `dirty_family_count=0` and the latest global artifact matches the current
   training/benchmark/config surface, trainer copies the previous global `program.json` into the
   new run instead of recompiling it.
10. Promote family replay-set records to first-class trainer and remote-storage objects.
    Stage 10 locally: `family_records` now persists replay-set members in family state, family
    compile consumes that replay set, and the remote family-state mirror now writes
    `family.json`, `father.json`, and `records/<snapshot>.json` for every family.
11. Gate family runtime artifacts by measured family `hit_rate`, and overwrite proxy turn traces
    with the final run outcome before export.
    Stage 11 locally: proxy now rejects degraded family artifacts in favor of fresh/global
    mediation, and worker-side batch handoff rewrites per-turn trace metrics/outcomes from the
    final run result before `trace-export` / `trace-enqueue`.
12. Carry forward the global DSPy program across dirty-family cycles when the compile-facing merged
    dataset did not change.
    Stage 12 locally: global carry-forward now keys off persisted training/benchmark example
    signatures, so dirty-family cycles can skip the global compile once the previous metadata
    already recorded matching signatures for the same merged dataset.
13. Move the primary local trainer filename and cache path from champion naming to family-state
    naming while preserving compat aliases.
    Stage 13 locally: trainer materialization now writes `family-state.json` first, mirrors
    `champion-index.json`, remote fetch caches under `remote-family-state/`, and old local
    `champion-index.json` snapshots are still accepted as fallback read input.
14. Move operator-facing trainer diagnostics from champion wording to family wording.
    Stage 14 locally: pending-recompile reasons and trainer-cycle warnings now use
    `family-*` terminology as the primary operator contract, while mirrored `champion_*` payload
    fields remain for compatibility.
15. Remove champion-named env-var emission from dataset / AKS deploy surfaces.
    Stage 15 locally: generated repo-rag storage secrets, trainer deploy bootstrap, and generated
    deployment-script templates now emit only family-state container env vars, while repo-side
    runtime readers still accept champion env names as fallback inputs for older live
    environments.
16. Remove champion-named container env fallback from repo-side Azure config resolution.
    Stage 16 locally: `AzureArtifactConfig.from_env()` now resolves family-state storage from
    family-state env names only, ignoring champion-named container env vars even when they are
    still present in the environment.
17. Remove champion-named fields from remote family-state upload/fetch payloads.
    Stage 17 locally: remote family-state upload/fetch responses now emit only `family_state_*`
    fields, while still mirroring `champion-index.json` on disk and in blob storage for backward
    compatibility.
18. Remove champion-named fields from newly written remote `current.json` snapshots.
    Stage 18 locally: new `current.json` family-state blobs now record only family-state lineage
    fields, while fetch still accepts older `current_champion_index_blob` metadata during the
    transition.
19. Remove champion-named fields from trainer candidate / pending-recompile payloads.
    Stage 19 locally: `training-candidates` summaries, `trainer-candidates` command payloads, and
    pending-recompile summaries now publish only family-state fields, while older
    `champion-index.json` snapshots remain readable as migration input.
20. Remove no-longer-used public `champion_*` wrapper helpers.
    Stage 20 locally: champion-named Azure/blob helper wrappers and remote upload/fetch wrappers
    have been removed from the repo API surface because runtime code no longer calls them.
21. Remove active mirrored `champion-index.json` state from the family-first path.
    Stage 21 locally: trainer materialization, remote family-state upload/fetch, and proxy
    resolution now write and prefer only `family-state.json`; older `champion-index.json`
    snapshots remain readable as fallback input when the new family-state file is absent.
22. Close the remaining live runtime gaps found in AKS run `25629990035`.
    Stage 22 locally: proxy now strips forwarded Discord tails, synthesizes family registry
    support from `family-state.json` when bundle-local registry data is absent, resolves staged
    mirror `program.json` / `families/<id>/program.json` paths without requiring trainer-side
    artifact paths, and the deploy-stage trusted handoff now skips itself when the worker already
    completed a successful per-turn batch enqueue/import.
23. Close the remaining live runtime gaps found in AKS run `25632110510`.
    Stage 23 locally: proxy can now fall back to the latest staged bundle version even without
    channel metadata, the worker resolves bundle versions directly from the staged bundle mirror,
    the raw `codex exec` prompt is stripped down to the cleaned task plus concise repo/attachment
    hints, and the generated AKS env now enables resumed-lane reset thresholds by default.
24. Eliminate the stale submodule runtime-image path that kept live trainer pods on champion-era code.
    Stage 24 locally: `../dataset/build_and_push_images.sh` and
    `../dataset/deploy_repo_rag_trainer.sh` now prefer the sibling
    `../dspy_rag_in_repo_docs_and_impl1` checkout over the pinned submodule whenever both are
    available, and runtime lineage stripping now also removes `Repository checkout:` /
    `Attachment mount:` scaffolding so family matching compares only prompt content.
25. Align trainer-side family-state normalization and bundle publication policy with the
    family-first runtime contract.
    Stage 25 locally: trainer-side prompt-family materialization now strips the same dataset
    execution envelope from `question`, `original_prompt`, `reformulated_prompt`, and prompt-like
    `command_trace` fields that the execution proxy already strips, so stored `father.json`
    questions are mathematically comparable to the live runtime prompt. The trainer cycle also no
    longer auto-injects an implicit `minimum_bundle_pass_rate = 1.0`; bundle publication now
    proceeds by default unless an operator explicitly configures a bundle pass-rate threshold.
    Finally, worker-side `trace-export` now writes under `exec_dir` instead of the target repo
    worktree, keeping `artifacts/traces/...` out of user branches and reducing self-inflicted diff
    noise during Codex rollouts.
26. Prevent idle trainer-service cycles from minting repeated timestamped bundle versions.
    Stage 26 locally: trainer-cycle now treats stale `pending_recompile` as insufficient by
    itself; automatic recompile/publish requires current-cycle queue input, and processed-ledger
    recovery no longer augments or authorizes active trainer cycles.
27. Prevent `trainer-service` from entering `trainer-cycle` at all when queue input is absent.
    Stage 27 locally: the long-lived service now preflights queue visibility before every poll
    iteration. When the queue has no new trace input, the service records an idle state update and
    sleeps without invoking `trainer-cycle`, so the running poller no longer burns work just to
    rediscover an empty queue.
30. Enforce the user-requested queue-only trainer contract.
    Stage 30 locally: processed-ledger recovery is now diagnostic only. `recoverable_processed`
    counts still surface in status payloads, but they no longer trigger `current_cycle_input`
    detection and no longer contribute trace paths to active family materialization or family-local
    recompilation.
31. Make family-state itself sufficient for runtime family artifact execution, even when the
    published bundle container is missing or stale.
    Stage 31 locally: remote family-state uploads now carry
    `runtime-artifact/program.json` / `metadata.json` alongside `family.json`, `father.json`, and
    `records/...`, while remote family-state fetch rewrites `family_runtime_artifact` paths onto
    the local worker cache so a matched father can resolve a runnable DSPy family program without
    depending on `repo-rag-bundles`.
32. Remove shell-directory dependence from dataset-side repo-rag bundle staging.
    Stage 32 locally: the deploy-stage PVC sync helper is now resolved from the dataset repository
    root rather than from the current shell directory, so `cd aks_modules && ./deploy.sh` no
    longer disables `.repo_rag_bundle_store` staging by failing to find
    `tools/pvc_artifact_sync.sh`.
33. Bridge matched family lookups onto fetched family-state runtime artifacts when bundle-local
    family registries are stale, and surface the selected family/runtime metadata in exported
    trace records.
    Stage 33 locally: bundle-local family registries still win when they point at valid runnable
    family programs, but the proxy now lazily falls back to the fetched `family-state.json`
    runtime-artifact path when a matched family registry entry is stale. Trainer-facing exported
    trace records now also carry `prompt_family_id`, `prompt_family_similarity`,
    `family_artifact_selected`, `bundle_version`, `program_path`, and `mediation_metric_hits` /
    `mediation_metric_total` as top-level fields instead of hiding them only inside nested runtime
    trace payloads.
34. Turn `family-state.json` into the thin family index the user asked for.
    Stage 34 locally: persisted trainer state now writes the full family payloads to
    `artifacts/trainer/families/<prompt_family_id>/family.json` plus `father.json` and
    `records/*.json`, while top-level `family-state.json` stores only thin routing/index metadata
    and repo-relative paths into that per-family cache.
35. Redesign trainer cache/version preparation so one queue event yields one family-state update.
    Stage 35 locally: `trainer-cycle` now prepares one active local cache before touching current
    `queued` traces. It reuses an existing local cache when present, copies the latest remote
    family-state version into that cache when the local cache is absent, and only rebuilds from
    `processed` when neither local nor remote state exists. That from-scratch rebuild uses
    `upload_remote_state=False`, so it does not mint an intermediate remote version before the
    current queued traces are applied and dirty families are recompiled.
36. Make processed-ledger replay stable so one logical trace cannot duplicate itself on restore.
    Stage 36 locally: imported trace records now preserve the original queued-item identity, trainer
    snapshot IDs prefer that stable source token over the transient imported filename, and family
    replay upserts plus family-state hydration dedupe re-imported processed traces instead of
    counting them as new snapshots. Remote family-state uploads are also skipped when a cycle loads
    no accepted/candidate records, so empty no-op versions are no longer minted.
37. Preserve user-authored lines that follow forwarded Discord messages, and stop comparing family
    trace `hit_rate` against unrelated benchmark pass-rate fields.
    Stage 37 locally: prompt extraction in both the proxy and the dataset worker now removes only
    the forwarded-message line plus its attachment companion line, preserving later user-authored
    prompt lines verbatim in `original_prompt`, `reformulated_prompt`, and prompt-like
    `command_trace` entries. The runtime bridge now also interprets family artifact readiness using
    the persisted family trace `hit_rate` (metric 1) and keeps compile-time
    `benchmark_pass_rate` as diagnostics only, so an exact family match no longer drops into
    heuristic mode merely because the bundle carried a separate benchmark score.
38. Keep runtime DSPy on one proxy thread and stop exporting repeated same-prompt traces.
    Stage 38 locally: the local Codex proxy now serves requests on one dedicated HTTP server
    thread instead of a new request thread per turn, which keeps `dspy.settings.configure(...)`
    on one thread and removes the live thread-affinity fallback to heuristic mode. The same stage
    also suppresses trainer-facing trace export when family reuse already succeeded and dedupes
    repeated same-prompt snapshots within one rollout even when `command_trace` keeps growing.
28. Align runtime father matching and deploy-stage recovery with the family-first trace contract.
    Stage 28 locally: family lookup now routes by `original_prompt` instead of the helper's
    reformulated text, so existing fathers are compared against the raw task surface that the user
    asked to preserve. Deploy-stage trusted handoff now also treats the worker batch manifest plus
    exported per-turn trace records as the primary recovery path, and only falls back to the old
    coarse single-trace payload when no valid worker batch exists.
29. Keep deploy-stage postprocessing from aborting after a successful worker run.
    Stage 29 locally: the dataset deploy script no longer carries the malformed trusted-handoff
    helper line with an unmatched `)`, so one successful worker run can proceed from Redis result
    rehydration into Azure `execution-artifacts` upload instead of dying during Step 7.3b.
