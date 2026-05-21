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

## 2026-05-21 From-Scratch Live Cycle Verification

Live verification after deleting the previously published family-state and stable bundle showed the
expected from-scratch behavior.

Pre-cycle remote state:

- `repo-rag-training-families/current.json` was absent (`BlobNotFound`)
- `repo-rag-bundles/channels/stable.json` was absent (`BlobNotFound`)

Execution run `26216842933_20260521_093234`:

- `prompt_tokens = 37292`
- `total_tokens = 37292`
- `use_dspy_requested = true`
- `bundle_resolved = false`
- `dspy_status = skipped`
- `mediation_mode = passthrough`

This confirms the lower token count in that run was not caused by DSPy reuse. The run took a
shorter verify/no-op path on a repository that already contained the GIF generator, the GIF asset,
and the README embed, while the expensive fallback branch (`npm install` after `gifenc` missing)
failed fast on `ENOSPC`.

Trainer evidence for the same run:

- cycle `repo-rag-trainer-cycle-29655935` consumed the queued traces
- `remote_family_state_found = false`
- `current_bundle_version = null`
- `training-candidates-summary.json` reported:
  - `input_trace_count = 8`
  - `loaded_candidate_count = 8`
  - `candidate_count = 6`
  - `family_count = 6`
  - `new_prompt_family_count = 6`
  - `dirty_family_count = 6`
  - `duplicate_count = 0`
  - `replaced_count = 1`
  - `skipped_reasons = {}`
- `generated-training-summary.json` reported:
  - `base_example_count = 8`
  - `candidate_example_count = 6`
  - `combined_example_count = 14`
- trainer logs reached the real DSPy compile path, including:
  - `Bootstrapped 2 full traces after 3 examples for up to 1 rounds, amounting to 3 attempts.`

Published outputs:

- `repo-rag-training-families/current.json` now points to:
  - `current_version = 20260521T094218Z`
  - `current_family_count = 6`
  - `current_family_record_count = 8`
- `repo-rag-bundles/channels/stable.json` now points to:
  - `current_bundle_version = 20260521T093925087172Z`
  - `current_routing_index_path = artifacts/dspy/20260521T093925087172Z/routing-index.sqlite3`
  - `current_publish_status = published`
  - `current_family_state_version_used = null`

Status:

- runtime correctly skipped DSPy because no bundle existed yet
- trainer still entered a real from-scratch cycle and produced both:
  - a new family-state version
  - a new stable bundle carrying its own routing index

Verification executed in this turn:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Observed:

- `compileall` passed
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed as `62 passed`
- `uv run repo-rag smoke-test` passed
- `cargo build --manifest-path rust-cli/Cargo.toml` passed

Verification categories not exercised in this turn:

- `make quality`
- `make coverage`
- lint
- type checking
- notebook execution
- UI verification

## 2026-05-21 Published Bundle Verification For From-Scratch Cycle

Remote inspection of the first stable bundle published after the from-scratch trainer cycle shows
that the new bundle version `20260521T093925087172Z` is structurally usable as a runtime package.

Confirmed in blob:

- versioned bundle members exist:
  - `versions/20260521T093925087172Z/bundle.json`
  - `versions/20260521T093925087172Z/program.json`
  - `versions/20260521T093925087172Z/metadata.json`
  - `versions/20260521T093925087172Z/published.json`
  - `versions/20260521T093925087172Z/routing-index.sqlite3`
- all six family artifacts also exist:
  - `versions/20260521T093925087172Z/families/<prompt_family_id>/program.json`
  - `versions/20260521T093925087172Z/families/<prompt_family_id>/metadata.json`
- `channels/stable.json` points at:
  - `current_bundle_version = 20260521T093925087172Z`
  - `current_routing_index_path = artifacts/dspy/20260521T093925087172Z/routing-index.sqlite3`
  - `current_publish_status = published`

Bundle consistency:

- top-level `bundle.json` reports `family_count = 6`
- embedded `family_registry.family_count = 6`
- embedded `family_artifact_registry` also contains `6` families
- the copied `routing-index.sqlite3` contains the same `6` `prompt_family_id` values as the
  embedded `family_registry`

