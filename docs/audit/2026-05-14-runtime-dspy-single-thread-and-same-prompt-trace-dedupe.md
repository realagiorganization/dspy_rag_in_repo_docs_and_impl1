# 2026-05-14 Runtime DSPy Single-Thread And Same-Prompt Trace Dedupe

## Summary

Two runtime bugs remained after the latest family-first execution review:

- the proxy still fell back to heuristic mediation with the warning
  `dspy.settings can only be changed by the thread that initially configured it.`
- one outer prompt could still emit many trainer-facing trace snapshots in a single rollout

The local fix now addresses both.

## Runtime Change

`running_codex_proxy()` no longer uses a per-request `ThreadingHTTPServer`. It now runs the local
proxy on a single dedicated HTTP server thread, so all DSPy helper/runtime configuration stays on
one request-serving thread for the lifetime of the worker-side proxy process.

That matters because the current DSPy runtime still treats `dspy.settings.configure(...)` as
thread-affine state. When the proxy created a fresh request thread for later Codex turns, DSPy
could refuse to reconfigure and the worker dropped back to heuristic mode even after a family
artifact had already been matched.

## Trace Dedupe Change

The proxy now suppresses trainer-facing turn-trace export in two cases:

1. matched family reuse already succeeded:
   - `family_artifact_selected = true`
   - `dspy_status = success`
2. the worker sees the same outer prompt + same routing/runtime state more than once in the same
   rollout

The dedupe key intentionally ignores `command_trace` growth. That means one long Codex rollout for
one unchanged `original_prompt` no longer produces a new trainer trace just because the visible
command history grew from 6 steps to 20 steps.

## Expected Behavioral Effect

After redeploy:

- matched family reuse should stay on the family DSPy runtime path instead of falling into the
  heuristic warning due to thread-affinity
- same-prompt rollouts should stop exporting repeated trainer traces when the routing outcome did
  not semantically change
- trainer queue volume should drop for already-known prompt families

## Verification

Configured checks run in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_codex_proxy.py -q` — `23 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/codex_proxy.py tests/test_codex_proxy.py` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — `52 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`

Not run in this turn:

- coverage
- notebook execution
- deployment/integration rerun against live AKS after redeploy

## Remaining Gap

This is still a **local** fix until the new image is pushed and the worker path is exercised in a
fresh live run. The next run should confirm both:

- `dspy_status = success` without the thread-affinity warning
- fewer trusted queue items for one unchanged outer prompt
