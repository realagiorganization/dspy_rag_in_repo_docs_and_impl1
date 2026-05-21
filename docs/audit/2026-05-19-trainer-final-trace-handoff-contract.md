# Trainer Final Trace Handoff Contract

Date: `2026-05-19`

## Change

This note records the trainer-ingestion fix that followed the first successful live run after the
compact mediation and full-trace policy changes.

The bug was not in family routing or SQLite publishing alone. It was in the handoff boundary
between the prompt-executor and trainer, plus one trainer-side baseline bootstrap mistake:

1. the worker exported proxy turn-trace batches but then accidentally disabled batch queue/import
   handoff almost all the time
2. trainer ingestion still accepted raw `codex-proxy-turn-mediation` records as if they were
   normal execution traces
3. empty-baseline trainer cycles pre-seeded a local family cache from the current cycle traces
   before the real materialization pass
4. the enriched batch traces could still carry the proxy fallback answer
   `No father-backed prompt-family support was found ...`

That combination let proxy-turn drafts seed singleton families, and it made from-scratch library
formation depend on whether an older DSPy library already existed.

## What Changed

- prompt-executor now preserves the intended hierarchy:
  - enriched per-turn batch traces are the preferred trainer-ingestion surface
  - the final single execution trace is only a fallback when no usable batch exists or batch
    handoff fails
- the worker no longer disables batch queue/import handoff by default
- enriched batch traces are normalized out of `codex-proxy-turn-mediation` mode before trainer
  export so they remain valid execution-stage training traces
- enriched batch traces now inherit the final execution answer/evidence before queue handoff so
  from-scratch training does not consume proxy fallback summaries
- worker/backend summaries now reflect batch queue/import handoff correctly
- when no remote family baseline exists, trainer now starts from an empty local cache instead of
  materializing the current cycle traces twice
- trainer ingestion now rejects mediation-only records when either of these is true:
  - `source_command = codex-proxy-turn-mediation`
  - `trace.mode = codex-proxy-turn-mediation`
  - `source_command = codex-proxy-turn-execution` but the answer still equals the proxy fallback
    `No father-backed prompt-family support was found ...`

## Why

The product contract is that trainer behavior should be stable regardless of whether a previous
remote library already exists:

- if no version exists, trainer builds families from the final execution traces in the imported
  batch
- if a version exists, trainer loads that baseline and applies the same family assignment logic to
  the new final execution traces

That contract breaks if trainer sometimes sees real execution traces and sometimes sees
intermediary mediation turns. The family algorithm was behaving consistently; the input surface was
not.

The repaired invariant is therefore:

- append-only raw mediation traces remain useful for audit/debug/history
- enriched per-turn execution traces are the primary trainer-ingestion surface
- the final single execution trace is fallback-only
- mediation-only traces are never valid training exemplars
- empty-baseline and remote-baseline cycles now differ only in their starting family set, not in
  the class of traces considered valid for training

## Verification

Executed in the current turn:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_training_samples.py -q`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make quality`
- `cd ../dataset && pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py -q`

Observed:

- `compileall` passed
- `tests/test_training_samples.py` passed as `42 passed`
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed as `62 passed`
- smoke test passed
- Rust build passed
- dataset worker regression slice passed as `24 passed`
- `make quality` passed with:
  - `374 passed`
  - `3 skipped`
  - total coverage `81.57%`

## Scope Notes

- This note covers repository-local correctness of the worker-to-trainer trace boundary.
- Live AKS redeploy and a fresh trainer cycle are still required to prove the repaired invariant in
  blob-backed production state.

## 2026-05-20 Follow-Up

Live AKS verification on `2026-05-20` surfaced one more trainer-side compact-trace bug after the
new no-dup trace contract landed:

- the trainer drained all `7` queued traces successfully
- queue handoff and imported trace creation therefore worked
- but `materialize_training_candidates(...)` still read `question` only from the top-level imported
  trace payload
- compact imported traces now keep the canonical prompt surface inside nested `trace`, so the live
  cycle skipped all `7` imported traces as `missing-question`

Observed live symptoms:

- trainer cycle `repo-rag-trainer-cycle-29654540` completed technically successfully
- `queue_drain.drained_count = 7`
- `training_candidates.loaded_candidate_count = 0`
- `training_candidates.skipped_reasons = {"missing-question": 7}`
- the next trainer cycles were no-op because the queue had already been drained

Local repair:

- `_training_candidate_from_trace_record(...)` now derives the canonical routing question from
  `_trace_context_snapshot(...)`, which already understands compact nested trace ownership
- a regression test now covers imported trace records whose `question` exists only inside nested
  `trace`