One structural debt remains:

- the copied routing index still carries `family_path` / `father_path` values such as
  `families/<id>/family.json` and `families/<id>/father.json`
- those sidecars are not currently published inside the bundle version; only
  `families/<id>/{program,metadata}.json` exist there

Current runtime status:

- this is not a hot-path blocker because bundle-local routing uses the thin SQLite fields plus the
  selected family program artifact, not the absent `family.json` / `father.json` members
- however, for a stricter notion of bundle autonomy, those stale family-state sidecar paths should
  eventually be removed from the copied routing index or satisfied by publishing the matching
  sidecars into the bundle

## 2026-05-21 Bundle Surface Compaction Follow-Up

The first autonomous bundle publish still carried more serialized weight than the runtime contract
required:

- `bundle.json` still inlined `family_artifact_registry`
- `bundle.json` and `metadata.json` both carried full benchmark `results`
- `published.json` stored `bundle_summary = <full bundle.json>`
- `channels/stable.json` stored `current_bundle = <full bundle.json>`
- the copied bundle-local `routing-index.sqlite3` still preserved `family_path` /
  `father_path` references to sidecars that do not exist inside `repo-rag-bundles`

Local repair:

- `bundle.json` now keeps only the runtime-facing bundle manifest, with compact benchmark and
  lineage summaries and no inline `family_artifact_registry`
- `metadata.json` now keeps compact benchmark summaries, compact lineage, and a compact
  `family_artifact_registry` suitable for carry-forward without per-case benchmark payloads
- `published.json` and `channels/stable.json` now persist only one compact bundle summary rather
  than a second full copy of `bundle.json`
- the copied bundle-local `routing-index.sqlite3` is now rebuilt as a stripped runtime index with
  `payload_json` entries and no `family_path` / `father_path` references

Local reconstruction against the live from-scratch bundle inputs projects the following size
reductions for the same published version shape:

- `bundle.json`: about `63 KB -> 16 KB`
- `metadata.json`: about `35 KB -> 8 KB`
- `published.json`: about `67 KB -> 3.5 KB`
- `channels/stable.json`: about `67 KB -> 3.9 KB`

The stripped bundle-local routing index now has only:

- `prompt_family_id`
- `payload_json`
- `family_record_count`

and one sample entry no longer carries `family_path` / `father_path`.

Verification executed in this follow-up:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_dspy_training.py tests/test_runtime_artifacts_azure.py tests/test_codex_proxy.py tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Observed:

- `compileall` passed
- targeted/local verification passed as `155 passed`
- smoke test passed
- Rust build passed

## 2026-05-21 Live From-Scratch Verification After Bundle Routing Copy

Latest verified execution run:

- `26221197956_20260521_110244`

Execution-side behavior matched the expected `from scratch` contract after deleting prior remote
family-state and stable bundle versions:

- `repo_rag_backend.json` reported:
  - `use_dspy_requested = true`
  - `bundle_resolved = false`
  - `bundle_version = null`
  - `dspy_status = skipped`
  - `mediation_mode = passthrough`
- `redis_results.json` reported:
  - `prompt_tokens = 21163`
  - `total_tokens = 21163`
  - `success = true`

This confirms the runtime did **not** reuse a prior DSPy bundle during the execution run.

Trainer-side publish completed successfully from scratch:

- `repo-rag-training-families/current.json` now points to:
  - `current_version = 20260521T111104Z`
  - `current_family_count = 5`
  - `current_family_record_count = 8`
- `repo-rag-bundles/channels/stable.json` now points to:
  - `current_bundle_version = 20260521T110641751838Z`
  - `current_routing_index_path = artifacts/dspy/20260521T110641751838Z/routing-index.sqlite3`
  - `current_family_state_version_used = null`
  - `current_publish_status = published`

The newly published family-state looks internally consistent:

- `family-index.sqlite3` contains `5` entries
- its `family_record_count` values sum to `8`
- the family ids are:
  - `pf-440eb981589fd25a`
  - `pf-b9d120cda6bd03f8`
  - `pf-c7c2e0a42d9d87ec`
  - `pf-dc1f706da0b4f060`
  - `pf-fbfd71330374ba41`

