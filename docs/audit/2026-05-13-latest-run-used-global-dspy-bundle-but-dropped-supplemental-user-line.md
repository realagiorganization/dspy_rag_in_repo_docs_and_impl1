# 2026-05-13 Latest Run Used Global DSPy Bundle But Dropped Supplemental User Line

## Scope

Inspect the latest `../dataset/artifacts` run to answer two questions:

1. whether the worker really used the DSPy family library, and specifically whether it used the
   family-state version the user expected (`20260513T134936Z`)
2. why the prompt that reached `codex exec` omitted the user-supplied trailing line
   `This is a test run, no development or installation required.`

## Artifact Set

Inspected:

- `../dataset/artifacts/redis_results.json`
- `../dataset/artifacts/upload_summary.json`
- `../dataset/artifacts/all_artifacts.tar.gz`
- `../dataset/artifacts/processed.tar.gz`

Key runtime files inside `all_artifacts.tar.gz`:

- `repo_rag_codex_proxy_last.json`
- `repo_rag_codex_proxy_payload.json`
- `repo_rag_turn_trace_batch_manifest.json`
- `repo_rag_turn_trace_enqueue_batch.json`
- `repo_rag_turn_traces/20260513T144725Z/*.json`
- `prompt_artifacts/prompts_debt_relief-p00000-f4638d.txt`
- `codex_response.txt`

## What Worked

- The worker run itself succeeded:
  - `success=true`
  - `backend_used=codex_cli_repo_rag_proxy`
  - `trace_handoff_status=queued`
  - `artifacts_count=59`
- The per-turn batch path worked:
  - `repo_rag_turn_trace_batch_manifest.json` listed `17` turn traces
  - `repo_rag_turn_trace_enqueue_batch.json` reported `handled_count=17`, `failed_count=0`
- DSPy reformulation ran:
  - `repo_rag_codex_proxy_last.json` recorded `dspy_status="success"`
  - `reformulation_status="dspy"`
  - `dspy_lm_model="azure/gpt-4o"`
- Family lookup also ran and matched the stored family:
  - `prompt_family_id="pf-9287fa96e7c8f8ff"`
  - `prompt_family_similarity=1.0`
  - `prompt_family_band="match"`

## What Bundle Was Actually Used

The worker did **not** use raw family-state version `20260513T134936Z` directly.

Instead, the runtime used the published DSPy bundle:

- `bundle_version="20260513T135020940018Z"`
- `program_path="artifacts/dspy/remote/20260513T135020940018Z/program.json"`

This means the live runtime contract still works as:

- prompt family state (`repo-rag-training-families`) provides family lookup and family artifacts
- published bundle (`repo-rag-bundles`) provides the actual compiled runtime program that the
  worker loads

So the expected family-state version `20260513T134936Z` was relevant as the family library source,
but the worker itself loaded bundle version `20260513T135020940018Z`.

## What Did Not Work

Even though the family matched, the worker still did **not** enter the family-artifact execution
path:

- `family_artifact_selected=false`
- `family_runtime_hit_rate=1.0`
- `family_artifact_hit_rate=0.0`

So the latest run used:

- DSPy reformulation
- family lookup
- global published DSPy bundle

but **not** the matched family-specific runtime artifact.

In other words, the DSPy library was used **partially**, not fully:

- yes: lookup and bundle-backed DSPy runtime path were active
- no: family-specific artifact reuse did not happen

## Prompt Mismatch Finding

The user-supplied extra line:

- `This is a test run, no development or installation required.`

was present upstream in the prompt artifact:

- `prompt_artifacts/prompts_debt_relief-p00000-f4638d.txt`
- message `[3]` in the aggregated Discord transcript

But it was absent in all downstream runtime surfaces:

- `codex_response.txt`
- `repo_rag_codex_proxy_last.json.original_prompt`
- `repo_rag_turn_traces/.../*.json.original_prompt`

The prompt that actually reached `codex exec` was:

- the older base task prompt without the trailing test-run sentence

This shows the loss happened **before** DSPy family reuse.

There is no evidence in this run that the DSPy family library replaced the user's prompt with an
older library prompt. The artifact evidence shows instead:

- the aggregated Discord/source artifact still had the extra line
- the execution prompt handed to `codex exec` already did not have it
- therefore the truncation happened in prompt extraction / prompt assembly before runtime family
  lookup

## Token Spend Interpretation

- `prompt_tokens=382078`
- `completion_tokens=0`
- `total_tokens=382078`

This is high, but for this run it looks tied to real work in `codex_response.txt`:

- long execution transcript
- Playwright/browser automation
- repeated commands and repo operations

So this run does **not** look like a pure trainer-burn or prompt-envelope blow-up.

## Verification

Ran:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

Results:

- compile step passed
- utility / BDD tests: `52 passed`
- smoke test passed
- cargo build passed

## Current Interpretation

- The latest worker run **did** use DSPy in the broad sense:
  - DSPy reformulation ran
  - DSPy global bundle loaded
  - family lookup matched
- The latest worker run **did not** use the matched family-specific runtime artifact.
- The missing `This is a test run...` line is a separate prompt-assembly bug and is **not**
  explained by the DSPy library substituting an old family prompt.

## Local Fix Prepared

The repository now carries a local fix for both defects uncovered by this run:

- Prompt cleaning no longer removes every line after the first forwarded Discord message. The
  forwarded marker and its attachment companion lines are stripped line-by-line, while later
  user-authored lines remain part of `original_prompt`, `reformulated_prompt`, and prompt-like
  `command_trace` entries.
- Bundle family-artifact selection now compares like-for-like metrics. The runtime bridge uses the
  family artifact's persisted trace `hit_rate` (metric 1) and treats `benchmark_pass_rate` as
  diagnostic only, so an exact family match is no longer disabled merely because the compiled
  artifact's benchmark summary omitted or lowered a separate pass-rate field.
