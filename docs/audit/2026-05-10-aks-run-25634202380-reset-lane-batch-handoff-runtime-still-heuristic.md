# Repository audit note for AKS run 25634202380 on 2026-05-10

## Scope

- Inspect the uploaded execution artifacts from `../dataset/artifacts`.
- Compare the live run against the current family-first DSPy runtime contract.
- Record what worked, what still failed, and which local verification commands still pass in this
  repository.

## Run identity

- Execution id: `25634202380_20260510_170342`
- Upload timestamp: `2026-05-10T17:03:44Z`
- Backend: `codex_cli_repo_rag_proxy`
- Result: `success=true`

## What worked

### 1. The worker did reset the Codex lane instead of resuming it again

`codex_session_state.json` reports:

- `session_mode=reset`
- `restore_status=reset:resumed-run-threshold`
- `lane_source=auto:queue_and_slug`

So the resumed-run guardrail is now live in the worker path.

### 2. The duplicate legacy trace handoff is gone

`trusted_trace_handoff_summary.json` shows:

- `status=success`
- `skipped=1`
- skip reason `worker-batch-handoff-already-succeeded`

That means the worker batch handoff won and the old trusted fallback did not upload a second queue
item.

### 3. Compact per-turn trace batching worked end to end

The run emitted:

- `repo_rag_turn_traces/20260510T170157Z/manifest.json`
- `repo_rag_turn_traces/20260510T170157Z/turn-000.json`
- `repo_rag_turn_trace_export_batch.json`
- `repo_rag_turn_trace_enqueue_batch.json`

`repo_rag_turn_trace_batch_manifest.json` reports:

- `batch_name=20260510T170157Z`
- `execution_status=success`
- `metric_hits=1`
- `metric_total=1`
- `trace_paths=[repo_rag_turn_traces/20260510T170157Z/turn-000.json]`

`repo_rag_turn_trace_enqueue_batch.json` reports:

- `command_status=success`
- `turn_count=1`
- `handled_count=1`
- `failed_count=0`

### 4. The raw Discord forwarding tail was removed from the actual execution prompt

The real `codex exec` transcript no longer contains:

- `Discord channel:`
- `Messages with required reaction:`
- `[forwarded]`
- `Attachment locations:`

The live prompt still includes a minimal repo/attachment envelope, but the noisy Discord scaffolding
is no longer present.

### 5. The trainer-facing answer payload stayed compact

`turn-000.json` stores a short final answer instead of the full `codex_response.txt`, and the batch
queue payload now carries one compact per-turn record rather than using the raw transcript as the
primary answer surface.

## What still did not work

### 1. Live DSPy bundle activation still failed

`repo_rag_codex_proxy_last.json`, `repo_rag_backend.json`, and `repo_rag_outcome.json` all agree:

- `bundle_resolved=false`
- `bundle_version=null`
- `program_path=null`
- `program_loaded=false`
- `dspy_status=heuristic`
- warning: `No compiled DSPy bundle is available.`

So the execution pod still did not load a staged bundle or family artifact during the live run.

### 2. Family routing never activated

The live execution fields remained null:

- `prompt_family_id`
- `prompt_family_similarity`
- `family_runtime_hit_rate`
- `family_artifact_hit_rate`
- `family_artifact_selected`
- `dspy_lm_model`

That means the family-first runtime path still did not run inside the execution pod.

### 3. Reformulation is still only an envelope prepend, not a real prompt rewrite

The prompt lineage is now cleaner, but it still behaves like this:

- `original_prompt` = the cleaned task
- `reformulated_prompt` = the cleaned task plus `Repository checkout` and `Attachment mount`

This is not yet the stronger prompt-family reformulation contract discussed for family-specific DSPy
mediation.

### 4. The execution tarball still contains no staged bundle or family-state payloads

A direct filename scan over `all_artifacts.tar.gz` found no entries matching:

- `bundle`
- `family-state`
- `family_state`
- `program.json`
- `metadata.json`
- `.repo_rag_bundle_store`

So from the execution-stage artifacts alone, the worker did not expose any staged bundle/family
payload into the captured artifact set. That strongly matches the null runtime bundle fields above.

### 5. Token usage is still much higher than the known compact baseline

This run used:

- `prompt_tokens=116099`

Comparison:

- versus previous inspected run `25632110510`: `134790 -> 116099` (`-13.9%`)
- versus the smaller compact baseline `25629990035`: `27193 -> 116099` (`+327.0%`)

The main cost is still inside the Codex transcript itself:

- `codex_response.txt` = `96362` bytes
- `3759` lines
- `38` shell `exec` steps
- `1` `search_repo`
- `1` `ask_repo`

So the biggest remaining token sink is still the autonomous Codex rollout, not the repo-RAG
developer message.

## Interpretation

The current state is split:

- downstream trainer/family generation may already be working outside this execution dump
- but the execution pod itself still runs in heuristic repo-RAG mode because no staged bundle/family
  artifact becomes visible at runtime

In other words, queueing and trace compaction are now substantially correct, but live family-first
DSPy execution is still missing.

## Local verification executed in this turn

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` -> `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` -> `pass` (`45 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test` -> `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`

## Checks not executed in this turn

- no new lint run
- no new type-checking run
- no `make coverage`
- no notebook execution suite
- no live Azure Blob inspection beyond the uploaded local artifact bundle

## Current conclusion

Run `25634202380_20260510_170342` confirms that the recent handoff and prompt-cleanup fixes are
live:

- reset-lane guardrail worked
- compact batch handoff worked
- duplicate queue upload stayed suppressed
- Discord forwarding noise no longer reached the real `codex exec` prompt

But the primary runtime goal is still not met:

- the execution pod did not resolve or load a compiled DSPy bundle
- family routing fields stayed null
- live execution still fell back to heuristic mediation