The newly published bundle now reflects the compact autonomous runtime contract in live storage:

- `bundle.json` size: `19189` bytes
- `metadata.json` size: `7216` bytes
- `program.json` size: `11567` bytes
- `published.json` size: `3454` bytes
- `routing-index.sqlite3` size: `36864` bytes

Live bundle shape verification:

- `bundle.json` still carries the runtime-facing `family_registry`
- `bundle.json` no longer carries inline `family_artifact_registry`
- `metadata.json` carries the compact `family_artifact_registry` used for trainer carry-forward
- `published.json` stores a compact `bundle_summary`
- the copied bundle-local `routing-index.sqlite3` now has only:
  - `prompt_family_id`
  - `payload_json`
  - `family_record_count`
- a sampled `payload_json` row no longer contains `family_path` or `father_path`

Conclusion for this live cycle:

- execution correctly ran without DSPy reuse
- trainer correctly entered a from-scratch cycle and published new `repo-rag-training-families`
  and `repo-rag-bundles` versions
- the newly published bundle is now compact and runtime-autonomous for routing

## 2026-05-21 Incremental No-Op After Missing Trace Export

Latest checked follow-up execution run:

- `26222834610_20260521_113707`

Observed outcome:

- `repo-rag-training-families/current.json` stayed at `20260521T111104Z`
- `repo-rag-bundles/channels/stable.json` stayed at `20260521T110641751838Z`
- trainer jobs `repo-rag-trainer-cycle-29656265`, `29656270`, and `29656275` all reported:
  - `queued_count_before = 0`
  - `drained_count = 0`
  - `current_cycle_input_detected = false`
  - `recompile_status = skipped-no-queued-input`
  - `pending_recompile.reason = bundle-matches-current-family-set`

This was not an incremental-training decision over fresh traces. It was a no-input trainer cycle.

Execution-side evidence explains why the queue stayed empty:

- `redis_results.json` for `26222834610_20260521_113707` reports a successful run with
  `prompt_tokens = 21163`
- the run includes only proxy bootstrap surfaces:
  - `repo_rag_codex_proxy_ready.json`
  - `repo_rag_codex_proxy_stderr.log`
- unlike the immediately previous successful from-scratch run
  `26221197956_20260521_110244`, this run does **not** include:
  - `repo_rag_backend.json`
  - `artifacts/traces/...`
  - trainer-facing `repo_rag_trace*` or `repo_rag_turn_trace*` exports

Blob state confirms that no new trainer input landed:

- the newest `repo-rag-training-traces/processed/...` objects still stop at the previous run's
  `20260521T110025Z ... 20260521T110117Z` batch
- no `processed/...` or `batches/...` objects were created for the `113707` execution

Execution transcript characteristics:

- the run completed as a repo verification/no-op path (`Already done in this checkout.`)
- `codex_response.txt` shows shell-only verification and no repo-RAG MCP usage
- `codex_restore_probe.json` shows a resume candidate existed but restore was reset because of
  `config-payload-mismatch`

Current diagnosis:

- the trainer did not fail to publish an incremental version after processing new traces
- the execution run failed to export any new trainer-facing traces at all
- the next debugging target is therefore the execution-side trace handoff path for this
  shell-only/no-op completion mode

Local repair for that execution-side failure:

- `dataset/docker/prompt-executor/worker_codex_cli_exec.py` no longer hard-codes a `15s`
  repo-rag proxy startup window
- the worker now uses a dedicated proxy startup timeout with a `45s` default and optional
  `DATASET_REPO_RAG_PROXY_STARTUP_TIMEOUT_SEC` override
- this is intended to prevent false fallback to direct `codex_cli` on cold or blob-backed
  proxy startup paths where the ready file appears later but the proxy itself is healthy

Local verification for this repair:

- `cd ../dataset && pytest tests/unit/test_worker_codex_cli_exec_small.py -q`
- `cd ../dataset && python -m compileall docker/prompt-executor`

Observed:

