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

## 2026-05-22 Live Incremental Reuse Follow-Up

Live AKS inspection after execution batch `20260522T145958Z` confirmed two things at once:

- the incremental trainer cycle did finally create a new family when one imported `full_trace`
  stopped matching its hinted baseline family
- the execution run still was not a pure "all traces use the previous DSPy family artifact"
  scenario, because one helper trace fell back to baseline mediation even though the root path
  reused the prior stable bundle

Live evidence gathered:

- `kubectl get jobs -n repo-rag --sort-by=.metadata.creationTimestamp | tail -n 8`
- `kubectl exec -n repo-rag repo-rag-trainer-inspect -- sh -c 'cat /mnt/artifacts/dspy/channels/stable.json'`
- `kubectl exec -n repo-rag repo-rag-trainer-inspect -- sh -c 'sed -n "1,220p" /mnt/artifacts/traces/imported/20260522T150508Z-...-0.json'`
- `kubectl exec -n repo-rag repo-rag-trainer-inspect -- sh -c 'sed -n "1,220p" /mnt/artifacts/traces/imported/20260522T150509Z-...-1.json'`
- `kubectl exec -n repo-rag repo-rag-trainer-inspect -- sh -c 'sed -n "1,220p" /mnt/artifacts/traces/imported/20260522T150509Z-...-2.json'`
- `kubectl exec -n repo-rag repo-rag-trainer-inspect -- sh -c 'sed -n "1,260p" /mnt/artifacts/traces/imported/20260522T150510Z-...-3.json'`
- `kubectl logs -n repo-rag job/repo-rag-trainer-cycle-29657705`
- `kubectl cp repo-rag/repo-rag-trainer-inspect:/mnt/artifacts/trainer/family-index.sqlite3 /tmp/family-index-20260522.sqlite3`
- `sqlite3 -readonly /tmp/family-index-20260522.sqlite3 "select prompt_family_id, family_record_count, question from family_index_entries order by prompt_family_id;"`

Observed:

- new stable bundle version: `20260522T150755015462Z`
- `current_family_state_version_used = 20260522T151150Z`
- bundle lineage reported:
  - `imported_trace_count = 4`
  - `new_candidate_count = 1`
  - `dirty_family_count = 3`
  - `prompt_family_ids = 6`
- current family index now contains:
  - `pf-440eb981589fd25a | 1`
  - `pf-b9d120cda6bd03f8 | 1`
  - `pf-c7c2e0a42d9d87ec | 3`
  - `pf-dc1f706da0b4f060 | 6`
  - `pf-f4bcccb50d73c37a | 1`
  - `pf-fbfd71330374ba41 | 3`
- the new family is `pf-f4bcccb50d73c37a` with father:
  - `Quick repo check done — verifying exact files before I wrap up.`

Execution-side reuse evidence from imported traces:

- three imported traces carried the previous stable bundle version
  `20260521T222149380506Z`
- those same traces showed:
  - `program_loaded = true`
  - `family_artifact_selected = true`
  - `used_baseline_fallback = false`
  - `backend = codex_cli_repo_rag_proxy`
- one imported helper trace still showed mixed behavior:
  - `bundle_version = 20260521T222149380506Z`
  - `family_artifact_selected = true`
  - `program_loaded = false`
  - `used_baseline_fallback = true`
  - `prompt_family_similarity = 0.539112`
  - `prompt_family_band = new`

Interpretation:

- the root execution path did reuse the previous DSPy bundle; this is not a pure passthrough run
- incremental family formation also worked better than the prior broken state because it created
  one genuinely new family
- however, the reuse path is still not perfectly uniform across all helper traces, because at
  least one helper trace fell back to baseline mediation rather than loading the selected family
  program

## 2026-05-22 Live Prompt-Normalization Laziness Follow-Up

The later live execution batch `20260522T154337Z` against
`realagiorganization/landscaper-crm` exposed a different failure mode: the pipeline did create
new families, but the root task was normalized into repository review, pricing, and planning work
instead of directly beginning implementation on the site.

Live evidence gathered:

- `kubectl exec -n repo-rag repo-rag-trainer-inspect -- sh -c 'ls -1t /mnt/artifacts/traces/imported | head -n 12'`
- `kubectl cp repo-rag/repo-rag-trainer-inspect:/mnt/artifacts/traces/imported/20260522T155008Z-worker-0-prompts_tylers_landscaper-p00000-86c9e8-realagiorganization_landscaper-crm-20260522T154337Z-0.json /tmp/landscaper-latest/trace-0.json`
- `kubectl cp repo-rag/repo-rag-trainer-inspect:/mnt/artifacts/traces/imported/20260522T155009Z-worker-0-prompts_tylers_landscaper-p00000-86c9e8-realagiorganization_landscaper-crm-20260522T154337Z-1.json /tmp/landscaper-latest/trace-1.json`
- `kubectl cp repo-rag/repo-rag-trainer-inspect:/mnt/artifacts/traces/imported/20260522T155010Z-worker-0-prompts_tylers_landscaper-p00000-86c9e8-realagiorganization_landscaper-crm-20260522T154337Z-2.json /tmp/landscaper-latest/trace-2.json`
- `kubectl cp repo-rag/repo-rag-trainer-inspect:/mnt/artifacts/traces/imported/20260522T155010Z-worker-0-prompts_tylers_landscaper-p00000-86c9e8-realagiorganization_landscaper-crm-20260522T154337Z-3.json /tmp/landscaper-latest/trace-3.json`

