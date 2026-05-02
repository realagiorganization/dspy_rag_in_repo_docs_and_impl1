# Trainer Context-Group Champion Plan

Goal: keep one global universal DSPy bundle while stopping `last write wins` churn when the same prompt is executed many times under evolving repository context.

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
