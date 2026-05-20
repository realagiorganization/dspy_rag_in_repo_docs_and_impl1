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

- `compileall` passed
- `tests/test_training_samples.py` passed as `50 passed`
- targeted DSPy carry-forward regressions passed as `3 passed`