- targeted dataset unit coverage passed as `49 passed`
- new regression covers a delayed ready-file case that would previously have fallen back
  prematurely to direct Codex execution
- Python compileall over `docker/prompt-executor` passed

## 2026-05-21 Live Incremental Trainer In-Flight Verification

Latest checked execution run:

- `26237532287_20260521_162034`

Execution-side status for this run:

- `backend_used = codex_cli_repo_rag_proxy`
- `bundle_version = 20260521T110641751838Z`
- `trace_handoff_status = queued`
- `repo_rag_proxy_status.dspy_status = success`
- `repo_rag_proxy_status.prompt_family_id = pf-dc1f706da0b4f060`

This confirms the new run did not fall back to direct Codex execution; it reused the published
bundle-backed repo-rag proxy path and queued fresh traces for trainer ingestion.

Trainer live status while versions were still unchanged in blob:

- active job: `repo-rag-trainer-cycle-29656340`
- published versions had not yet moved at inspection time:
  - `repo-rag-training-families/current.json = 20260521T111104Z`
  - `repo-rag-bundles/channels/stable.json = 20260521T110641751838Z`

In-pod trainer state already shows a real incremental cycle in progress:

- `input_trace_count = 6`
- `loaded_candidate_count = 6`
- `candidate_count = 5`
- `family_count = 5`
- `dirty_family_count = 3`
- `new_candidate_count = 0`
- `duplicate_count = 0`
- `replaced_count = 0`
- `skipped_reasons = {}`

Generated-training state:

- `base_example_count = 8`
- `candidate_example_count = 5`
- `combined_example_count = 13`

The hydrated family-state inside the running pod already reflects incremental carry-forward:

- previous baseline records from `20260521T105752Z` are present
- new imported traces from `20260521T161515Z` are present alongside them
- current in-memory family counts are:
  - `pf-440eb981589fd25a = 1`
  - `pf-b9d120cda6bd03f8 = 1`
  - `pf-c7c2e0a42d9d87ec = 6`
  - `pf-dc1f706da0b4f060 = 4`
  - `pf-fbfd71330374ba41 = 2`

The active trainer log also reached DSPy compile:

- `Bootstrapped 2 full traces after 2 examples for up to 1 rounds, amounting to 2 attempts.`

Conclusion at inspection time:

- trainer is working
- it is running an incremental cycle, not a no-op cycle
- versions had not yet been published only because the active compile/publish job was still in
  flight

## 2026-05-21 Published Incremental Bundle Verification

After the in-flight cycle finished, blob pointers moved to:

- `repo-rag-training-families/current.json -> 20260521T162716Z`
- `repo-rag-bundles/channels/stable.json -> 20260521T162315360070Z`

Execution-side DSPy reuse for the triggering run `26237532287_20260521_162034` was real:

- `backend_used = codex_cli_repo_rag_proxy`
- `bundle_version = 20260521T110641751838Z`
- `trace_handoff_status = queued`
- `repo_rag_proxy_status.dspy_status = success`
- `repo_rag_proxy_status.prompt_family_id = pf-dc1f706da0b4f060`
- `repo_rag_proxy_status.prompt_family_similarity = 1.0`
- `repo_rag_proxy_status.family_artifact_selected = true`

So the execution reused the previously published stable bundle, then trainer produced the next
incremental family-state and next bundle generation from the queued traces.

Published bundle surface for `20260521T162315360070Z` remains compact:

- `bundle.json = 22913` bytes
- `metadata.json = 7345` bytes
- `program.json = 10816` bytes
- `published.json = 3579` bytes
- `routing-index.sqlite3 = 40960` bytes

The new bundle is mostly correct structurally:

- `bundle.json.family_count = 5`
- `metadata.json.family_artifact_registry` contains `5` families
- bundle-local routing index still has the stripped runtime schema:
  - `prompt_family_id`
  - `payload_json`
  - `family_record_count`
- payload rows still omit `family_path` / `father_path`

Two metadata defects remain in the published bundle:

1. `family_state_version_used` is still `null` in both:
   - `bundle.json`
   - `published.json`
   - `channels/stable.json`
   even though this bundle was generated from the newly published incremental family-state version
   `20260521T162716Z`.

