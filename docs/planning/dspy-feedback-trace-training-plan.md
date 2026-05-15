# DSPy Feedback-Trace Training Plan

Date: `2026-05-15`

## Problem

The current family-first DSPy pipeline still under-learns in one critical path:

- when runtime finds a matching family and reuses the compiled family artifact,
  trainer-facing trace handoff is skipped;
- that means successful reuse runs do not update family-level success priors;
- the library therefore learns mostly from fresh/fallback traces and very weakly from
  successful production reuse;
- routing and artifact selection remain tied too closely to replay-set `metric_ratio`
  instead of a runtime feedback posterior.

This keeps the DSPy bundle from improving in the way the contract requires. Even when
runtime repeatedly succeeds on one family, trainer has no structured signal that the
current family artifact is working well.

## Target Contract

The pipeline must carry **two distinct trainer-visible signal types**:

1. `full_trace`
   - produced when no suitable family artifact is available;
   - produced when runtime deliberately falls back to fresh meditation / exploration;
   - contains the full replay object:
     - `original_prompt`
     - `reformulated_prompt`
     - `command_trace`
     - `metrics`
     - retrieved context / provenance
   - becomes a first-class family replay record and may mark a family dirty.

2. `feedback_trace`
   - produced when runtime reuses an existing family artifact successfully or unsuccessfully;
   - does **not** create a new replay-set exemplar by default;
   - updates family / artifact success priors instead;
   - must still preserve enough lineage to audit the decision:
     - `prompt_family_id`
     - `bundle_version`
     - `program_path`
     - `family_artifact_selected`
     - `mediation_metric_hits`
     - `mediation_metric_total`
     - `original_prompt`
     - `reformulated_prompt`
     - condensed `command_trace`

## Design

### Runtime

1. Every runtime mediation result must carry `trainer_signal_kind`.
2. When `family_artifact_selected=true` and `dspy_status=success`, runtime emits:
   - `trainer_signal_kind = "feedback_trace"`
3. When runtime falls back to fresh/global mediation, runtime emits:
   - `trainer_signal_kind = "full_trace"`
4. Runtime no longer suppresses all trainer input on family reuse. It suppresses only
   replay-set growth, not feedback.

### Trainer

1. Imported traces must be classified as:
   - `full_trace`
   - `feedback_trace`
2. `full_trace` updates:
   - `family_records`
   - `family_father_record`
   - `family_runtime_record`
   - `family_needs_recompile`
3. `feedback_trace` updates:
   - `family_feedback_metric`
   - `family_feedback_count`
   - `family_runtime_artifact.feedback_metric`
   - `family_runtime_artifact.predicted_hit_rate`
   - optional per-program feedback summary
4. `feedback_trace` must **not** mark a family dirty by default.
5. Bundle recompilation remains limited to dirty families only.

### Routing / Scoring

Runtime cannot use the current turn's own `metric 1`, because that metric does not exist
until after execution. Instead runtime must choose between family artifact and fresh
mediation using a feedback-aware expected-success score derived from history.

Initial scoring rule for this implementation pass:

- `runtime_hit_rate`:
  best replay-set `metric_ratio` of the current family runtime record
- `feedback_hit_rate`:
  mean of accumulated `feedback_trace` hits / totals for the family artifact
- `predicted_hit_rate`:
  prefer feedback-aware score when present, otherwise fall back to replay-set mean

Implemented formula in the current slice:

- aggregate evidence across:
  - replay-set `full_trace` records
  - compact runtime `feedback_trace` records
- persist one `family_success_metric` payload with:
  - `posterior_mean`
  - `lower_bound`
  - `uncertainty`
  - replay and feedback evidence counts
- runtime artifact selection uses:
  - `predicted_hit_rate = posterior_mean`
  - conservative gating baseline = `lower_bound` when present

## Phases

### Phase 1

- add `trainer_signal_kind`
- stop treating family reuse as "no trainer input"
- persist queue-visible `feedback_trace`
- update family/artifact feedback counters
- expose feedback-aware `predicted_hit_rate`

### Phase 2

- use feedback-aware `predicted_hit_rate` consistently in proxy artifact gating
- surface family uncertainty explicitly
- add exploration policy knobs

Implemented slice in this turn:

- proxy artifact gating now prefers feedback-aware `predicted_hit_rate`
- worker/spec + CLI now carry `family_exploration_rate`
- proxy can deterministically bypass a family artifact for controlled exploration, producing a
  non-family `full_trace` even when a family match exists
- `family_success_metric` now persists one posterior success profile that combines replay traces
  and feedback traces instead of relying on raw means alone
- runtime artifact gating now prefers the conservative lower-bound success baseline when available
- dataset worker handoff now mirrors posterior success fields into trainer-facing payloads so
  queue/import artifacts preserve the same family success profile that runtime used

### Phase 3

- split routing representation from `father` text alone:
  - structured prompt summary
  - embedding/profile centroid
  - family-level latent representation

Implemented slice in this turn:

- family similarity now evaluates the stored prompt profile, not only `family_father_question`
- the profile already includes persisted original/reformulated variants from stored family traces

## Current Work In This Turn

This turn implements **Phase 1** plus the minimum runtime gating changes needed to make
feedback affect future artifact selection.