Observed:

- the current stable bundle became `20260522T155334155226Z`
- trainer lineage shows:
  - `imported_trace_count = 11`
  - `new_candidate_count = 9`
  - `family_count = 15`
- so incremental family creation was active for this run
- however the root imported trace (`...-0.json`) had:
  - `original_prompt` beginning with a request for effort and pricing assessment:
    - `Please review ... and give me a plausible take on 1) how long ... 2) how much ...`
  - only later in the same user prompt came:
    - `You now have examples of how the site should look ... Start correcting the site according to the requirements`
  - `reformulated_prompt` then became:
    - `Review the repository ... and provide an implementation-grounded plan ...`
  - `program_loaded = false`
  - `family_artifact_selected = null`
  - `used_baseline_fallback = true`
- a secondary mediation trace (`...-1.json`) did reuse DSPy successfully:
  - `prompt_family_id = pf-dc1f706da0b4f060`
  - `prompt_family_similarity = 0.866789`
  - `program_loaded = true`
  - `family_artifact_selected = true`
  - `used_baseline_fallback = false`
- multiple additional helper traces then focused on assessment-style subgoals rather than direct
  implementation, for example:
  - pricing and timeline take
  - code maturity and deliverables assessment
  - route/script/deploy verification
  - existing form documentation review

Interpretation:

- DSPy reuse was real in this run, but not at the most important first/root trace
- the first/root trace fell back and preserved the earliest dominant asks from the raw user
  message: review the repo, estimate effort, and discuss pricing
- that fallback reformulation then seeded a chain of helper traces that were internally
  consistent, but “lazy” relative to the user’s later imperative to begin correcting the site
- so the pipeline’s laziness here was caused primarily by prompt-normalization priority, not by
  trainer family assignment alone

## 2026-05-22 Root Prompt Verbatim Contract Repair

The live `landscaper-crm` run showed that the execution path had a deeper runtime bug than family
reuse alone: the root prompt itself was allowed to pass through the helper reformulation path
before the first execution turn started. That violated the intended orchestration boundary and let
an early “review / pricing / timeline take” clause dominate over the later imperative to start
correcting the site.

Local repair:

- the root Codex prompt now stays verbatim through the proxy
- for the root prompt only:
  - `original_prompt == reformulated_prompt`
  - helper-LM prompt reformulation is disabled
  - the user prompt is no longer whitespace-collapsed into a compact mediation form before the
    first execution turn
- helper reformulation remains available only for later lineage/helper turns after the root prompt
  is already inside the standard proxy/orchestrator cycle

## 2026-05-24 Live Follow-Up: No Reformulation + Hard Reuse Gates

Local follow-up after the root-verbatim repair introduced two additional runtime changes:

- prompt reformulation is disabled for all prompt surfaces, not only the root prompt
- family reuse now requires hard eligibility on:
  - intent
  - constraint surface
  - command-pattern surface

Live verification after rebuilding and redeploying image `20260524-105717` used execution batch
`prompt-exec-1353735964635435100`, run directory
`/mnt/artifacts/runs/c2ddcdba4fb2400a9288f5428415628b`.

Evidence gathered:

- execution log:
  - `/mnt/artifacts/runs/c2ddcdba4fb2400a9288f5428415628b/execution_artifacts/prompt-worker-0-lt5lf/execution.log`
- execution-side backend summary:
  - `.../artifacts/prompts_tylers_landscaper-p00000-a8903b/repo_rag_backend.json`
- separated root developer-layer prompt:
  - `.../artifacts/prompts_tylers_landscaper-p00000-a8903b/repo_rag_root_developer_message.txt`
- imported traces:
  - `/mnt/artifacts/traces/imported/20260524T114009Z-...-0.json`
  - `/mnt/artifacts/traces/imported/20260524T114010Z-...-1.json`
  - `/mnt/artifacts/traces/imported/20260524T114013Z-...-6.json`
  - `/mnt/artifacts/traces/imported/20260524T114014Z-...-7.json`
- current stable bundle channel:
  - `/mnt/artifacts/dspy/channels/stable.json`

Observed:

- the run started as a fresh Codex execution, not a resumed rollout:
  - `Codex restore debug [startup]: status=fresh-no-snapshot`
  - `Codex restore debug [config-payload-mismatch]: status=reset:config-payload-mismatch`
- root-path repair still holds live:
  - root imported trace shows `prompt_family_id = null`
  - `program_loaded = false`
  - `family_artifact_selected = false`
  - `used_baseline_fallback = false`
  - `dspy_bypass_reason = root-prompt-never-uses-dspy`
  - `trace.original_prompt == trace.reformulated_prompt`
