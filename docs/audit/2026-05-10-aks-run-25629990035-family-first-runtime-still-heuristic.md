# Repository audit note for 2026-05-10 AKS run 25629990035 family-first runtime still heuristic

## Scope

- Inspect the latest execution artifacts uploaded under `../dataset/artifacts` after the post-hotfix
  rerun.
- Compare the observed live behavior against the intended family-first DSPy runtime contract.

## Inspected run

- `execution_id`: `25629990035_20260510_134639`
- Azure execution path from `upload_summary.json`:
  `executions/25629990035_20260510_134639`

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

### 2. Prompt-token growth stayed controlled

- `prompt_tokens = 27193`
- previous inspected baseline in the same resume lane:
  `25803`
- delta versus previous:
  - `+1390`
  - `+5.387%`

This is materially better than the earlier oversized runs. The major transcript-bloat regression is
not present in this execution.

### 3. Per-turn batch export and per-turn batch enqueue both succeeded

The worker now persisted and handled the compact turn batch:

- `repo_rag_turn_traces/20260510T134451Z/manifest.json`
- `repo_rag_turn_traces/20260510T134451Z/turn-000.json`
- `repo_rag_turn_trace_export_batch.json`
- `repo_rag_turn_trace_enqueue_batch.json`

Observed statuses:

- `repo_rag_turn_trace_export_batch.json`
  - `command_status = "success"`
  - `exported_count = 1`
- `repo_rag_turn_trace_enqueue_batch.json`
  - `command_status = "success"`
  - `handled_count = 1`

The batch queue artifact metadata shows a generated queue item at:

- `queued/repo-rag-training/20260510T134502Z-worker-0-prompts_debt_relief-p00000-cfc990-realagiorganization_national-debt-relief-20260510T134451Z-0.json`

### 4. Compact answer persistence is still working

`turn-000.json` carries a compact answer confirming that the README already contains the requested
demo GIF and that local verification passed. The run no longer needs the full `codex_response.txt`
transcript as the primary answer payload.

### 5. Final per-turn metric fields are present

The per-turn trace now records:

- `mediation_metric_hits = 1`
- `mediation_metric_total = 1`

That means final `hits / total` is now reaching the compact turn artifact, even though the family
selection fields are still empty.

## What still did not work

### 1. The live runtime still did not load a compiled DSPy bundle

Both `repo_rag_codex_proxy_last.json` and `turn-000.json` show heuristic fallback instead of family
artifact execution:

- `dspy_status = "heuristic"`
- warning:
  `DSPy mediation was unavailable; using heuristic synthesis instead. (No compiled DSPy bundle is available.)`
- `bundle_version = null`
- `program_path = null`
- `program_loaded = false`

So the live proxy still did **not** activate the intended family-first DSPy runtime path.

### 2. Family routing fields are still absent at runtime

The trace carries no family match:

- `prompt_family_id = null`
- `prompt_family_similarity = null`
- `prompt_family_band = null`
- `family_runtime_hit_rate = null`
- `family_artifact_hit_rate = null`
- `family_artifact_selected = null`

This means the proxy did **not** do the agreed runtime step:

1. load bundle
2. compare against fathers
3. pick the best family above threshold
4. run the family artifact

### 3. Prompt reformulation is still not happening in practice

In both the proxy status and the compact turn trace:

- `original_prompt == reformulated_prompt`

So the intended contract step

1. incoming prompt
2. prompt reformulation
3. DSPy mediation on the reformulated lineage

is still collapsing to identity at runtime for this case.

### 4. The forwarded tail still leaks into all prompt-lineage fields

The prompt is no longer carrying the full dataset execution envelope, but it still includes the
Discord forwarding tail:

- `[forwarded] @Tyler ATTTENTION. @|DT| drybox`

This leakage is still present in:

- `question`
- `original_prompt`
- `reformulated_prompt`
- the user entry in `command_trace`

So prompt normalization improved, but it is still incomplete.

## What behaved incorrectly

### 1. Both batch handoff and legacy handoff are still running

The run produced:

- successful per-turn batch enqueue at
  `queued/repo-rag-training/20260510T134502Z-worker-0-prompts_debt_relief-p00000-cfc990-realagiorganization_national-debt-relief-20260510T134451Z-0.json`
- successful legacy single-trace enqueue at
  `queued/repo-rag-training/20260510T134638Z-prompts_debt_relief-p00000-cfc990.json`

That means the same execution is still handed off twice:

1. the intended compact per-turn batch item
2. the old coarse run-level queue item

This duplication is not part of the intended family-first contract.

### 2. The run is still resumed, not fresh

- `codex_session_state.session_mode = "resumed"`
- `lane_source = "auto:queue_and_slug"`

This did not create a large token spike in this run, but it still means the execution is not a
clean fresh-start verification of the family-first path.

## What cannot be concluded from these local artifacts alone

The inspected files under `../dataset/artifacts` are execution-phase artifacts only. They show:

- runtime mediation behavior
- trace export/enqueue behavior
- queue handoff artifacts

They do **not** contain the downstream trainer outputs from Azure Blob such as:

- `repo-rag-training-families`
- published family runtime programs inside `repo-rag-bundles`

So if family generation and DSPy program generation succeeded later on the trainer side, that is
compatible with these artifacts. It is simply not directly provable from this local execution dump.

## Current conclusion

This run is a meaningful improvement over the earlier broken live attempts:

- token growth stayed controlled
- compact per-turn trace batching worked
- batch enqueue now worked
- the trainer definitely received a compact turn trace

But the central family-first runtime goal is still not live:

- the proxy did not resolve a compiled DSPy bundle
- no family match happened at runtime
- no family artifact was selected
- prompt reformulation still collapsed to identity
- the forwarded tail still contaminates prompt lineage
- legacy single-trace handoff still duplicates the batch path

## Highest-value next fixes

1. make runtime bundle activation succeed in the deployed image so `bundle_version`,
   `program_path`, and `program_loaded` stop staying null
2. strip the forwarded Discord tail from all prompt-lineage fields, not only the old dataset
   execution envelope
3. stop emitting the legacy single-trace enqueue path once per-turn batch enqueue succeeds