Verification for this follow-up:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_training_samples.py -q`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`

Observed:

- `compileall` passed
- `tests/test_training_samples.py` passed as `47 passed`
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed as `62 passed`

## 2026-05-20 Live Status After Redeploy

After rebuilding and redeploying image `20260520-103514`, the live trainer progressed beyond the
previous `missing-question` failure mode:

- active cycle `repo-rag-trainer-cycle-29654595`
- running pod `repo-rag-trainer-cycle-29654595-8db5w`
- `training-candidates-summary.json` inside the pod shows:
  - `input_trace_count = 9`
  - `loaded_candidate_count = 9`
  - `candidate_count = 7`
  - `family_count = 7`
  - `skipped_reasons = {}`
- `generated-training-summary.json` shows:
  - `base_example_count = 8`
  - `candidate_example_count = 7`
  - `combined_example_count = 15`

This confirms the compact imported traces are now accepted by trainer materialization and no longer
collapse into `missing-question`.

However, the same live cycle had not finished publishing at the time of inspection:

- the job remained `Running`
- `fetch_remote_family_state(...)` still returned `None`
- `inspect_remote_bundle_channel('stable')` still returned `None`

The in-pod family surface also still looks suspiciously over-split:

- `7` families for `9` imported traces
- many singleton families whose fathers are micro-step helper prompts such as:
  - `I’ll inspect the repo shape first, then add the demo asset and README embed.`
  - `I found the asset and script; next I’m refreshing the GIF from the live wireframe.`
  - `The recorder needs dependencies present; I’m installing and rerunning once.`

So the live status is:

- trainer ingestion now works materially better than before
- the previous compact-trace `missing-question` bug is fixed
- but the end-to-end cycle was still in progress and the provisional family split remained more
  fragmented than the stage-level family contract intends

## 2026-05-20 Family-State No-Dup Follow-Up

Fresh blob inspection after the compact trace rollout showed that the trace envelopes had shrunk
substantially, but the published `repo-rag-training-families` SQLite index still carried one
legacy duplication surface:

- `family_index_entries` still persisted `question`, `normalized_question`, and
  `family_father_question` side by side even when all three reduced to the same routing question
- it also preserved `question_variant_count` in the hot index even though the count is derivable
  from canonical family payloads
- the compact local `family.json` files no longer inlined `family_father_record`, but remote
  publish still dropped `father.json` because it only uploaded inline father payloads

Local repair:

- the SQLite writer now stores one canonical `question` column for new family-index versions and
  keeps backward-read compatibility for older indexes
- legacy read paths now reconstruct `family_father_question` or `normalized_question` only when
  they carry information not already owned by `question`
- remote family-state publish now reloads `father.json` from the local sidecar when the compact
  `family.json` no longer inlines `family_father_record`

Verification for this follow-up:

- `uv run pytest tests/test_runtime_artifacts_azure.py -q`
- `uv run pytest tests/test_training_samples.py -q`

Observed:

- `tests/test_runtime_artifacts_azure.py` passed as `23 passed`
- `tests/test_training_samples.py` passed as `47 passed`

## 2026-05-20 Successful-Reuse Trace Suppression

Fresh blob inspection of execution `26163756050_20260520_131417` exposed one more runtime-side
contract regression:

- the run reported `prompt_tokens = 199227`
- trainer only saw `2` new processed traces from that run
- both traces were `full_trace` records for the same reused family and carried the same prompt
  snapshot
- the new version `20260520T131847Z` then published only those two records while carried-forward
  families lost replay history

Local reproduction isolated the root cause to the trace-generation boundary rather than the family
merge logic itself:

- applying the two imported traces manually onto the healthy baseline `20260520T123707Z`
  preserved the original `8` replay records and extended the family state to `10` total records
- therefore the merge and persist logic can preserve prior family history when it receives the
  expected imported traces
- the runtime bug was that successful DSPy family reuse short-circuited helper/lineage trace
  persistence, even though the repository contract requires every proxy prompt and every
  auxiliary/helper-LM prompt to remain a distinct trainer-visible trace

Local repair:

- `CodexProxyRuntime.persist_turn_trace(...)` no longer returns early when
  `family_artifact_selected=true` and `dspy_status=success`; lineage traces now persist under the
  same `full_trace` policy as other proxy prompts
- worker-side synthetic fallback batch seeding no longer skips turn-trace creation merely because a
  reused family artifact already succeeded

Verification for this follow-up:

- `uv run pytest tests/test_codex_proxy.py -q`
- `pytest ../dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py -q`

## 2026-05-20 Incremental Family-Attach Repair