2. The copied bundle-local `routing-index.sqlite3` has incorrect `family_record_count` values:
   - bundle index rows report `0` for all five families
   - the source family-state index for `20260521T162716Z` correctly reports:
     - `pf-440eb981589fd25a = 1`
     - `pf-b9d120cda6bd03f8 = 1`
     - `pf-c7c2e0a42d9d87ec = 6`
     - `pf-dc1f706da0b4f060 = 4`
     - `pf-fbfd71330374ba41 = 2`

Current assessment:

- DSPy reuse during the triggering execution run worked correctly
- the incremental trainer cycle completed and published new versions
- the new bundle is compact and likely still routable because `payload_json` remains intact
- but the published bundle is not fully correct yet because provenance and `family_record_count`
  metadata were zeroed/omitted during bundle-local routing-index generation

## 2026-05-21 Bundle Provenance And Routing-Count Repair

Local repair for the published-bundle defects above:

- `_bundle_family_entry(...)` now carries `family_record_count` forward into compact bundle family
  entries before the stripped bundle-local `routing-index.sqlite3` is written
- `run_trainer_cycle(...)` now publishes remote family-state before bundle publish and refreshes
  the local bundle metadata/manifest with the newly published `family_state_version`
- bundle publish therefore now sees the correct family-state provenance instead of serializing
  `family_state_version_used = null`

Verification executed in the current turn:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_runtime_artifacts_azure.py -q`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `uv run pytest tests/test_codex_proxy.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Observed:

- `compileall` passed
- `tests/test_runtime_artifacts_azure.py` passed as `28 passed`
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed as `63 passed`
- `tests/test_codex_proxy.py` passed as `29 passed`
- smoke test passed
- Rust build passed

## 2026-05-21 Live Incremental Bundle Verification After Provenance Repair

Latest checked execution run:

- `26241282193_20260521_173126`

Execution-side DSPy reuse for that run was real and used the previously published stable bundle:

- `repo_rag_backend.json` reported:
  - `backend = codex_cli_repo_rag_proxy`
  - `use_dspy_requested = true`
  - `bundle_resolved = true`
  - `bundle_version = 20260521T162315360070Z`
  - `dspy_status = success`
  - `mediation_mode = dspy_rag`
  - `trace_handoff_status = queued`
  - `trace_queued = true`
- `redis_results.json` reported:
  - `prompt_tokens = 42104`
  - `total_tokens = 42104`

That run then produced the next published versions:

- `repo-rag-training-families/current.json -> 20260521T173935Z`
- `repo-rag-bundles/channels/stable.json -> 20260521T173350406407Z`

The new bundle now carries the family-state provenance correctly:

- `channels/stable.json.current_family_state_version_used = 20260521T173935Z`
- `bundle.json.family_state_version_used = 20260521T173935Z`
- `published.json.family_state_version_used = 20260521T173935Z`
- `metadata.json.lineage.family_state_version = 20260521T173935Z`

The copied bundle-local routing index now preserves the same counts as the source family-state
index:

- `pf-440eb981589fd25a = 1`
- `pf-b9d120cda6bd03f8 = 1`
- `pf-c7c2e0a42d9d87ec = 10`
- `pf-dc1f706da0b4f060 = 6`
- `pf-fbfd71330374ba41 = 3`

These values match exactly between:

- `repo-rag-bundles/versions/20260521T173350406407Z/routing-index.sqlite3`
- `repo-rag-training-families/versions/20260521T173935Z/family-index.sqlite3`

The bundle-local routing payload remains stripped as intended:

- payload rows carry routing fields plus `family_record_count`
- payload rows do **not** carry `family_path`
- payload rows do **not** carry `father_path`

Observed bundle sizes for the new published version:

- `bundle.json = 27099` bytes
- `metadata.json = 7603` bytes
- `published.json = 3918` bytes
- `program.json = 10816` bytes
- `routing-index.sqlite3 = 45056` bytes

Status:

- the provenance repair is now reflected in live blob state
- the bundle-local routing index is both compact and count-correct
- the triggering execution run reused the previous stable DSPy bundle successfully
