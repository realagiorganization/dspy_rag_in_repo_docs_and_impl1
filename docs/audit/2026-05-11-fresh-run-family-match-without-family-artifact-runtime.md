# 2026-05-11 Fresh Run Matches Families but Does Not Activate Family Artifacts at Runtime

## Context

The user asked for a verification pass over the latest execution artifacts exported to
`../dataset/artifacts/`, with special attention to:

- whether DSPy worked correctly
- whether prompt families were used
- whether token spend looked valid
- whether the family-first DSPy cycle completed end-to-end

This note records the artifact inspection for the fresh run plus a same-turn local verification
baseline from this repository checkout.

## Artifact-Backed Findings

### 1. The execution itself succeeded, but runtime DSPy stayed on the heuristic path

The latest exported result in `../dataset/artifacts/redis_results.json` reports:

- `success = true`
- `backend_used = codex_cli_repo_rag_proxy`
- `trace_handoff_status = queued`
- `acceptance_status = candidate`
- `execution_time = 2310.248155`
- `prompt_tokens = 248870`

The execution therefore completed and did hand off a training trace, but the prompt-token spend was
very high for a run that was supposed to benefit from family-backed DSPy runtime reuse.

### 2. Prompt-family matching happened, but family artifacts were not used

`repo_rag_codex_proxy_last.json` shows:

- `prompt_family_id = pf-c93cbc537b800fac`
- `prompt_family_similarity = 1.0`
- `prompt_family_band = "match"`
- `family_artifact_selected = false`
- `bundle_version = null`
- `dspy_status = "heuristic"`
- `reformulation_status = "identity"`

So the proxy **did** find an existing family match at runtime, and the match quality was maximal
(`1.0`), but it still failed to load or select a family runtime artifact. The run therefore stayed
on heuristic mediation instead of the intended family-first DSPy path.

### 3. Turn-level traces were captured, and reformulation behavior was mixed

The archive contains a turn batch under:

- `repo_rag_turn_traces/20260511T093405Z/`

That batch contains `44` turn JSON files plus a batch manifest.

Aggregating the turn traces shows:

- `19` turns with `reformulation_status = "dspy"`
- `25` turns with `reformulation_status = "identity"`
- `26` turns where `original_prompt == reformulated_prompt`

So DSPy-style reformulation was not completely absent, but it was inconsistent and it did not
translate into family-artifact execution.

At the same time, the compact and trainer-facing surfaces still disagree:

- the compact turn-trace files do not consistently carry the family metadata
- the exported trainer-facing trace files under `artifacts/traces/*.json` do carry it

Aggregating the exported trace files shows:

- `44` exported traces
- `44` traces with a `prompt_family_id`
- `25` traces with `prompt_family_band = "match"`
- `19` traces with `prompt_family_band = "new"`
- similarity range `0.5 .. 1.0`
- `family_artifact_selected_count = 0`
- no non-null `bundle_version`

This means the family lookup stage is partially alive, but the bridge from family lookup to actual
family-artifact execution is still broken.

### 4. The run still queued the legacy single coarse trace

The batch manifest exists:

- `repo_rag_turn_trace_batch_manifest.json`

But the trainer queue artifacts that survived into the archive are still the legacy single-trace
handoff surfaces:

- `trusted_trace_handoff_summary.json`
- `repo_rag_trace_enqueue.json`
- `repo_rag_trace_enqueue_stdout.txt`

Those files show the queued blob:

- `queued/repo-rag-training/20260511T101344Z-prompts_debt_relief-p00000-cfc990.json`

and `repo_rag_trace_enqueue.json` still points at:

- `source_trace_path = execution_artifacts/.../repo_rag_codex_proxy_payload.json`

instead of a per-turn exported trace file. So although the run captured `44` turn traces, the
observable queue handoff in this artifact dump is still the old coarse path.

### 5. Token spend was not healthy for a family-assisted run

This run spent:

- `248870` prompt tokens

The same artifact set reports the previous fresh baseline as:

- `baseline_prompt_tokens = 69812`

So the delta was:

- `prompt_tokens_delta = 179058`
- `prompt_tokens_delta_ratio = 2.56486`

This is too large for a run where the family-first DSPy runtime should have reused an existing
family artifact on the very first request. The evidence points to the main Codex rollout doing
real work, but the cost is still not “healthy” in the intended architecture because the runtime
never crossed from family-match into family-artifact execution.

### 6. The full family-first DSPy cycle did not complete

Against the intended design, the cycle stopped short at runtime:

- original prompt captured: **yes**
- reformulated prompt generated: **not really**; proxy status says `identity`
- family lookup by similarity: **yes**
- family artifact / bundle selected: **no**
- runtime DSPy mediation injected: **no**
- per-turn traces captured: **yes**
- queue handoff happened: **yes**, but visibly through the legacy coarse trace path
- runtime used the family-backed DSPy artifact: **no**

So the cycle did **not** complete end-to-end.

## Specific Bugs / Gaps Confirmed by This Run

1. **Family match without family artifact activation**
   - exact family match (`1.0`) still did not activate the runtime artifact
   - `bundle_version` stayed null

2. **Reformulation regressed to identity**
   - `original_prompt == reformulated_prompt` in proxy status

3. **Batch handoff remains incomplete/inconsistent**
   - turn batch exists locally
   - queue-visible artifact is still the legacy single trace

4. **Compact trace surfaces are missing family fields**
   - family metadata exists in `artifacts/traces/*.json`
   - the compact `repo_rag_turn_traces/...` files do not consistently mirror it

## Local Verification Baseline

Executed in this repository checkout during the same turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `47 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`

## Verification Categories Not Executed in This Turn

- `coverage`
  - not run
- lint / formatting / type checking
  - not run in this turn
- live AKS inspection
  - not run in this turn
- downstream trainer publish verification against Azure Blob
  - not run in this turn

## Conclusion

The fresh run shows meaningful progress over earlier broken states:

- family matching is now visible
- turn-level capture is working
- queue handoff still happens

But DSPy did **not** work correctly in the intended family-first sense:

- prompt families were recognized
- family runtime artifacts were **not** used
- bundle activation still failed
- token spend was therefore not healthy for the target architecture
- the full family-first DSPy cycle did **not** complete end-to-end

## Next Operator Focus

The next fixes should target the execution/runtime path, not the trace capture surface:

1. make exact family matches activate a family runtime artifact
2. make reformulation behavior consistent and keep it coupled to family-artifact selection
3. make the per-turn batch handoff the authoritative queue/export path instead of the coarse
   single-trace fallback