Fresh blob inspection of the `20260520T145215Z` family-state version showed that trainer did start
from the prior remote baseline, but the published result was still not a correct incremental
continuation:

- trainer log reported `family_cache_preparation.status = using-remote-version-as-local-cache`
- the baseline source path pointed at the earlier remote version `20260520T123707Z`
- nevertheless carried-forward replay records disappeared from families such as
  `pf-dc1f706da0b4f060`, while several new singleton families appeared

Local analysis isolated two trainer-side bugs in the imported-trace attach path:

- `_training_candidate_from_trace_record(...)` recomputed `prompt_family_id` from the normalized
  question instead of preserving the runtime/exported family hint already present on the trace
- `_find_or_create_prompt_family(...)` ignored an already-existing `preferred_family_id` and fell
  back to similarity-based family creation, which could suffix new family ids instead of extending
  the carried-forward family

Local repair:

- imported trace candidates now preserve `payload.prompt_family_id` / `trace.prompt_family_id`
  whenever the runtime already selected a family
- trainer now treats an existing `preferred_family_id` as an attach target and extends that family
  directly instead of creating a new family merely because lexical similarity is low

Verification for this follow-up:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_training_samples.py -q`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`

Observed:

- `compileall` passed
- `tests/test_training_samples.py` passed as `50 passed`
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed as `62 passed`

## 2026-05-20 Bundle Carried-Forward Artifact Rebinding

Remote bundle inspection after the `20260520T144639227927Z` publish showed that the stable channel
did point at a genuinely new bundle version, but the new manifest still looked wrong for
carried-forward families:

- `channels/stable.json` promoted `20260520T144639227927Z`
- the versioned remote bundle blobs for that version existed
- but carried-forward `family_artifact_registry` entries such as `pf-a87005417d5640cf` and
  `pf-cf4cba34871dd9c2` still reported `artifact_dir`, `program_path`, and `metadata_path` under
  the earlier run `20260520T123257740415Z`

That did not mean the old version was overwritten. The remote publisher still uploaded fresh family
artifact blobs under the new version prefix. The bug was narrower:

- the carried-forward family artifact registry copied the previous run's local paths verbatim
- the new bundle manifest therefore looked like a pointer back into the old version even though the
  new versioned blobs existed

Local repair:

- family-scoped carried-forward artifacts now stage their `program.json` and `metadata.json` into
  the current run's family artifact directory
- the carried-forward registry payload is then rewritten to point at the current run's
  `artifact_dir`, `program_path`, and `metadata_path`
- bundle/family metadata still records `artifact_source = carried-forward`, but the paths now match
  the current bundle version instead of the previous run

Verification for this follow-up:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_training_samples.py -q`
- `uv run pytest tests/test_dspy_training.py -q -k 'recompiles_only_dirty_families or carries_forward_global_program_when_no_dirty_families or carries_forward_global_program_for_dirty_family_cycle'`

Observed:

## 2026-05-20 Incremental Replay Carry-Forward Contract

Fresh inspection of `repo-rag-training-families` version `20260520T165809Z` showed a narrower but
critical incremental-family bug. Trainer did use the previous remote version as baseline, but the
result was still not a valid append-only family-state update:

- `current.json` pointed at `20260520T165809Z`
- the previous family-state version in the container was `20260520T123707Z`
- both versions had the same four family ids, which confirmed that trainer started from the prior
  baseline rather than rebuilding from scratch
- however carried-forward replay records changed destructively inside existing families
- for example `pf-dc1f706da0b4f060` dropped from `5` replay records to `4`, and the surviving
  records were not the same five snapshots from the previous version

That behavior violates the intended contract:

- new family-state versions must be computed from the prior remote family-state baseline plus the
  current imported traces
- previous replay snapshots must remain present unless the incoming trace is literally the same
  snapshot identity
- later prompt-level traces from the same logical source are allowed to extend the family, but not
  to replace older carried-forward snapshots

Local repair:

- family replay upserts now key strictly on `exact_snapshot_id` (or the deterministic fallback
  snapshot reference when that field is absent)
- trainer-side family-state normalization also dedupes only by exact snapshot identity
- the older “logical replay” merge behavior no longer lets a later snapshot overwrite a prior
  snapshot merely because both share a stable source identity

Verification for this follow-up:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_training_samples.py -q`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Observed:

- `compileall` passed
- `tests/test_training_samples.py` passed with the new incremental carry-forward regression
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed
- `uv run repo-rag smoke-test` passed
- `cargo build --manifest-path rust-cli/Cargo.toml` passed

## 2026-05-20 Live Trainer Status Check