- helper traces also now preserve verbatim prompt lineage:
  - imported helper traces `...-1.json`, `...-6.json`, and `...-7.json` all showed
    `trace.original_prompt == trace.reformulated_prompt`
  - the helper questions were no longer rewritten copies of the mixed root prompt; instead they
    appeared as newly generated explicit tasks such as:
    - `I found prior work already covering the ask. Now I’m checking whether anything still needs code changes and making a tight call-prep deliverable.`
    - `The repo already has the form docs and demo pipeline. I’m packaging a clean “plausible take” note and verifying deploy hooks rather than rebuilding solved pieces.`
    - `I’m doing one small improvement: refreshing the call-prep note date and tightening the repo-state wording so it cleanly matches today’s handoff.`
- execution-side DSPy reuse was blocked for the run:
  - `repo_rag_backend.json` reported:
    - `bundle_resolved = false`
    - `bundle_version = null`
    - `dspy_status = skipped`
    - `mediation_mode = passthrough`
  - representative helper traces ended with:
    - `family_artifact_selected = false`
    - `used_baseline_fallback = true`
    - `prompt_family_band = new`
- user-visible behavior still remained assessment-first:
  - `codex_response.txt` still produced pricing / call-prep content
  - it refreshed `docs/CALL_PLAUSIBLE_TAKE.md` and `docs/REVIEW_PRICING_NOTE.md`
  - it explicitly said no substantive app changes were needed in that pass

Interpretation:

- the two requested runtime repairs did reach the cluster:
  - no prompt reformulation now holds for both root and helper turns
  - the harder routing eligibility checks prevented the old assessment family from being reused
    automatically for this run
- but the run still did not move into implementation-first behavior
- the remaining failure mode is now earlier than DSPy reuse:
  - the orchestrator itself is still generating assessment/call-prep helper tasks from the mixed
    prompt
  - those helper tasks are already explicit and verbatim, so this is no longer a prompt-rewrite
    bug
  - and because those helper tasks are context-mismatched, the new hard gates correctly skip DSPy
    reuse rather than fixing the task selection

Repository-local verification executed in the current turn:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Observed:

- `compileall` passed
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed as `63 passed`
- smoke test passed
- Rust build passed

Scope note:

- this live follow-up proves the no-reformulation and hard-gate changes landed in runtime
- it does not prove task-selection correctness, because the mixed prompt is still being decomposed
  into assessment-oriented helper tasks before any useful implementation branch begins

## 2026-05-24 Local Repair: Sticky Execution Mode

The next correction focuses on the remaining live failure mode after no-reformulation and hard
reuse gates landed: the run was still producing pricing / call-prep output because the root
developer layer was too soft and the proxy did not keep the root execution directive sticky across
the rest of the Codex rollout.

Local repair:

- the dataset-side root developer/system prompt now explicitly says:
  - once a concrete execution directive appears, the whole session stays in execution mode
  - pricing / timeline / call-prep / talk-track / repository-review subtasks are invalid as the
    main branch when implementation is also requested
  - documentation-only edits do not satisfy a site/app change request
  - the orchestrator must inspect named implementation surfaces before declaring the task already
    done
- the proxy runtime now derives one sticky execution guard from the first/root prompt and reuses
  that guard for every later request in the same Codex rollout
- even passthrough turns without family support now still receive that execution guard as a
  developer-layer instruction instead of running entirely unguided
- helper mediation blocks no longer repeat the current prompt line inside the developer message,
  which removes one more way to re-amplify an assessment-oriented internal subtask

Repository-local verification executed in the current turn:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_codex_proxy.py -q`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `cd ../dataset && pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/unit/test_worker_codex_cli_exec_small.py -q`
- `cd ../dataset && python -m compileall docker/prompt-executor/worker_execution.py docker/prompt-executor/worker_execution_prompt.py docker/prompt-executor/worker_codex_cli_exec.py`

Observed:

- repo `compileall` passed
- `tests/test_codex_proxy.py` passed
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed
- smoke test passed
- Rust build passed
- dataset repo-rag worker slices passed
- dataset compileall passed

Live redeploy and another fresh run are still required to prove that the sticky execution guard is
strong enough to stop the call-prep / pricing branch in blob-backed production state.
- the root developer-message injection no longer adds a truncated `Prompt:` mirror line, so the
  model sees the user prompt only in its original user-message position instead of through a second
  shortened proxy copy
- proxy mediation caches now distinguish root-prompt and helper-prompt entries so the root
  verbatim path cannot be polluted by helper-turn cache reuse

Verification for this repair:

- `uv run pytest tests/test_codex_proxy.py -q`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Observed:

- `tests/test_codex_proxy.py` passed as `30 passed`
- `compileall` passed
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed as `63 passed`
- smoke test passed
- Rust build passed

Scope note:

- this turn fixed the local proxy/orchestrator contract and added a regression for verbatim root
  prompt handling
- blob-backed live verification is still required to prove that the next real execution run no
  longer normalizes the root prompt into a planning/assessment-first task

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
- trainer preserves the runtime `preferred_family_id` as a `full_trace` routing hint, but not as a
  hard attach override
  - if the hinted family still matches by the normal threshold, trainer extends it
  - if the hinted family no longer matches, trainer must still be able to create a new family
  - only `feedback_trace` binds directly to the hinted family without a new similarity decision

Verification for this follow-up:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_training_samples.py -q`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`

Observed:

- `compileall` passed
- `tests/test_training_samples.py` passed as `50 passed`
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed as `62 passed`

## 2026-05-21 Incremental New-Family Creation Follow-Up

Later live inspection of the `from scratch` family-state version `20260521T111104Z` and the
incremental family-state version `20260521T173935Z` showed a suspicious pattern:

- the family id set stayed exactly the same across both versions
- only `family_record_count` changed (`1,1,3,2,1` became `1,1,10,6,3`)
- no new prompt families appeared at all during later incremental runs

That pattern alone is not always wrong, but the code path confirmed a real trainer bug:

- imported `full_trace` records preserved the runtime `prompt_family_id` hint correctly
- `_find_or_create_prompt_family(...)` then treated that hinted id as an unconditional attach
  target whenever the family already existed
- so a later incremental cycle could never create a new family from a hinted `full_trace`, even
  when the new trace had drifted far enough away that the normal family-similarity threshold would
  have rejected the old family

Local repair:

- `preferred_family_id` is now a soft hint for `full_trace`
  - if the hinted family still matches by the normal family threshold, trainer extends it
  - if it no longer matches, trainer falls back to normal family search and may create a new
    family
- `feedback_trace` remains the only record class that binds directly to the hinted family without
  a new similarity decision
- regression coverage now includes both sides of the contract:
  - hinted `full_trace` that still matches the old family
  - hinted `full_trace` that must create a new family instead

Verification for this follow-up:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_training_samples.py -q`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Observed:

