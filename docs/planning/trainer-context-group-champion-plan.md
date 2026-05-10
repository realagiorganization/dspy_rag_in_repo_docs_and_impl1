# Trainer Context-Group Champion Plan

Historical plan. The active product contract now lives in
[docs/planning/family-first-mipro-runtime-contract.md](family-first-mipro-runtime-contract.md),
which keeps the family grouping but replaces champion-first product truth with father-based routing
plus family runtime artifacts.

Goal: keep one global universal DSPy bundle while stopping `last write wins` churn when the same prompt is executed many times under evolving repository context.

## Standing Product Requirement

This plan exists to satisfy one explicit requirement and should not drift away from it:

- the system must maintain **one global universal DSPy bundle**
- that bundle must **learn incrementally on every accepted/candidate run**
- if an existing prompt family produces a materially better family champion, the next bundle
  candidate must replace the prior champion for that family
- if a completely new prompt family appears, the next bundle candidate must include that new
  family rather than treating it as repo-local noise
- publication must eventually validate the bundle against the **global champion set**, not only
  against one repo-local benchmark bank
- that means the final publish gate must be **family-aware and delta-aware**:
  - compare the incoming request against prior family champions by request delta, not by repo name
    or branch identity
  - compare the retrieved context against prior champion evidence by context delta, not by assuming
    one fixed repo replay surface
  - allow repo metadata to be supporting evidence only, never the primary identity contract
  - avoid flattening all champion families into one repo-local benchmark pass

Clarification:

- “incremental” here does **not** mean “never rematerialize or recompile the bundle”
- the expected incremental contract is:
  - keep the full durable candidate set
  - update champion state incrementally from that candidate set
  - then rebuild the compile-facing champion set from current champions when publication is needed
- so a fresh bundle artifact may still be recompiled from the current champion set; the
  incrementality lives in `candidate -> champion` state, not in an in-place patch to bundle weights
- candidates are the broad accepted/candidate trace pool
- champions are the reduced compile-facing state
- a large delta should first create a **new context-group champion candidate** or a **new prompt
  family**, and only then participate in family-champion selection and bundle publication
- a new context-group champion does **not** necessarily replace the family champion immediately if
  the family-level comparison still prefers the incumbent champion on score/support grounds

The current repo-local benchmark-path split is only a temporary unblocker for trainer publication.
It is not the final contract.

## Constraints

- The current DSPy compile contract still trains on `question -> expected_answer`.
- The generated compile set cannot safely contain multiple conflicting answers for one identical `question`.
- Because of that, the first implementation stage must distinguish multiple context groups in trainer state, but materialize only one `family champion` per prompt family into the compile set.

## Phase 0: Recon and shape

- [x] Inspect the current trainer flow from imported traces to `training-candidates.yaml`, `generated-training.yaml`, and `run_trainer_cycle(...)`.
- [x] Inspect the current trace payload shape to confirm which context fields are already available for grouping.
- [x] Confirm the current DSPy compile limitation: duplicate questions with conflicting answers are not a safe first-stage compile contract.

## Phase 1: State surfaces

- [x] Add explicit trainer state surfaces for prompt families, context groups, and champions.
- [x] Persist a new champion index under `artifacts/trainer/` alongside the existing training snapshots.
- [x] Keep raw imported traces immutable and separate from champion state.

## Phase 2: Identity and grouping

- [x] Add `prompt_family_id` derived from normalized question text.
- [x] Add `exact_snapshot_id` for exact immutable trace identity.
- [x] Add a first-stage `context_group_id` assignment based on retrieval context similarity.
- [x] Implement a stable context similarity heuristic using retrieved source overlap and retrieval mode.
- [x] Let one context group absorb gradual retrieval-source drift instead of splitting on every minor context shift.
- [x] Export and consume snippet-level evidence fingerprints so same-source but semantically different retrieval contexts can split cleanly.
- [x] Tighten prompt-delta grouping so materially different incoming prompts can split into a new
  prompt-family or new champion path before they are flattened into normalized-question identity.
- [ ] Make the context/request split policy explicit as a product knob; current code already uses
  similarity bands, and that is the preferred shape over one hard “20% delta” cutoff:
  - `>= strong-match threshold` should merge into the same family/group
  - `< weak-match threshold` should split into a new family/group
  - the band in between should remain a gray zone for additional overlap heuristics instead of a
    single hard boundary

## Phase 3: Champion policy

- [x] Add a trainer-side quality score for one trace candidate.
- [x] Track one champion per context group.
- [x] Track one family champion across the context groups within a prompt family.
- [x] Replace champions only when a challenger clears the quality gate instead of using `last write wins`.
- [x] Accumulate explicit support for repeated same-answer variants inside a context group.
- [x] Keep the family champion stable when a new context group has only a slight score edge but weaker support.

## Phase 4: Materialization

- [x] Materialize `training-candidates.yaml` from family champions instead of from raw last-write question replacement.
- [x] Keep `generated-training.yaml` compatible with the current DSPy compile contract.
- [x] Ensure `new_candidate_count` reflects meaningful champion changes rather than raw duplicate trace replay.
- [x] Add a minimum-new-candidates recompile gate so trainer-cycle can batch family-champion changes instead of recompiling on every single update.
- [x] Preserve benchmark context inside trainer-candidate champion rows so bundle benchmarking can
  follow the generated champion set without forcing repo/branch replay identity.

## Phase 5: Verification and docs

- [x] Add and update tests for prompt-family grouping, context grouping, champion replacement, and no-churn replay.
- [x] Wire `min_new_candidates_for_recompile` through trainer deployment defaults and Kubernetes manifest generation so live AKS trainer cycles can batch recompiles the same way the local trainer CLI already can.
- [x] Update `docs/architecture/research-narrative.md` with the new trainer model.
- [x] Update `docs/planning/dataset-integration-plan.md` to describe the champion-index flow.
- [x] Sync `FILES.md` and `FILES.csv` after tracked-file changes.
- [x] Run targeted verification and record the exact commands/results.

## Deferred work after this first stage

- [ ] Add chunk-hash and evidence-summary similarity once the worker trace schema exports them consistently.
- [ ] Consider an exemplar-memory layer for similar prior tasks that sits beside the global DSPy bundle.
- [ ] Revisit whether future DSPy compile surfaces should support multiple context-distinct examples for one visible user prompt.
- [ ] Finish the publish gate so family-aware, request-delta-aware, and context-delta-aware
  validation comes from champion/request/context comparisons directly rather than today’s
  benchmark-context bridge.