After redeploying the current `repo-rag-runtime` image, live AKS inspection showed trainer working
through a real queue-triggered cycle again instead of stalling on empty input:

- `repo-rag-trainer-cycle-29655050` drained `7` fresh imported traces
- the pod-local `training-candidates-summary.json` reported:
  - `input_trace_count = 7`
  - `loaded_candidate_count = 7`
  - `candidate_count = 4`
  - `family_count = 4`
  - `dirty_family_ids = ["pf-a87005417d5640cf", "pf-cf4cba34871dd9c2", "pf-d4d2ffa1a8f20d51", "pf-dc1f706da0b4f060"]`
- the pod-local `generated-training-summary.json` reported:
  - `base_example_count = 8`
  - `candidate_example_count = 4`
  - `combined_example_count = 12`

The same completed cycle then published and promoted new remote artifacts:

- family-state publish summary pointed at `versions/20260520T185724Z/family-index.sqlite3`
- stable bundle promotion advanced to `bundle_version = 20260520T185402016224Z`

The immediately following cycle `repo-rag-trainer-cycle-29655055` behaved as an expected no-op:

- `queued_count_before = 0`
- `drained_count = 0`
- `recompile_status = skipped-no-queued-input`
- `pending_recompile.reason = bundle-matches-current-family-set`
- `current_bundle_version = 20260520T185402016224Z`

This confirms the current live trainer posture:

- queue ingestion is active
- trainer can materialize candidates from imported traces
- publish/promotion complete without crashing
- the next scheduled cycle recognizes the freshly published bundle/family set and stays idle

## 2026-05-20 Incremental Baseline and Append-Only Replay Repair

Fresh live inspection of `repo-rag-training-families` after version `20260520T185724Z` showed a
deeper incremental bug than simple family-id drift:

- the published family ids stayed stable across `20260520T123707Z -> 20260520T185724Z`
- but the replay-set shrank from `8` snapshots to `7`
- `pf-dc1f706da0b4f060` dropped from `5` persisted snapshots to `4`
- trainer logs for the publish cycle showed it had hydrated its local cache from
  `20260520T123707Z`, so the loss happened during the new publish, not because the prior baseline
  was absent

Local analysis isolated two concrete failure modes:

1. the persist path only preserved carried-forward replay history when an incoming family payload
   was completely empty; if the in-memory payload was merely a reduced subset, older snapshots were
   overwritten instead of unioned append-only with the existing local baseline cache
2. remote family-state fetch trusted `current.json` too literally; if the pointer lagged behind a
   newer already-published `versions/*/family-index.sqlite3`, trainer could hydrate from an older
   baseline than the newest available remote family-state

Local repair:

- `_persist_local_family_state(...)` now merges existing cached replay records with the current
  in-memory family payload append-only by exact snapshot identity before writing `family.json`,
  `records/*.json`, and the thin SQLite index
- `fetch_remote_family_state(...)` now prefers the newest actually published
  `versions/*/family-index.sqlite3` over an older `current.json` pointer, while still returning
  `None` for a broken pointer when no newer published baseline exists

