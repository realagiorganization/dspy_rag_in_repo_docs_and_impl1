# 2026-05-15 Remote Bundle Authority And Lane Reset Hardening

## Summary

This turn fixed three worker-side defects that kept live AKS runs inconsistent with the intended
family-first DSPy contract:

- stale local bundle mirrors could still be reused after remote bundle cleanup
- trusted queue handoff could serialize a weaker outer payload than the final runtime trace
- Codex lane `reset` reused the old lane lifecycle counters instead of starting a new lifecycle

## Runtime Change

`run_bundle_inspection()` now treats the remote Azure bundle channel and remote bundle versions as
authoritative whenever bundle blob storage is configured. If the remote `stable` channel or a
requested remote bundle version is missing, the worker no longer falls back to a local staged
mirror and claim that an old bundle is still available.

`codex_proxy.py` follows the same rule for bundle-version hints, family-registry resolution, and
program-path lookup. Remote channel absence now means “no active bundle,” not “scan staged local
versions anyway.”

## Trace Handoff Change

Worker-side Codex proxy payloads now mirror the selected family/runtime fields on the outer
payload, not only inside the nested `trace` object. Trusted handoff also prefers
`repo_rag_trace.json` before the older envelope files and, when it wraps a raw runtime trace, it
copies the same family/runtime fields onto the outer trusted payload.

That closes the observed mismatch where local runtime artifacts showed:

- `prompt_family_id = <family>`
- `program_loaded = true`
- `family_artifact_selected = true`

but the queued/processed trace for trainer ingestion flattened back to null top-level routing
state.

## Lane Lifecycle Change

When worker restore logic decides to `reset` a lane because of:

- resumed-run threshold
- session-age threshold
- prompt-token growth threshold
- operator reset request
- resume-failure threshold

the worker now clears the persisted lane counters, usage baselines, transcript summaries, and
stored session identifiers before writing the new snapshot. The next persisted snapshot therefore
starts a new lane lifecycle instead of inheriting the old lane’s counters under a nominal reset.

## Verification

Configured checks run in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py -k 'remote_channel_state or remote_missing'` — `pass`
- `../dataset/.venv/bin/pytest ../dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py -k 'family_artifact or stale_turn_trace_batch'` — `pass`
- `../dataset/.venv/bin/pytest ../dataset/tests/unit/test_worker_codex_cli_exec_small.py -k 'resumed_run_threshold or prompt_token_growth_threshold or session_age_threshold'` — `pass`
- `../dataset/.venv/bin/pytest ../dataset/tests/unit/test_deployment_script_template_regressions.py -k 'trusted_trace_handoff_after_rehydration'` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_codex_proxy.py` — `pass`
- `uv run python -m compileall src ../dataset/docker/prompt-executor ../dataset/src/execution ../dataset/tests/unit` — `pass`

## Remaining Gap

This turn hardens the source-of-truth and lifecycle behavior, but it does not yet prove that the
next live AKS run will drop back to the smaller token footprint. The next artifact review should
confirm two things together:

- the worker does not reuse a stale local bundle after remote cleanup
- a hard lane reset no longer correlates with the same large-token pattern that motivated this fix