- `compileall` passed
- `tests/test_training_samples.py` passed as `54 passed`
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed as `63 passed`
- smoke test passed
- Rust build passed

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

## 2026-05-22 Live Root-Verbatim Follow-Up

Latest checked execution run:

- `26302660255_20260522_180011`

This run was inspected after the root-prompt verbatim contract repair. The goal was to determine
whether the pipeline still drifted into repository assessment/planning instead of directly
continuing site implementation.

Live evidence gathered:

- `az storage blob list --account-name realagistorage --container-name execution-artifacts --prefix executions/ --query 'reverse(sort_by([?ends_with(name, \`redis_results.json\`)], &properties.lastModified))[:8]'`
- `az storage blob download --account-name realagistorage --container-name execution-artifacts --name executions/26302660255_20260522_180011/redis_results.json`
- `az storage blob download --account-name realagistorage --container-name execution-artifacts --name executions/26302660255_20260522_180011/all_artifacts.tar.gz`
- `kubectl cp repo-rag/repo-rag-trainer-inspect:/mnt/artifacts/traces/imported/20260522T180008Z-...-0.json /tmp/landscaper-latest-174814/trace-0.json`
- `kubectl cp repo-rag/repo-rag-trainer-inspect:/mnt/artifacts/traces/imported/20260522T180009Z-...-1.json /tmp/landscaper-latest-174814/trace-1.json`
- `kubectl cp repo-rag/repo-rag-trainer-inspect:/mnt/artifacts/traces/imported/20260522T180010Z-...-2.json /tmp/landscaper-latest-174814/trace-2.json`
- `kubectl cp repo-rag/repo-rag-trainer-inspect:/mnt/artifacts/traces/imported/20260522T180010Z-...-3.json /tmp/landscaper-latest-174814/trace-3.json`
- `kubectl exec -n repo-rag repo-rag-trainer-inspect -- sh -lc 'cat /mnt/artifacts/dspy/channels/stable.json'`
- `kubectl exec -n repo-rag repo-rag-trainer-cycle-29657880-7ntvz -- sh -lc 'sed -n "1,220p" /workspace/repo-rag/artifacts/trainer/training-candidates-summary.json'`

Observed execution-side behavior:

- `repo_rag_backend.json` reported:
  - `backend = codex_cli_repo_rag_proxy`
  - `bundle_resolved = true`
  - `bundle_version = 20260522T172801104492Z`
  - `dspy_status = success`
  - `mediation_mode = dspy_rag`
  - `trace_handoff_status = queued`
- `redis_results.json` reported:
  - `prompt_tokens = 132003`
  - `artifacts/traces/...-0.json` through `...-7.json` were all exported

Most important root-trace finding:

- `trace-0.json` now satisfies the repaired root contract:
  - `trace.original_prompt == trace.reformulated_prompt`
  - `trace.program_loaded = true`
  - `trace.family_artifact_selected = true`
  - `outcome.used_baseline_fallback = false`
  - `trace.prompt_family_id = pf-4debe1f147146967`
  - `trace.prompt_family_similarity = 1.0`

That means the previous bug is fixed:

- the root prompt was **not** helper-rewritten
- the root trace did **not** fall back to baseline mediation
- the root trace did reuse a previously published DSPy family artifact

However, the run still behaved as assessment-first rather than implementation-first, and the
reason changed:

- the verbatim root prompt itself still begins with:
  - `Please review ... give me a plausible take on`
  - `1) how long ...`
  - `2) how much ...`
- the later implementation clause
  - `You now have examples of how the site should look ... Start correcting the site according to the requirements`
  remains present, but it appears too late to dominate the root task semantics
- because the root prompt is now passed through verbatim, DSPy matched it exactly to an existing
  assessment-oriented family and returned an assessment-style answer:
  - timing estimate
  - pricing estimate
  - risk / pitch framing
  - optional memo follow-up

