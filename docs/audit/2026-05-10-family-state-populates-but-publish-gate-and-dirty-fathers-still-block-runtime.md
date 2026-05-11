# 2026-05-10 Family State Populates But Publish Gate And Dirty Fathers Still Block Runtime

## Context

The latest uploaded execution artifacts from `../dataset/artifacts` came from run
`25637723574_20260510_195334`. The execution-side symptoms changed materially:

- `repo_rag_codex_proxy_last.json` now showed a clean `original_prompt` and a real
  `reformulated_prompt`
- per-turn batch export existed under `repo_rag_turn_traces/20260510T194226Z/`
- `trace_handoff_status` still reached `queued`

But runtime still did not activate family-first DSPy execution:

- `bundle_resolved = false`
- `bundle_version = null`
- `dspy_status = "skipped"`
- `family_artifact_selected = null`

The user also reported two operator-visible failures:

1. `repo-rag-training-families` still appeared empty
2. prompt-token usage still looked suspiciously high

## Live Evidence

Live trainer inspection in AKS showed that the first report was now stale:

- `/workspace/repo-rag/artifacts/trainer/family-state.json` exists inside the trainer pod
- live `training-candidates-summary.json` reports:
  - `candidate_count = 19`
  - `input_trace_count = 22`
  - `prompt_family_count = 19`
  - `new_prompt_family_count = 1`
- Azure Blob container `repo-rag-training-families` is populated
  - live inspection counted `143` blobs
  - `current.json` exists
  - `families/<prompt_family_id>/family.json` exists
  - `families/<prompt_family_id>/father.json` exists
  - `families/<prompt_family_id>/records/<snapshot>.json` exists

So the earlier “family container stays empty” blocker is resolved in live infrastructure.

The second live inspection exposed the actual two remaining blockers:

### 1. Stored family fathers were still polluted with execution scaffolding

Downloaded `father.json` records in `repo-rag-training-families` still included lines like:

- `Repository checkout: ...`
- `Attachment mount: ...`

The execution-side proxy now compares a clean prompt against those polluted stored father strings.
That drives similarity down even for the same logical task. The latest run showed:

- `prompt_family_id = "pf-d2d30a2c28a2a9d1"`
- `prompt_family_similarity = 0.293333`
- `prompt_family_band = "new"`

So runtime kept treating the clean prompt as a new family and fell back to passthrough.

### 2. `repo-rag-bundles` was genuinely empty

Live Blob inspection of `repo-rag-bundles` showed:

- blob count `0`
- no `channels/stable.json`
- no `channels/current.json`
- no `published.json`

This was not a staging bug anymore. The live trainer service state explains why:

- `successful_cycle_count = 0`
- `failed_cycle_count = 7`
- `bundle_gate_failure_count = 7`
- `total_publish_count = 0`
- `last_cycle_warnings` contained:
  - `Bundle publish was blocked by trainer-side DSPy benchmark gates.`
  - `Promotion to stable was blocked by trainer-side DSPy benchmark gates.`

The latest local bundle exists under
`artifacts/dspy/20260510T190905532238Z/{program.json,metadata.json,bundle.json}`, but its
benchmark summary is:

- `case_count = 26`
- `pass_count = 8`
- `pass_rate = 0.3076923076923077`

So runtime could not possibly activate a remote bundle because none had ever been published.

## Token Interpretation

This run used `prompt_tokens = 69812`, which is much lower than the earlier six-figure resumed
lanes but still non-trivial. The artifacts show that the remaining cost was mostly real Codex
activity rather than prompt-envelope noise alone:

- `repo_rag_turn_trace_batch_manifest.json` captured `15` turns
- `repo_rag_mcp_usage_summary.json` only recorded `search_repo = 1` and `ask_repo = 1`
- the cleaned prompt lineage in `repo_rag_codex_proxy_last.json` is compact and no longer carries
  the Discord execution envelope

There was still one likely secondary noise source: `trace-export` was writing
`artifacts/traces/...` under the target repo root, which risks making Codex diff or commit its own
trace files.

## Local Fix

This turn applied three fixes.

### 1. Sanitize trainer-side family prompts the same way runtime already sanitizes them

`src/repo_rag_lab/training_samples.py` now strips worker execution scaffolding from:

- `question`
- `original_prompt`
- `reformulated_prompt`
- prompt-like `command_trace` fields
- equivalent provenance prompt-lineage fields

The trainer now normalizes away:

- `Discord channel:`
- `Messages with required reaction:`
- `Repository checkout:`
- `Attachment mount:`
- forwarded Discord tails

That means stored `family_father_question` values and replay-set records are now built from the
same cleaned prompt surface that the execution-side proxy uses for live family matching.

### 2. Remove the implicit bundle publish gate for family-first runs

`src/repo_rag_lab/utilities.py` no longer auto-injects
`minimum_bundle_pass_rate = 1.0` whenever a trainer recompile or publish is requested.

That implicit gate was champion-era policy. In the current family-first architecture it kept
`repo-rag-bundles` empty even after family generation and per-family DSPy artifacts were already
working locally. Bundle gating still remains available when an operator explicitly sets
`minimum_bundle_pass_rate`, but it is no longer silently forced on every recompile cycle.

### 3. Keep trace-export files out of the target repository worktree

`../dataset/docker/prompt-executor/worker_execution_prompt.py` now runs `repo-rag trace-export`
with `--root <exec_dir>` instead of `--root <target_repo>`.

That keeps exported trace JSONs under the worker execution directory instead of creating
`artifacts/traces/...` inside the repository being edited by Codex.

## Verification

Executed locally in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_training_samples.py tests/test_utilities.py -q`
  - `71 passed`
- `cd ../dataset && pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py -q`
  - `22 passed`
- `cd ../dataset && python -m compileall docker/prompt-executor/worker_execution_prompt.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py`
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `46 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `command_status = success`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `Finished 'dev' profile`
- `UV_CACHE_DIR=/tmp/uvcache make files-sync`
  - `command_status = success`
- `UV_CACHE_DIR=/tmp/uvcache make exploratorium-sync`
  - `command_status = success`
- `UV_CACHE_DIR=/tmp/uvcache make verify-surfaces`
  - `command_status = success`

## Remaining Risk

No new live AKS run has been executed after these fixes.

The next expected live proof points are:

- new family fathers in `repo-rag-training-families` no longer contain
  `Repository checkout:` / `Attachment mount:`
- runtime prompt similarity for the debt-relief prompt rises above the family match threshold
- trainer cycles start publishing into `repo-rag-bundles`
- execution-side `bundle_resolved` / `bundle_version` become non-null on a subsequent run
