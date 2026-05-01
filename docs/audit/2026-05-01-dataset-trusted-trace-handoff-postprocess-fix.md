# Dataset Trusted Trace Handoff Post-Processing Fix

- Date: `2026-05-01`
- Scope: downstream `../dataset` secure trainer-trace handoff after AKS worker completion
- Preceding blocker note: `2026-05-01-aks-run-25212955759-trace-handoff-secret-gap.md`

## Summary

The latest live AKS evidence showed that worker-side repo-RAG mediation and trace export were
already healthy, but trainer-side trace handoff still stopped at
`trace_handoff_status = "skipped"` because the generated `repo-rag-storage-config` secret carried
container names without Azure Blob credentials. Those credentials could be injected into the worker,
but that would let `codex exec` read them from its own process environment.

The downstream `../dataset` fix implemented in this turn takes the safer path:

- keep worker-side `codex` / repo-RAG execution credential-minimal
- keep worker-side trace export in place
- perform trainer-side Blob + Queue handoff in the trusted deploy/post-processing stage after
  `execution_artifacts` rehydration, where Azure storage credentials are already available

This preserves the queue/blob format without exposing trainer storage secrets inside the
prompt-worker container that executes Codex.

## Downstream Code Changes

Changed files in `../dataset`:

- `aks_module_generator/templates/deployment_script/part_4.txt`
- `aks_modules/deploy.sh`
- `tests/unit/test_deployment_script_template_regressions.py`

Behavioral change:

- new `Step 7.3b: Trusted repo-rag trace handoff` runs after inline artifact rehydration
- it scans `execution_artifacts/*/artifacts/*/repo_rag_trace.json`
- it uploads queued trace payloads to `repo-rag-training-traces`
- it emits Azure queue messages to `repo-rag-training`
- it writes `repo_rag_trace_enqueue.json` plus command/stdout/stderr artifacts back into the
  rehydrated prompt artifact directory
- it updates `repo_rag_backend.json` and consolidated result files so the uploaded artifact set
  reflects `trace_handoff_status = queued` or `failed`

## Security Posture

This fix intentionally avoids the earlier shortcut of injecting `AZURE_STORAGE_ACCOUNT`,
`AZURE_STORAGE_KEY`, or `AZURE_STORAGE_CONNECTION_STRING` into the worker pod solely to satisfy
repo-RAG trace handoff.

Under the new design:

- worker pods still do not need trainer storage credentials
- Codex does not gain read access to Blob/Queue secrets through the worker process environment
- the trusted deploy stage remains the only execution boundary that touches the trainer-trace store

## Verification Run In This Turn

Executed against `../dataset`:

- `bash -n aks_modules/deploy.sh` — `pass`
- `python -m compileall aks_module_generator tests/unit/test_deployment_script_template_regressions.py tests/test_aks_module_generator_generate_modules.py tests/test_aks_module_generator_manifests.py` — `pass`
- `uv run pytest tests/unit/test_deployment_script_template_regressions.py tests/test_aks_module_generator_generate_modules.py::test_generate_modules_writes_bash_valid_deploy_script tests/test_aks_module_generator_manifests.py::test_deployment_script -q` — `15 passed`

Repository-local checks re-run here:

- `uv run python -m compileall src tests` — `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — `37 passed`
- `uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`
- `make files-sync` — `pass`
- `make verify-surfaces` — `pass`

## Remaining Runtime Proof

This turn did not include a new live AKS rerun after the downstream post-processing fix. The next
production-like verification should confirm all three outcomes together:

1. `repo_rag_trace_enqueue.json` appears in uploaded execution artifacts
2. `repo-rag-training-traces` is no longer empty
3. `trace_handoff_status` in consolidated uploaded results changes from `skipped` to `queued`