Helper traces still reformulated normally and several of them remained planning-style:

- `trace-1.json` rewrote the same client prompt into an explicit
  `estimate/triage/pricing` mediation query
- `trace-3.json` through `trace-6.json` were still repo-review / validation / summary helper turns
  rather than implementation-start turns

So the live interpretation is now:

- the root-verbatim repair worked technically
- the current lazy behavior is no longer caused by helper rewriting of the root prompt
- it is caused by the mixed-intent user prompt itself plus exact DSPy reuse of the already learned
  assessment-family `pf-4debe1f147146967`

Trainer status at inspection time:

- latest published versions were still the previous cycle:
  - `repo-rag-training-families/current.json -> 20260522T173601Z`
  - `repo-rag-bundles/channels/stable.json -> 20260522T172801104492Z`
- a newer trainer job was still running:
  - `repo-rag-trainer-cycle-29657880`
- its in-pod `training-candidates-summary.json` already showed:
  - `input_trace_count = 8`
  - `loaded_candidate_count = 8`
  - `new_candidate_count = 3`
  - `family_count = 19`

So incremental family creation still appears alive, but the freshly imported traces are currently
teaching mostly assessment / review patterns rather than implementation-start behavior.

## 2026-05-22 Root Prompt Never Uses DSPy Repair

The next local runtime correction tightened the root-turn contract one step further. The earlier
root-verbatim repair stopped helper LM rewriting of the first prompt, but live evidence showed that
the root prompt could still match an already-published assessment-oriented DSPy family artifact and
therefore continue steering the run into review / pricing / effort-estimate behavior. That is not
allowed by the intended orchestration contract.

The repaired invariant is now:

- the root prompt still passes through the local proxy
- the root prompt still produces a normal trainer-facing trace after execution
- but the root prompt never performs family routing and never loads a DSPy family artifact
- DSPy family routing is reserved only for later helper / derived turns after the orchestrator has
  already started the run

Local code changes:

- `build_codex_mediation(..., root_prompt=True)` now returns an intentional root passthrough result
  before any family lookup, repo retrieval, or DSPy program load
- that result carries:
  - `original_prompt == reformulated_prompt`
  - `dspy_status = skipped`
  - `dspy_bypass_reason = root-prompt-never-uses-dspy`
  - `family_artifact_selected = false`
  - no injected mediation block
- cached root results now preserve `dspy_bypass_reason`
- turn-trace outcomes now distinguish intentional root DSPy bypass from real baseline fallback, so
  root traces no longer appear as accidental DSPy failures

Verification executed in this turn:

- `uv run pytest tests/test_codex_proxy.py -q`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Observed:

- `tests/test_codex_proxy.py` passed as `31 passed`
- `compileall` passed
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed as `63 passed`
- smoke test passed
- Rust build passed

Verification categories still not exercised in this turn:

- no full `make quality`
- no coverage run
- no UI/browser integration run
- no live AKS redeploy yet for this exact root-no-DSPy repair

## 2026-05-22 Live Result After Root-No-DSPy Redeploy

Live AKS inspection after execution batch `26306410579_20260522_191720` confirmed that the
root-no-DSPy repair itself now works in production, but it also exposed the next orchestration
problem clearly: helper-turn generation is still steering the run into estimate / review behavior.

Live evidence gathered:

- downloaded:
  - `execution-artifacts/executions/26306410579_20260522_191720/redis_results.json`
  - `execution-artifacts/executions/26306410579_20260522_191720/all_artifacts.tar.gz`
- inspected:
  - `repo_rag_backend.json`
  - `execution.log`
  - imported traces for batch `20260522T191020Z` copied from the trainer PVC
  - `repo-rag-bundles/channels/stable.json`

Observed for the root trace `trace-0.json`:

- `trace.original_prompt == trace.reformulated_prompt`
- `prompt_family_id = null`
- `prompt_family_similarity = 0.0`
- `program_loaded = false`
- `family_artifact_selected = false`
- `used_baseline_fallback = false`
- `dspy_bypass_reason = root-prompt-never-uses-dspy`

This is the intended contract:

- the root prompt stayed verbatim
- the root prompt did not family-match
- the root prompt did not load a DSPy family artifact
- the root prompt still produced a normal imported trainer trace

Execution-level backend summary agreed:

- `backend = codex_cli_repo_rag_proxy`
- `bundle_resolved = false`
- `bundle_version = null`
- `dspy_status = skipped`
- `mediation_mode = passthrough`
- `trace_handoff_status = queued`

So the earlier defect is fixed: the root prompt is no longer being templated by DSPy.

However, the helper-turn surface still pushed the run toward estimation:

- `trace-1.json` immediately reformulated into a repository-grounded
  `Review and continue implementing ...` helper prompt but then matched the old assessment family
  `pf-4debe1f147146967` with:
  - `program_loaded = true`
  - `family_artifact_selected = true`
  - `used_baseline_fallback = false`
- later helper traces explicitly asked for:
  - client-facing estimate drafting
  - deployment-readiness assessment
  - pricing take
  - realistic effort estimate
- sampled answers from `trace-0`, `trace-1`, `trace-3`, `trace-7`, and `trace-8` all began with
  `**Plausible Take**`

Interpretation:

