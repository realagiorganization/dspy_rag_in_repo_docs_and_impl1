# Per-Turn DSPy Mediation Contract

Historical stage-0 note. The active family-first contract now lives in
[docs/planning/family-first-mipro-runtime-contract.md](family-first-mipro-runtime-contract.md).

Date: `2026-05-08`

This document is the current source of truth for how DSPy is supposed to work in the
`codex exec` pipeline.

## Goal

Keep `codex exec` as the main orchestrator, but make every outbound model request follow the same
DSPy-aware path regardless of whether the request came from the original user prompt or from a
later self-directed Codex step.

## Required Runtime Contract

1. `codex exec` remains the primary orchestrator.
2. Every outbound request that would go from Codex to the model is intercepted by the local proxy.
3. The proxy extracts the latest outbound prompt for that turn as `original_prompt`.
4. Before sending anything into the helper DSPy path, the proxy reformulates that prompt into
   `reformulated_prompt`.
5. The proxy checks the current DSPy champion state for prompt-family support using the
   `reformulated_prompt`.
6. If prompt-family support exists, the proxy runs the helper DSPy mediation model on the
   `reformulated_prompt` and produces one per-turn DSPy trace.
7. If prompt-family support does not exist, the proxy must not inject DSPy. It must pass the
   original request through unchanged.
8. The proxy still records that unsupported turn as a candidate trace so the trainer can learn it
   later.
9. When a command or tool-step sequence is observable for the turn, it must be captured as
   `command_trace` in the same per-turn trace and carried forward with the prompt lineage.

The reformulation stage is the key feature of this design. The active DSPy path is not just
“receive prompt and answer it”. It is:

- receive `original_prompt`
- produce `reformulated_prompt`
- use `reformulated_prompt` for champion lookup, helper-model mediation, traces, champions, and
  the final DSPy program
- preserve `command_trace` alongside that reformulated prompt whenever the sequence is observable

## Allowed Metrics

Only these values are allowed to decide champion updates:

1. `hits / total`
2. prompt-family semantic similarity

No additional trainer-side ranking metrics, replacement deltas, benchmark gates, or hidden score
mixes are allowed on the active champion-selection path.

## Prompt-Family Rules

Prompt-family grouping is defined only by these thresholds:

- similarity `> 0.8`: same prompt family; replace the family champion only when `hits / total` is
  strictly better than the current champion
- similarity `0.8 .. 0.6`: heuristic band
- similarity `< 0.6`: create a new prompt family

## Storage Contract

The storage layout is part of the runtime contract:

- `repo-rag-training-traces`
  - append-only per-turn traces
  - traces are grouped by batch timestamp directory
- `repo-rag-champions`
  - current and historical prompt-family champions
- `repo-rag-bundles`
  - published DSPy bundles

Local worker/PVC behavior:

- the proxy accumulates per-turn trace directories during the run
- after `codex exec` finishes, the worker sends the whole batch to the trainer queue
- the same trace batch is also persisted under the raw training-trace storage contract
- every trace must include both `original_prompt` and `reformulated_prompt`
- every trace must also include `command_trace` when the sequence is observable

## Trainer Contract

The trainer is intentionally narrow:

1. ingest the per-turn traces from one completed worker run
2. group them into prompt families by semantic similarity over `reformulated_prompt`
3. retain `command_trace` as an equal lineage surface for those families and champions whenever it
   is present
4. compare candidate vs champion using only `hits / total`
5. update the family champion when the candidate is strictly better
6. create a new family when similarity is below `0.6`
7. assemble the latest family champions into the next DSPy bundle

The trainer is not allowed to add extra ranking math on top of that path.

Champion records and the final DSPy program must retain the `reformulated_prompt` explicitly.
Champion records and trace storage must retain `command_trace` explicitly whenever it exists.

## Work Plan

1. Update the repository docs so this contract replaces the old “prompt-time augmentation only”
   mental model.
2. Make the proxy turn-aware and persist one per-turn DSPy mediation trace directory for every
   outbound Codex request.
3. Gate runtime DSPy injection on champion prompt-family support instead of always injecting the
   global bundle output.
4. Batch-export all per-turn traces after one `codex exec` run and hand them off through the
   existing trainer queue.
5. Align champion storage and trainer updates with `repo-rag-champions`, `repo-rag-training-traces`,
   and `repo-rag-bundles`.
6. Remove the active trainer-side extra ranking rules so champion replacement follows only the
   contract above.
