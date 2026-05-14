# 2026-05-14 Latest Run Partial DSPy Runtime And Single-Family Trainer Rebuild

## Summary

The latest execution run completed successfully and uploaded a full `execution-artifacts` bundle, but
the runtime still only used DSPy **partially**:

- the worker loaded bundle `20260513T190827406187Z`
- the proxy preserved the full user prompt, including `This is a test run, no development or installation required.`
- family lookup succeeded for the demo-GIF task
- however the proxy still reported `dspy_status=heuristic` with the thread-affinity warning
  `dspy.settings can only be changed by the thread that initially configured it.`

On the trainer side, the new family-state version `20260514T101620Z` contains **one** family with
`17` replay records. Blob evidence shows that those records do in fact belong to one prompt family:
every record shares the same `original_prompt`, and only two reformulation variants exist across the
set. The surprising part is not the clustering; the surprising part is that the worker exported
`10` same-prompt snapshots for one rollout, and `repo-rag-training-traces/processed` now contains
`20` blobs for that same run because the authoritative trusted handoff re-imported those traces
under second-generation processed names.

## Execution Findings

From `../dataset/artifacts/upload_summary.json` and `../dataset/artifacts/all_artifacts.tar.gz`:

- `execution_id = 25853290372_20260514_100423`
- upload to `execution-artifacts/executions/25853290372_20260514_100423` succeeded
- `repo_rag_codex_proxy_last.json` reported:
  - `bundle_version = 20260513T190827406187Z`
  - `prompt_family_id = pf-9287fa96e7c8f8ff`
  - `prompt_family_similarity = 0.906298`
  - `prompt_family_band = match`
  - `family_artifact_selected = true`
  - `family_runtime_hit_rate = 1.0`
  - `family_artifact_hit_rate = 1.0`
  - `dspy_status = heuristic`
  - `reformulation_status = identity`
  - `program_path = null`
- the proxy warning remained:
  - `DSPy mediation was unavailable; using heuristic synthesis instead. (dspy.settings can only be changed by the thread that initially configured it.)`

This means the worker did consult family/runtime metadata from the DSPy library, but it did **not**
successfully execute a DSPy mediation program for the final proxy snapshot.

## Prompt Preservation

The user-supplied supplemental line survived into the actual `codex exec` prompt. In
`codex_response.txt` the worker executed:

- the original task text
- followed by `This is a test run, no development or installation required.`

The absence of a new commit in the target repository was not caused by this line being dropped.
`codex_response.txt` explicitly states:

- `HEAD 62a0814 already satisfies the request, so I did not make any edits in this run.`
- `git status --short` was clean
- the demo GIF and README wiring were already present

So the missing commit was expected for this run.

## Trusted Trace Handoff

The worker exported:

- `10` turn-trace files under `repo_rag_turn_traces/20260514T095824Z/`
- `10` trusted queue items `.trusted_trace_queue_item.{0..9}.json`
- `repo_rag_turn_trace_enqueue_batch.json` with `handled_count = 10`
- `trusted_trace_handoff_summary.json` with `status = success`, `queued = 1`, `skipped = 0`

Inside the trusted queue items:

- `1/10` item remained `prompt_family_band = new`
- `9/10` items matched `pf-9287fa96e7c8f8ff`
- all `10/10` items shared the same `original_prompt`
- `8/10` items used the long reformulated prompt variant
- `12/20` processed descendants later used the identity reformulated variant

The worker therefore over-produced snapshots for one outer prompt. The family match itself is not
the problem; the repeated snapshots of the same prompt are the problem.

## Blob Findings

Using Azure CLI against `realagistorage`:

- `repo-rag-training-traces/queued/repo-rag-training/` was empty by inspection time
- `repo-rag-training-traces/processed/repo-rag-training/` contained **20** blobs for this run:
  - `10` direct processed blobs:
    - `20260514T100052Z-worker-0-...-0.json` through `20260514T100247Z-worker-0-...-9.json`
  - `10` second-generation processed blobs from trusted-handoff replay:
    - `20260514T100404Z-20260514T100046Z-worker-0-...-0.json` through
      `20260514T100404Z-20260514T100242Z-worker-0-...-9.json`
- all `20` processed blobs still shared one `original_prompt`
- processed family metadata across those `20` blobs was:
  - `18` blobs tagged `pf-9287fa96e7c8f8ff`
  - `2` blobs remained `prompt_family_id = null`

The latest trainer version in `repo-rag-training-families` was:

- `20260514T101620Z`

That version contained:

- `family-state.json` size `3101` bytes
- one family:
  - `pf-dc1f706da0b4f060`
- `family.json` reported:
  - `family_records_len = 17`
  - `question_variants_len = 2`
  - `family_needs_recompile = true`
  - `family_runtime_artifact = null`
- all `17` family records shared the same `original_prompt`

So trainer did **not** incorrectly merge multiple unrelated prompt families. It rebuilt a single
family because the historical processed corpus visible to it for this task was still one logical
prompt family.

## Interpretation

Two distinct problems remain:

1. **Runtime DSPy execution remains partial.**
   Family metadata is loaded and matched, but the final proxy snapshot still falls back to the
   heuristic path because of the DSPy thread-affinity warning.
2. **The worker still emits too many same-prompt snapshots.**
   One rollout created `10` queue items for the same `original_prompt`, and trusted replay doubled
   that to `20` processed blobs for storage. Trainer-side dedupe reduced the final family to `17`
   records, but the upstream overproduction remains.

The single-family result itself is therefore **not** the primary bug. The bug is that one prompt
rollout still produces too many trace snapshots, and the proxy still does not complete family-backed
DSPy mediation reliably.

## Validation

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