- the root-no-DSPy repair is working live
- the run is still becoming assessment-first, but now for a different reason
- the current failure is no longer root prompt templating
- it is helper-task spawning / intent prioritization after the root prompt enters the
  orchestrator

This means the next fix must target helper orchestration:

- mixed-intent prompts with an explicit implementation clause cannot immediately spawn pricing /
  timeline / triage helper tasks as the dominant next step
- estimate-style sidecar work must be demoted behind implementation-first execution when the user
  explicitly says to start correcting the site

## 2026-05-22 Root Developer-Layer Injection Repair

The next local repair moved the runtime execution contract out of the concatenated user prompt and
into the correct higher-priority developer instruction layer for root Codex requests.

Why this was necessary:

- `dataset` had been building one flat prompt by concatenating:
  - the user task
  - execution context
  - autonomous execution contract
- that flattening meant the root task and the system rules were traveling in the same user text
  blob
- the local proxy already knew how to inject a separate `developer` message for helper mediation,
  but the root path still left `developer_message=""` and therefore never used that channel

Repaired invariant:

- the root user prompt stays verbatim and uncompressed
- the root execution contract is sent separately as a `developer` message in the Responses payload
- the same system rules are therefore no longer duplicated inside the root user prompt
- the root instruction layer now explicitly says that concrete action directives (`develop`,
  `implement`, `fix`, `correct`, `update`, `create`, `change`, `make`) must be executed in the
  current run rather than reduced to estimate/pricing/review output

Local code changes:

- `dataset/docker/prompt-executor/worker_execution.py`
  - split the execution contract into `_build_execution_system_prompt(...)`
  - kept `_build_final_prompt(...)` only as the direct-Codex fallback surface
- `dataset/docker/prompt-executor/worker_execution_prompt.py`
  - root proxy specs now carry `root_developer_message`
  - Codex proxy path now sends only the cleaned runtime user prompt, not the concatenated system
    contract blob
- `dataset/docker/prompt-executor/worker_codex_cli_exec.py`
  - proxy sessions now persist `repo_rag_root_developer_message.txt`
  - `serve-codex-proxy` receives that file via explicit CLI argument
- `src/repo_rag_lab/codex_proxy.py`
  - root mediation now returns `developer_message=root_developer_message`
  - root requests inject that text as a separate `developer` message while still bypassing DSPy
- `src/repo_rag_lab/cli.py`
  - `serve-codex-proxy` now accepts `--root-developer-message-file`

Verification executed in this turn:

- `uv run pytest -q tests/test_codex_proxy.py::test_build_codex_mediation_keeps_root_prompt_verbatim tests/test_codex_proxy.py::test_persist_turn_trace_marks_root_bypass_as_not_fallback`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `cd ../dataset && python -m compileall docker/prompt-executor/worker_execution.py docker/prompt-executor/worker_execution_prompt.py docker/prompt-executor/worker_codex_cli_exec.py`
- `cd ../dataset && pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/unit/test_worker_codex_cli_exec_small.py -q`

Observed:

- targeted `tests/test_codex_proxy.py` root-path slice passed as `2 passed`
- `compileall` passed
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed
- smoke test passed
- Rust build passed
- dataset worker `compileall` passed
- the targeted `dataset` proxy-spec / proxy-session regression slice passed as `74 passed`

Verification categories still not exercised in this turn:

- no full `make quality`
- no coverage run
- no live AKS redeploy yet for this exact root developer-layer injection repair

## 2026-05-24 Live Result After Root Developer-Layer Separation

Live inspection of the newer `prompts_tylers_landscaper` execution run showed that the root
developer-layer separation repair is now working, but the overall run still stays lazy for two
other reasons:

1. later repeat cycles continue prior Codex rollout state
2. helper traces still reinterpret the mixed prompt into pricing/review/verification families

Live evidence gathered:

- `kubectl get jobs -A --sort-by=.metadata.creationTimestamp`
- `kubectl describe job -n prompt-exec-1353735964635435100 prompt-worker-0`
- `kubectl run artifact-inspect -n prompt-exec-1353735964635435100 ...`
- `kubectl exec -n prompt-exec-1353735964635435100 artifact-inspect -- sh -c 'df -h /mnt/artifacts /mnt/cache'`
- `kubectl cp prompt-exec-1353735964635435100/artifact-inspect:/mnt/artifacts/runs/2bb963e8046843e29ed3cdcfe10e772c/... /tmp/landscaper-runs/...`
- `kubectl run live-inspect -n repo-rag ...`
- `kubectl exec -n repo-rag live-inspect -- sh -c 'cat /mnt/artifacts/dspy/channels/stable.json'`
- `kubectl exec -n repo-rag live-inspect -- sh -c 'sed -n "1,260p" /mnt/artifacts/traces/imported/...r10...-0.json'`
- `kubectl exec -n repo-rag live-inspect -- sh -c 'sed -n "1,220p" /mnt/artifacts/traces/imported/...r10...-1.json'`
- `kubectl exec -n repo-rag live-inspect -- sh -c 'sed -n "1,220p" /mnt/artifacts/traces/imported/...r10...-7.json'`
- `kubectl exec -n repo-rag live-inspect -- sh -c 'sed -n "1,220p" /mnt/artifacts/traces/imported/...r10...-10.json'`