Verification for this follow-up:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_training_samples.py -q`
- `uv run pytest tests/test_runtime_artifacts_azure.py -q`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Observed:

- `compileall` passed
- `tests/test_training_samples.py` passed as `52 passed`
- `tests/test_runtime_artifacts_azure.py` passed as `24 passed`
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed as `62 passed`
- `uv run repo-rag smoke-test` passed
- `cargo build --manifest-path rust-cli/Cargo.toml` passed

## 2026-05-20 Compact Baseline Replay Hydration Repair

Another live regression still violated the incremental family-state contract even after the earlier
append-only merge repair:

- new versions kept the same prompt-family ids as the previous version
- but the replay-set still shrank
- the shrink happened even when no family ids changed and even when the cycle started from a
  valid remote baseline

The deeper root cause was that compact family-state sidecars were not being hydrated back into the
trainer cache correctly:

1. `fetch_remote_family_state(...)` downloaded `family.json` and `father.json`, but it only
   downloaded `records/*.json` when those replay records were already inlined inside the compact
   `family.json`
2. compact `family.json` intentionally omits inline `family_records`, so remote baseline fetch
   frequently cached zero replay records even though the blob container still held a full
   `records/*.json` replay-set
3. `_family_state_entry_to_payload(...)` and `_persist_local_family_state(...)` then trusted the
   thin `family.json` surface and did not reload replay records from local `records/*.json`
   sidecars when the inline `family_records` field was absent

That meant replay history could disappear before merge logic even ran: trainer loaded a compact
baseline family as if it contained only its father/runtime summaries, then republished that reduced
payload as the next remote version.

Local repair:

- `fetch_remote_family_state(...)` now enumerates and downloads remote
  `versions/<family_state_version>/families/<prompt_family_id>/records/*.json` blobs even when
  compact `family.json` does not inline replay records
- `_family_state_entry_to_payload(...)` now reloads local `records/*.json` sidecars whenever the
  compact `family.json` lacks inline `family_records`
- `_persist_local_family_state(...)` now also reloads existing local `records/*.json` sidecars
  before deciding whether the current in-memory family payload is a strict subset

This repairs the actual compact-sidecar baseline path that blob-backed trainer cycles use, instead
of only the inline-family-record path that earlier unit tests covered.

Verification for this follow-up:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_training_samples.py -q`
- `uv run pytest tests/test_runtime_artifacts_azure.py -q`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Observed:

- `compileall` passed
- `tests/test_training_samples.py` passed as `53 passed`
- `tests/test_runtime_artifacts_azure.py` passed as `25 passed`
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed as `62 passed`
- `uv run repo-rag smoke-test` passed
- `cargo build --manifest-path rust-cli/Cargo.toml` passed

## 2026-05-21 Remote Family-State Surface Verification

Blob verification against the current published family-state version `20260520T212024Z` confirmed
that the incremental replay history is now preserved, but the serialization contract is still only
partially satisfied.

Healthy surfaces:

- `current.json` reports `current_family_count = 4` and `current_family_record_count = 18`
- `family-index.sqlite3` loads successfully and exposes `4` entries whose
  `family_record_count` sum is also `18`
- the hot SQLite index no longer carries the old duplicate prompt columns:
  `normalized_question`, `family_father_question`, and `question_variant_count`
- each family still has its expected `records/*.json` sidecars plus runtime-artifact blobs under
  `versions/20260520T212024Z/families/<prompt_family_id>/...`

Remaining structural problem:

- each published `family.json` still inlines `family_records`
- each published `family.json` still inlines `family_father_record`
- each published `family.json` still inlines `family_runtime_artifact`
- those same payloads already exist as sidecars:
  `records/*.json`, `father.json`, and `runtime-artifact/{program,metadata}.json`

The result is that published `family.json` files remain much larger than the compact contract
allows, for example:

- `pf-a87005417d5640cf/family.json` ≈ `56 KB`
- `pf-cf4cba34871dd9c2/family.json` ≈ `35 KB`
- `pf-d4d2ffa1a8f20d51/family.json` ≈ `33 KB`
- `pf-dc1f706da0b4f060/family.json` ≈ `100 KB`

One subtle detail is working as designed:

- SQLite `family_path` / `father_path` members remain relative paths such as
  `families/<prompt_family_id>/family.json`
- those paths are resolved relative to the cached family-state root after
  `fetch_remote_family_state(...)` downloads the versioned blobs
- they are not intended to be direct blob names at the container root

Status:

- incremental carry-forward for replay records is now healthy
- the SQLite hot index is now compact enough to satisfy the no-dup prompt-column requirement
- published `family.json` sidecars still violate the stricter no-dup serialization contract and
  need one more compaction pass

## 2026-05-21 Bundle-Local Routing Index Verification

Local verification now covers the runtime split between trainer source-of-truth state and runtime
bundle autonomy.

Implemented:

- bundle publish now stages one copied `routing-index.sqlite3` beside every versioned bundle
- remote bundle upload now publishes that index as
  `versions/<bundle_version>/routing-index.sqlite3`
- fetched bundle caches now retain a local `routing_index_path`
- runtime proxy now resolves family matches from the bundle-local SQLite index before consulting
  `repo-rag-training-families`
- remote family artifacts are no longer downloaded eagerly just to route; the proxy now downloads
  only the selected `families/<id>/program.json` / `metadata.json` when those files are not
  already staged locally

Verified locally with:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_runtime_artifacts_azure.py tests/test_codex_proxy.py -q`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Observed:

- `tests/test_runtime_artifacts_azure.py tests/test_codex_proxy.py` passed as `56 passed`
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed as `62 passed`
- the new tests confirm:
  - remote bundle upload includes `routing-index.sqlite3`
  - remote bundle fetch can skip eager family artifact downloads while still staging the routing
    index
  - the proxy can route from a bundle-local SQLite index without touching fallback family-state
  - one selected family artifact can be fetched independently on demand

Status:

- `repo-rag-training-families` remains the trainer source of truth
- `repo-rag-bundles` is now materially closer to a self-sufficient runtime package
- runtime hot-path routing no longer depends on loading a monolithic bundle registry just to pick
  the family
