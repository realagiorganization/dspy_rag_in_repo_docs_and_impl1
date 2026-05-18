# Compact DSPy Mediation And Trace Escalation

Date: `2026-05-18`

## Change

This audit note now covers two adjacent runtime refinements from the same day:

1. the Codex proxy now injects a much more compact mediation block on successful repo-RAG/DSPy
   matches
2. successful family-artifact reuse no longer stays feedback-only; the current active policy emits
   `full_trace` directly for matched runs
3. the live prompt-executor and CLI surfaces now honor that contract instead of silently reverting
   matched runs back to `feedback_trace` or launching the proxy with stale mediation-budget
   defaults

## What Changed

- reduced the default proxy mediation hot-path footprint:
  - preview count `4 -> 2`
  - essentials count `3 -> 2`
  - token budgets `700/280 -> 420/180`
- rewrote the injected developer mediation message to keep only:
  - execution mode
  - family id when known
  - one compact prompt line
  - one compact summary
  - up to two file hints
  - at most one evidence snippet
  - at most one note
- removed the reuse-path pruning that previously deleted earlier local turn traces for the same
  prompt once a family artifact succeeded
- simplified reuse-path admission:
  - successful family-artifact reuse now emits `full_trace`
  - the earlier replay similarity floor and deterministic sampling gate were removed
- persisted `trainer_signal_reason` alongside the trace so exported artifacts can explain whether a
  trace came from family reuse or fresh/fallback mediation
- aligned the `serve-codex-proxy` CLI defaults with the active compact mediation contract:
  - token budget `420`
  - trivial token budget `180`
  - essentials count `2`
- removed the dataset-side worker downgrade that had still been rewriting successful reused family
  traces back to `feedback_trace` after proxy export

## Why

The previous runtime behavior had two opposing problems:

- DSPy reuse added too much prompt overhead, especially via a long developer message plus multiple
  evidence snippets
- successful family reuse fed only `feedback_trace` into the trainer, which risked freezing family
  replay sets around older exemplars even when newer matched executions might be better training
  material

This turn keeps the compact mediation payload reduction, but the trace policy is now intentionally
greedy for learning: successful family reuse is replay-visible again. That aligns with the current
product requirement that runtime-side matching must not block potentially better traces from
reaching later DSPy recompilation, and it keeps admission decisions entirely on the runtime side
instead of adding trainer-side pairwise replay comparisons.

The live AKS inspection during this follow-up showed why the previous code-only change had not
taken effect end to end: the prompt-executor worker still contained a post-proxy rule that mapped
successful reused family artifacts back to `feedback_trace`, and the CLI surface that launches the
proxy still exposed the old `700/280/3` defaults even though the runtime constants had already been
reduced to `420/180/2`. Fixing those two deployment-facing surfaces restores the intended runtime
contract.

## Verification

Executed in the current turn:

- `uv run python -m compileall src tests`
- `cd ../dataset && pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py -q`
- `uv run pytest tests/test_codex_proxy.py -q`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make quality`

Observed:

- `compileall` passed
- dataset worker regression slice passed as `24 passed`
- `tests/test_codex_proxy.py` passed as `27 passed`
- smoke test passed
- Rust build passed
- `make quality` passed with:
  - `373 passed`
  - `3 skipped`
  - total coverage `81.54%`

## Scope Notes

- This note covers repository-local correctness of the compact mediation payload and trainer signal
  split.
- This note now also records the live AKS root cause that explained the mismatch seen in fresh
  execution artifacts before this fix.