Observed root-path results:

- the worker now stores a separate root instruction file:
  - `repo_rag_root_developer_message.txt`
- the persisted prompt artifact for `r10` still contains only the user/Discord bundle, not the
  autonomous execution contract text
- imported root trace
  `20260523T210243Z-worker-0-prompts_tylers_landscaper-p00000-bcb735-r10-...-0.json` shows:
  - `original_prompt == reformulated_prompt`
  - `prompt_family_id = null`
  - `program_loaded = false`
  - `family_artifact_selected = false`
  - `used_baseline_fallback = false`
  - `dspy_bypass_reason = root-prompt-never-uses-dspy`

This confirms the intended root contract now holds in live AKS:

- root prompt is no longer rewritten
- root prompt no longer uses DSPy
- root trace is still exported as a normal trainer-facing trace
- the developer/system layer is no longer duplicated into the user prompt body

However, the same run still stayed lazy because the later turns did not follow the root action
directive:

- the prompt bundle still begins with the older:
  - `Please review ...`
  - `give me a plausible take ...`
  - `how long ...`
  - `how much ...`
- only much later does it say:
  - `Start correcting the site according to the requirements`
  - `No analysis is needed, start fixing the site right now`

Helper-trace observations:

- imported helper trace `...r10...-1.json` was reformulated into a planning/estimation query:
  - `Review the repository ... and use it to ground a planning/estimation response ...`
  - `program_loaded = true`
  - `family_artifact_selected = true`
  - `prompt_family_id = pf-4debe1f147146967`
  - `prompt_family_similarity = 1.0`
- later helper traces `...r10...-7.json` and `...r10...-10.json` pivoted into disk-space
  bootstrap troubleshooting:
  - answer: `Build validation hit a disk-space blocker during pnpm bootstrap ...`
  - `program_loaded = false`
  - `family_artifact_selected = false`
  - `used_baseline_fallback = true`
  - new helper families such as `pf-47f24bec7c9d2d25` and `pf-5e7e293c10eb60df`

Session-resume observations:

- this execution namespace processed the same prompt through repeated cycles:
  - prompt artifact shows `Run 10 of 10`
  - execution log reports `Processed 10 prompts (10 successful)`
- cycle `r09` was a fresh `codex exec` because restore reset on usage-growth-threshold:
  - `restore_status = reset:usage-growth-threshold`
  - `restored_files = 0`
  - command: `codex exec --dangerously-bypass-approvals-and-sandbox ...`
- cycle `r10` did resume the previous rollout:
  - `restore_status = restored`
  - `restored_files = 8`
  - `latest_session_id = rollout-2026-05-23T20-18-59-019e567d-b370-7db1-aa0a-5c76eafd52db`
  - command: `codex exec resume rollout-2026-05-23T20-18-59-019e567d-b370-7db1-aa0a-5c76eafd52db ...`

Interpretation:

- root developer-layer separation is working
- root no-DSPy is working
- but later repeated cycles can still continue an assessment-heavy prior rollout
- even without resume (`r09`), the mixed prompt still led the model into pricing/call-prep mode
- therefore session continuation amplifies the problem, but it is not the only cause

Disk-space observations:

- the Azure File PVCs were not full:
  - `/mnt/artifacts`: `5.0G size`, `89.4M used`, `4.9G available`
  - `/mnt/cache`: `10.0G size`, `2.8G used`, `7.2G available`
- the reported `No space left on device` errors came from the Codex rollout recorder under
  `/dev/shm/codex_home_.../sessions/...jsonl`, not from the blob/PVC mounts:
  - `codex_rollout::recorder: rollout writer failed for /dev/shm/... No space left on device`
  - `codex_core::session: failed to record rollout items: thread-store internal error: No space left on device`

So the live failures are now a compound issue:

- root prompt handling is repaired
- helper orchestration still prioritizes assessment/review over implementation
- repeat-cycle resume continues prior rollout state
- `/dev/shm` thread-store exhaustion adds session-recorder instability during long/repeated runs

Current published state at inspection time:

- stable bundle channel:
  - `current_bundle_version = 20260523T210919371113Z`
  - `current_family_state_version_used = 20260523T232346Z`
- bundle lineage:
  - `family_count = 63`
  - `imported_trace_count = 33`
  - `dirty_family_count = 19`
  - `new_candidate_count = 7`

This means trainer is now incrementally learning the helper-side planning/disk-space branches as
new families, even though the user-visible failure is still "the site does not get corrected."

Additional repository-native verification executed in the current turn:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Observed:

- `compileall` passed
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed as `63 passed`
- smoke test passed
- Rust build passed

Verification categories still not exercised in this turn:

- no full `make quality`
- no coverage run
- no local UI browser run
- no local dataset test suite
- no new live redeploy beyond the already inspected artifacts

## 2026-05-24 Local Repair: No Prompt Reformulation + Hard Reuse Gates

The next local correction intentionally tackled only two runtime/trainer issues:

1. automatic prompt reformulation is now disabled everywhere
2. DSPy family reuse now uses hard execution-context eligibility gates instead of only soft
   lexical scoring

Why this was necessary:

- live helper traces were still turning mixed prompts into planning/pricing/review queries even
  after the root prompt itself stopped rewriting
