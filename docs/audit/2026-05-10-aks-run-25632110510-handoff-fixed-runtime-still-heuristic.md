# Repository audit note for 2026-05-10 AKS run 25632110510 handoff fixed but runtime still heuristic

## Scope

- Inspect the latest execution artifacts uploaded under `../dataset/artifacts` after the next live
  rerun with the family-first runtime fixes already deployed.
- Verify whether the fixes from `2026-05-10-family-first-runtime-fixes-after-run-25629990035.md`
  actually changed live runtime behavior.

## Inspected run

- `execution_id`: `25632110510_20260510_152621`
- Azure execution path from `upload_summary.json`:
  `executions/25632110510_20260510_152621`

## Evidence inspected

- `../dataset/artifacts/redis_results.json`
- `../dataset/artifacts/upload_summary.json`
- `../dataset/artifacts/all_artifacts.tar.gz`
- `../dataset/artifacts/processed.tar.gz`

## What worked

### 1. The worker stayed on the intended repo-rag proxy path

- `backend_used = "codex_cli_repo_rag_proxy"`
- `success = true`
- `trace_handoff_status = "queued"`

### 2. Forwarded Discord tail no longer contaminates prompt-lineage artifacts

The live proxy status and compact turn trace no longer include the forwarded tail:

- `question`
- `original_prompt`
- `reformulated_prompt`
- user-facing `command_trace`

The persisted prompt lineage is now the clean repository task only:

- `In https://github.com/realagiorganization/national-debt-relief ... Put it in the readme ...`

The earlier forwarded suffix
`[forwarded] @Tyler ATTTENTION. @|DT| drybox` is absent from those compact trainer-facing fields.

### 3. Per-turn batch export and enqueue still work

Observed files:

- `repo_rag_turn_traces/20260510T152439Z/turn-000.json`
- `repo_rag_turn_trace_export_batch.json`
- `repo_rag_turn_trace_enqueue_batch.json`

Observed statuses:

- batch export: `command_status = "success"`
- batch enqueue: `command_status = "success"`
- `turn_count = 1`
- `handled_count = 1`

### 4. The legacy duplicate queue handoff is now effectively suppressed

The deploy-stage trusted handoff summary now reports:

- `attempted = 0`
- `queued = 0`
- `failed = 0`
- `skipped = 1`
- skip reason:
  `worker-batch-handoff-already-succeeded`

That means the runner-side fallback no longer creates a second queue upload after the worker already
performed the compact batch handoff.

Related evidence:

- `execution_artifacts/trusted_trace_handoff_summary.json`
- `repo_rag_trace_enqueue.json` now mirrors the batch summary shape
  (`command = "trace-enqueue-batch"`) instead of a second single-trace queue item.

### 5. Compact trainer-facing trace persistence still works

`turn-000.json` remains compact and useful:

- `answer_length ~= 600`
- `mediation_metric_hits = 1`
- `mediation_metric_total = 1`
- no giant `codex_response.txt` transcript is being exported as the trainer-facing answer payload

## What still did not work

### 1. Live DSPy runtime still did not activate

The live proxy still fell back to heuristic mediation:

- `bundle_resolved = false`
- `bundle_version = null`
- `program_path = null`
- `program_loaded = false`
- `dspy_status = "heuristic"`
- warning:
  `DSPy mediation was unavailable; using heuristic synthesis instead. (No compiled DSPy bundle is available.)`

So the central family-first runtime goal is still not live in this execution.

### 2. Family routing fields are still absent at runtime

The compact trace still carries no family match:

- `prompt_family_id = null`
- `prompt_family_similarity = null`
- `prompt_family_band = null`
- `family_runtime_hit_rate = null`
- `family_artifact_hit_rate = null`
- `family_artifact_selected = null`

That means the proxy still did not perform the agreed runtime step of matching the prompt against
bundle fathers and selecting a family runtime artifact.

### 3. Prompt reformulation still collapsed to identity

In both `repo_rag_codex_proxy_last.json` and `turn-000.json`:

- `original_prompt == reformulated_prompt`

So the helper-model reformulation stage still did not produce a distinct mediation prompt in this
live case.

## What behaved incorrectly

### 1. Prompt-token usage regressed sharply again

Observed token usage:

- `prompt_tokens = 134790`
- previous inspected live baseline:
  `27193`
- delta versus previous:
  - `+107597`
  - `+395.679%`

### 2. The main token blow-up is not the mediation block; it is the resumed Codex lane

The compact proxy mediation payload is comparatively small:

- cleaned `question` length: `297` chars
- `developer_message` length: `1668` chars

But the persisted Codex transcript is large again:

- `codex_response.txt` size: `92952` bytes
- `codex_response.txt` line count: `2706`
- `package-lock.json` mentions: `36`

The live session state also confirms heavy resume reuse:

- `codex_session_mode = "resumed"`
- `total_run_count = 13`
- `resumed_run_count = 11`
- `usage_delta_vs_previous.prompt_tokens_delta = 107597`

So the dominant inflation in this run comes from the resumed Codex conversation and its long
transcript/diff loop, not from the repo-rag mediation block itself.

### 3. The raw Codex CLI input is still noisy even though the compact trace is clean

The command header inside `codex_response.txt` still shows that `codex exec` was launched with the
full dataset execution envelope and forwarded Discord message in the initial prompt text.

That means:

- trainer-facing compact traces are now cleaner
- but the actual first Codex prompt still contains Discord scaffolding, attachment listings, the
  autonomous execution contract, and the forwarded message

This is a separate live-context source of noise from the now-clean compact turn trace.

## What cannot be concluded from these local artifacts alone

The local execution dump does not contain the downstream Azure Blob contents of:

- `repo-rag-training-families`
- `repo-rag-bundles`

So this artifact set does **not** directly prove or disprove whether the trainer later generated
families or new DSPy programs. It only proves the execution-stage runtime and queue-handoff
behavior.

## Repository-native verification executed in this turn

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` → `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` → `pass` (`45 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test` → `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` → `pass`

## Checks not executed in this turn

- no live Azure Blob inspection was possible from this shell because Azure storage credentials were
  not available in the current local environment
- `make coverage` was not rerun
- no UI or notebook execution suite exists/reran for this turn

## Current conclusion

This rerun confirms that two important live fixes really landed:

- compact prompt-lineage sanitation works
- duplicate runner-side trusted handoff is gone

But the main family-first runtime goal is still missing in live execution:

- no compiled DSPy bundle resolved
- no family match occurred
- no family artifact was selected
- reformulation still collapsed to identity

And a new practical problem dominates the run cost:

- token usage exploded because the same `queue_and_slug` resume lane kept accumulating Codex
  transcript state across repeated reruns of the same prompt

## Highest-value next fixes

1. make the deployed proxy actually see the staged bundle/program/family artifacts so
   `bundle_version`, `program_path`, and `program_loaded` stop staying null
2. reduce live token inflation by forcing a fresh lane for reruns of the same verification prompt,
   or otherwise resetting the resumed Codex session lineage before repeated validation runs
3. strip dataset execution scaffolding earlier, before the raw `codex exec` prompt is formed, so
   the first Codex turn itself is not polluted even when the compact trainer-facing trace is clean
