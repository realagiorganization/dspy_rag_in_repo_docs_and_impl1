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

## Storage Contract

Target blob/container layout:

- `repo-rag-training-traces`
  - append-only raw turn traces, grouped by run/batch timestamp
- `repo-rag-training-families`
  - durable family state and replay sets
- `repo-rag-bundles`
  - published monolithic bundles with family registry inside

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
- remote bundle publish/fetch now includes family runtime `program.json` / `metadata.json` assets
  beside the global compiled program
- proxy DSPy execution now loads the matched family runtime artifact when available and invokes it
  with `original_prompt`, `reformulated_prompt`, and `command_trace` instead of collapsing runtime
  back to the global bundle program
- family state now tracks `family_needs_recompile`, trainer-side family artifacts are recompiled
  only for dirty families, and clean families carry their previous runtime artifact references
  forward into the next monolithic bundle
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
- trainer-side durable recovery is now incremental: `restore_processed_trace_records(...)` restores
  only processed queue blobs that have not already been mirrored into
  `artifacts/trainer/recovered-imported-traces/`, and `materialize_training_candidates(...)`
  treats `trace_paths=[]` as “process nothing new” instead of falling back to the full imported
  ledger
- worker-side `trace-export` now writes under the execution directory instead of the target
  repository root, so Codex no longer risks diffing or re-editing its own exported trace files
- AKS defaults now enable the existing resumed-lane rollover logic through
  `DATASET_CODEX_MAX_RESUMED_RUNS=3` and
  `DATASET_CODEX_PROMPT_TOKEN_GROWTH_RESET_RATIO=2.0`, so repeated verification reruns of one
  queue/slug lane do not keep compounding the same Codex transcript without bound

Not implemented yet:

- aggregate `family-state.json` is still the compatibility-backed source of truth beside the newer
  per-family `records/*.json` mirror
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
