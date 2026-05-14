# 2026-05-13 Latest Run: Partial Family Runtime Use And Six Same-Prompt Traces

## Scope

Inspect the freshly uploaded `../dataset/artifacts` bundle to answer four questions:

1. whether the worker used the DSPy family library at runtime
2. how many new trainer trace blobs this run produced
3. whether the six new traces all landed in one family because they are genuinely the same prompt
4. whether the current behavior matches the intended contract that every prompt hitting the proxy
   should yield a fresh trace only when DSPy did not work

## Artifact Set

Inspected:

- `../dataset/artifacts/redis_results.json`
- `../dataset/artifacts/upload_summary.json`
- `../dataset/artifacts/all_artifacts.tar.gz`

Key runtime files inside `all_artifacts.tar.gz`:

- `repo_rag_codex_proxy_last.json`
- `repo_rag_turn_trace_batch_manifest.json`
- `repo_rag_turn_trace_enqueue_batch.json`
- `repo_rag_turn_trace_export_batch.json`
- `.trusted_trace_queue_item.{0..5}.json`
- `repo_rag_turn_traces/20260513T172037Z/*.json`

## Run Summary

- `execution_id=25814410681_20260513_172803`
- `success=true`
- `backend_used=codex_cli_repo_rag_proxy`
- `trace_handoff_status=queued`
- `prompt_tokens=68041`
- `artifacts_count=37`

The token count is elevated but not runaway for this run. The execution transcript indicates a real
codex rollout instead of pure helper churn.

## DSPy Family Library Usage

The worker **did** use the DSPy family library, but only partially and inconsistently.

Top-level proxy status:

- `bundle_version=20260513T144835007919Z`
- `prompt_family_id=pf-9287fa96e7c8f8ff`
- `prompt_family_similarity=0.906298`
- `prompt_family_band=match`
- `reformulation_status=dspy`
- `dspy_lm_model=azure/gpt-4o`

Per trusted queue item:

- item `0` selected the matched family artifact:
  - `family_artifact_selected=true`
  - `family_artifact_hit_rate=1.0`
  - `program_path=artifacts/trainer/remote-family-state/20260513T162847Z/families/pf-9287fa96e7c8f8ff/runtime-artifact/program.json`
- items `1..5` fell back to the global bundle program:
  - `family_artifact_selected=false`
  - `family_artifact_hit_rate=0.0`
  - `program_path=artifacts/dspy/remote/20260513T144835007919Z/program.json`

So the runtime family library is no longer entirely dead, but it still behaves incorrectly: the
same matched family oscillates between family-artifact reuse and global fallback across one run.

## New Trace Count

This run produced exactly **6** new trainer queue items.

Evidence:

- `repo_rag_turn_trace_batch_manifest.json` listed six payloads under
  `repo_rag_turn_traces/20260513T172037Z/`
- `repo_rag_turn_trace_enqueue_batch.json` reported `handled_count=6`
- `repo_rag_turn_trace_export_batch.json` listed six generated queue paths:
  - `queued/repo-rag-training/...-0.json`
  - `queued/repo-rag-training/...-1.json`
  - `queued/repo-rag-training/...-2.json`
  - `queued/repo-rag-training/...-3.json`
  - `queued/repo-rag-training/...-4.json`
  - `queued/repo-rag-training/...-5.json`
- the execution bundle also preserved six `.trusted_trace_queue_item.*.json` files

Live Azure blob listing now confirms those six queue items were really uploaded under
`repo-rag-training-traces/queued/repo-rag-training/20260513T172756Z-*`.

## Why They All Went To One Family

The six queued traces all belong to one family **under the current family-routing logic**, because
their prompt-identifying fields are effectively identical:

- `prompt_family_id` in trusted queue items: always `pf-9287fa96e7c8f8ff`
- `prompt_family_similarity`: always `0.906298`
- `original_prompt`: identical in all six
- `question`: identical in all six
- `reformulated_prompt`: identical in all six

What changes across the six traces is not the prompt, but the accumulated execution trace:

- `command_trace` length grows across the six queue items: `2`, `6`, `10`, `20`, `26`, `30`

The answers are also different textually in all six traces, but semantically say the same thing:
the repository already contains the requested demo GIF.

So these are **not** six different prompt families. They are six different snapshots of the same
top-level user request taken at different points in the Codex rollout.

## What Blob Shows In The Family Container

The current family-state pointer is:

- `current_version=20260513T172754Z`
- `current_family_count=1`

The matched family is still:

- `pf-9287fa96e7c8f8ff`

Comparing the previous family version `20260513T162847Z` with the new one `20260513T172754Z`
shows:

- previous replay-record count: `132`
- current replay-record count: `136`
- newly added replay-record files: **4**

So the trainer accepted all **6** queued trace items, but only materialized **4** new
family-record snapshots. This means the current trainer-side dedupe merged two of the six queued
items instead of blindly appending all six.

The four new family replay-records still all correspond to the same outer prompt:

- identical `question`
- identical `original_prompt`
- identical `reformulated_prompt`
- identical `metric_ratio=1.0`
- varying `command_trace` lengths: `2`, `6`, `9`, `18`

That confirms the family grouping itself is not mixing unrelated prompts. The mismatch is upstream:
the runtime keeps emitting repeated same-prompt mediation snapshots, and the trainer only partially
collapses them.

## Contract Mismatch

This behavior is mathematically consistent with the current routing implementation, but it does
not fully match the user-requested contract.

The intended contract says:

- every prompt that reaches the proxy should be evaluated as its own mediation event
- a new trace should be created only when DSPy did not work

What the current run shows instead:

- the proxy keeps reusing the same `original_prompt` / `question` for multiple turns in the same
  rollout
- those repeated snapshots become six trainer queue items for one top-level prompt
- one of those six items even had `family_artifact_selected=true`, so the system still exported a
  trace even though DSPy did work for that turn

So the current implementation still over-produces traces relative to the intended “trace only on
DSPy miss” contract.

## Current Interpretation

The important facts are now:

- DSPy family lookup is active.
- Family-artifact execution is active for at least one turn.
- The runtime bridge is still unstable because the same matched family falls back to the global
  program on later turns in the same run.
- The six queued traces are not six different prompt families; they are six snapshots of one
  identical outer prompt with growing `command_trace`.
- The trainer did not dump all six queued traces into the family as six distinct replay records;
  it reduced them to four new family records, so some dedupe is already happening.
- If the desired contract is “new trace only when DSPy miss happens”, the current behavior still
  needs tightening.