- those helper rewrites then matched assessment-oriented families with `similarity = 1.0`
- lexical similarity alone was allowing prompts with different execution context to reuse the same
  families as long as the wording was close enough

Repaired contract:

- every prompt surface now stays verbatim
  - `original_prompt == reformulated_prompt` for root turns, helper turns, and lineage turns
- helper generation may still create new explicit tasks, but the proxy no longer rewrites an
  existing prompt into a narrower DSPy mediation query
- family reuse is now ineligible, not merely lower-scored, when:
  - inferred intent labels do not overlap
  - both sides expose constraint/path anchors and those anchors do not overlap
  - command-pattern surfaces do not share substantive anchor terms

Local code changes:

- `src/repo_rag_lab/codex_proxy.py`
  - `reformulate_codex_prompt(...)` now returns the stable verbatim prompt surface instead of
    invoking one helper-LM prompt rewrite path
  - `build_codex_mediation(...)` now disables reformulation for helper turns too
  - runtime family lookup now passes the full prompt/command context into
    `resolve_prompt_family_support(...)`
- `src/repo_rag_lab/training_samples.py`
  - added one normalized routing-context surface for prompt terms, command-pattern terms,
    constraint anchors, and inferred intent labels
  - family routing now performs hard eligibility checks before coarse shortlist scoring and before
    rich similarity scoring
  - trainer-side family-to-family comparison uses the same context gates, so incremental family
    creation and runtime reuse follow the same contract

Targeted regression updates:

- `tests/test_codex_proxy.py`
  - helper mediation now asserts `allow_reformulation is False`
  - family runtime artifact execution now expects the original helper prompt to remain the runtime
    question surface
- `tests/test_training_samples.py`
  - added new command-pattern mismatch and constraint-mismatch cases that must now return
    `band = new`
  - unsupported cross-context reuse no longer carries one fallback `prompt_family_id`

Verification executed in this turn:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_codex_proxy.py tests/test_training_samples.py -q`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Observed:

- `compileall` passed
- `tests/test_codex_proxy.py tests/test_training_samples.py` passed as `87 passed`
- `tests/test_utilities.py tests/test_repository_rag_bdd.py` passed as `63 passed`
- smoke test passed with `command_status = success`
- Rust build passed

Verification categories still not exercised in this turn:

- no full `make quality`
- no coverage run
- no live redeploy yet for this stricter no-reformulation / hard-gate runtime contract

## 2026-05-24 Live Follow-Up: Sticky Guard Landed, Latest Run Resumed, Thread-Store ENOSPC Persists

Latest inspected execution run:

- execution-artifacts run directory:
  - `runs/79b3a5d9f3394371a5e6f5de7f9b7b4f`
- prompt artifact:
  - `prompts_tylers_landscaper-p00000-a8903b`

What the latest live run proved:

- the root/system-layer repair did land:
  - `repo_rag_root_developer_message.txt` included the sticky execution rules:
    - once a concrete execution directive appears, keep the session in execution mode
    - pricing / timeline / call-prep / review subtasks are not valid as the main branch when the
      prompt also requires implementation
    - docs-only edits do not satisfy a site/app change request
- the run was not routed through DSPy:
  - `repo_rag_backend.json` reported:
    - `backend = codex_cli_repo_rag_proxy`
    - `bundle_resolved = false`
    - `bundle_version = null`
    - `dspy_status = skipped`
    - `mediation_mode = passthrough`
- the run still exported trainer-facing traces:
  - `trace_exported = true`
  - `trace_queued = true`

Critical nuance:

- the latest run was not a truly fresh Codex rollout:
  - `execution.log` showed:
    - `codex exec resume rollout-2026-05-24T11-32-35-019e59c2-20e5-7583-8dac-79bc073befd7`
  - `codex_restore_probe.json` confirmed:
    - `restore_status = restored`
    - `restored_files = 6`
    - `latest_session_id = rollout-2026-05-24T11-32-35-019e59c2-20e5-7583-8dac-79bc073befd7`

Interpretation:

- the newest run still inherited prior rollout state
- that makes it an imperfect proof point for the orchestration repair, because the evaluation is no
  longer isolated from previous session decisions

User-visible outcome:

- unlike the earlier purely lazy call-prep runs, this latest resumed rollout did make a concrete
  site change:
  - `apps/web/src/style.css` gained `direction: ltr` fixes for the floating workspace menu toggle
- the response also reported a successful deploy and hosted verification
- so the latest run was no longer `assessment-only`
- but because it resumed a prior rollout, it still cannot be treated as a clean fresh-run proof of
  the sticky execution behavior

Persistent operational bug:

- `codex_response.txt` still contained repeated errors of the form:
  - `failed to record rollout items: thread-store internal error: No space left on device (os error 28)`
- prior live inspection already showed that the Azure artifact/cache PVCs were not full
- the remaining evidence still points to Codex thread-store/session recording under its local
  per-run home area rather than blob/PVC capacity as the bottleneck

Current status:

- root no-rewrite is live
- sticky execution developer-layer instructions are live
- latest run did perform a real UI fix
- DSPy was not reused in that run
- resume was still active
- thread-store `ENOSPC` remains unresolved
