# 2026-05-15 Feedback Trace Phase 1

## Summary

This turn started and extended the pipeline correction that the family-first DSPy contract still
lacked: runtime reuse of a compiled family artifact no longer means “no trainer signal at all,”
and the runtime now has a controlled way to escape pure exploitation.

Phase 1 introduced an explicit split between:

- `full_trace` for fresh / fallback / exploration replay traces
- `feedback_trace` for successful family-artifact reuse

That change closes the architectural hole where DSPy could succeed repeatedly in production while
trainer learned almost nothing from those successful reuse turns.

The same turn now also adds a Phase-2 routing slice: compiled family artifacts can be
deterministically bypassed for low-rate controlled exploration so the runtime occasionally emits
non-family `full_trace` examples even when a family match exists.

The first Phase-3 routing slice is also in place: family matching now scores a new prompt against
the stored prompt profile of the family, not only the current father text.

## Runtime / Trace Contract

The runtime trace schema now carries `trainer_signal_kind`, and stored trace records persist that
same field. Worker-side Codex proxy payloads now mark:

- `feedback_trace` when `family_artifact_selected=true` and `dspy_status=success`
- `full_trace` otherwise

The local proxy runtime now also persists one compact feedback trace for successful family reuse
instead of suppressing trainer-visible output completely, while still avoiding lineage-batch replay
growth for that path.

## Trainer Change

`materialize_training_candidates()` now separates the two signal classes:

- `full_trace` still updates `family_records` and marks the family dirty
- `feedback_trace` updates `family_feedback_metric`, `family_feedback_count`, and the persisted
  runtime artifact’s `predicted_hit_rate` without expanding the replay set or forcing recompile

That means trainer-side learning can now improve runtime priors from successful reuse traffic
without poisoning the family replay corpus with every reuse turn.

## Runtime Gating Change

`codex_proxy.py` now prefers the feedback-aware predicted family hit-rate when deciding whether a
matched compiled family artifact should still be trusted for the next turn. The previous baseline
was replay-set only; the new baseline can incorporate accumulated reuse feedback.

The newest slice hardens that math further. Family state now persists one combined
`family_success_metric` that merges replay evidence and reuse feedback into a posterior profile
with:

- `posterior_mean`
- `lower_bound`
- `uncertainty`

Runtime artifact metadata now carries those same fields, and proxy gating prefers the conservative
`lower_bound` when deciding whether a family artifact underperforms its current family baseline.
The dataset worker handoff now mirrors those fields into the trainer-facing `repo_rag_codex_proxy`
payload as well, so queued/imported traces do not lose `predicted_hit_rate`,
`predicted_hit_rate_lower_bound`, `prediction_uncertainty`, or `family_feedback_count` between
runtime and trainer.

The proxy now also accepts a deterministic `family_exploration_rate` knob. When the matched family
artifact would otherwise be reused, the proxy derives a stable hash-based roll from the prompt,
family id, and bundle version; if that roll falls below the configured rate, the proxy bypasses
the family artifact and uses the fresh/global mediation path instead. The default dataset worker
spec now carries `0.05` as the low exploration rate.

## Verification

Configured / repo-native checks run in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_codex_proxy.py -k 'persist_turn_trace'` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_training_samples.py -k 'feedback_trace or keeps_prompt_reformulation_and_command_trace'` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_codex_proxy.py -k 'controlled_exploration or persist_turn_trace or lower_bound_baseline or underperforms'` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_training_samples.py -k 'feedback_trace or variant_not_only_father'` — `pass`
- `cd ../dataset && .venv/bin/python -m compileall docker/prompt-executor/worker_execution_prompt.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py` — `pass`
- `cd ../dataset && .venv/bin/pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py -k 'pid-codex or stale_turn_trace_batch_when_final_proxy_reuses_family_artifact'` — `pass`
- `cd ../dataset && .venv/bin/pytest tests/unit/test_deployment_script_template_regressions.py -k 'trusted_trace_handoff_after_rehydration'` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`
- `cd ../dataset && .venv/bin/pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py -k 'pid-codex or stale_turn_trace_batch_when_final_proxy_reuses_family_artifact'` — `pass`
- `cd ../dataset && .venv/bin/pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py -k 'proxy_spec or pid-codex or stale_turn_trace_batch_when_final_proxy_reuses_family_artifact'` — `pass`
- `cd ../dataset/submodules/dspy_rag_in_repo_docs_and_impl1 && UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` — `pass`
- `cd ../dataset/submodules/dspy_rag_in_repo_docs_and_impl1 && UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_codex_proxy.py -k 'controlled_exploration or persist_turn_trace'` — `pass`
- `cd ../dataset/submodules/dspy_rag_in_repo_docs_and_impl1 && UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_training_samples.py -k 'feedback_trace or keeps_prompt_reformulation_and_command_trace'` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_training_samples.py -k 'variant_not_only_father or feedback_trace or keeps_prompt_reformulation_and_command_trace'` — `pass`
- `cd ../dataset/submodules/dspy_rag_in_repo_docs_and_impl1 && UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_training_samples.py -k 'variant_not_only_father or feedback_trace or keeps_prompt_reformulation_and_command_trace'` — `pass`

## Remaining Work

This is still not the whole redesign. Remaining work for later turns:

- richer family routing than father-text similarity alone
- better predicted-success math than raw mean ratios
- a fully converged live deployment that proves worker images match the new source behavior
