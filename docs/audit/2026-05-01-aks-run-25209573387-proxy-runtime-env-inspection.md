# 2026-05-01 AKS Run 25209573387 Proxy Runtime Env Inspection

## Summary

- Inspected the newest dataset AKS workflow run `25209573387` through GitHub Actions metadata, the
  user-supplied deployment log, the locally re-exported artifacts under `../dataset/artifacts`,
  and live Azure Blob storage.
- Confirmed that the worker used the new image tag `prompt-executor:20260501-073125`, so this run
  is newer than the prior resolver-fix deployment attempts.
- Confirmed that the repo-rag proxy no longer fails at project-root resolution. The worker result
  now includes:
  - `repo_rag_proxy_status`
  - `repo_rag_codex_proxy_last.json`
  - `repo_rag_codex_proxy_stderr.log`
  - `repo_rag_codex_proxy_stdout.log`
- Confirmed that the proxy still does **not** mediate the Codex call, because `repo-rag` fails to
  start its local Azure OpenAI runtime:
  - `RuntimeError: Missing Azure OpenAI runtime settings: AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_CHAT_COMPLETIONS_URI, AZURE_OPENAI_DEPLOYMENT_NAME or AZURE_OPENAI_CHAT_COMPLETIONS_URI, AZURE_OPENAI_API_VERSION.`
- Confirmed that both live Blob containers remain empty after this run:
  - `repo-rag-training-traces`
  - `repo-rag-bundles`

## Main Interpretation

- The previously fixed `project_root_unresolved` blocker is gone.
- The next blocker is environment/config translation:
  - the worker can launch `repo-rag serve-codex-proxy`
  - but the proxy runtime expects Azure OpenAI chat/runtime variables that are not present in the
    worker environment handed to `repo-rag`
- Because the proxy process crashes before mediation begins, the worker falls back to plain
  `codex_cli`, which leaves `trace_handoff_status` unset and exports no trainer trace.

## Artifact Evidence

From `../dataset/artifacts/upload_summary.json`:

- `execution_id: "25209573387_20260501_095133"`
- `azure_path: "executions/25209573387_20260501_095133"`

From `../dataset/artifacts/redis_results.json`:

- `backend_used: "codex_cli"`
- `method_used: "codex_cli"`
- `artifacts_count: 5`
- `warnings` includes:
  - `Repo-rag Codex proxy failed to start; falling back to direct Codex execution.`
- `repo_rag_proxy_status` is present and equals:
  - `{"mediation_mode":"passthrough","warnings":["Repo-rag Codex proxy failed to start; falling back to direct Codex execution."]}`
- `artifacts` include:
  - `repo_rag_codex_proxy_last.json`
  - `repo_rag_codex_proxy_stderr.log`
  - `repo_rag_codex_proxy_stdout.log`
  - `codex_response.txt`
  - the attached spec `.docx`

From `repo_rag_codex_proxy_stderr.log`:

- the proxy traceback ends in:
  - `resolve_azure_openai_runtime(dict(os.environ))`
  - `RuntimeError: Missing Azure OpenAI runtime settings: AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_CHAT_COMPLETIONS_URI, AZURE_OPENAI_DEPLOYMENT_NAME or AZURE_OPENAI_CHAT_COMPLETIONS_URI, AZURE_OPENAI_API_VERSION.`

From `repo_rag_codex_proxy_last.json`:

- `mediation_mode: "passthrough"`
- warning only:
  - `Repo-rag Codex proxy failed to start; falling back to direct Codex execution.`

## GitHub Actions Evidence

- `gh run view 25209573387 --json ... -R realagiorganization/dataset` — pass
  - `workflowName: Parallel Prompt Execution on Azure AKS`
  - `headBranch: main`
  - `headSha: 5f1204a308ab05dcf0dc56f22cde7edf2662b50d`
  - `conclusion: success`
- User-supplied deploy log excerpt — reviewed
  - `Deploying queue initializer with prebuilt image: .../queue-initializer:20260501-073125`
  - `Using prebuilt worker image: .../prompt-executor:20260501-073125`
  - `Success breakdown: codex_cli: 1`
  - `Rehydrated 3 inline artifacts`

## Azure Evidence

- `az account show -o json` — pass
- `az storage blob list --account-name realagistorage --account-key "$KEY" --container-name repo-rag-training-traces --num-results 10 -o json` — pass, empty list
- `az storage blob list --account-name realagistorage --account-key "$KEY" --container-name repo-rag-bundles --num-results 10 -o json` — pass, empty list

## Why Blob Still Looks Empty

- `repo-rag-training-traces` is empty because no proxy-backed trace was ever produced.
- `repo-rag-bundles` is still not the right success signal for this stage; it only fills during a
  separate publish/promote bundle flow.
- The immediate failure is earlier:
  - `repo-rag serve-codex-proxy` cannot bootstrap its Azure runtime
  - so the worker never reaches retrieval/DSPy mediation
  - so there is nothing to enqueue or export as a trainer trace

## Practical Conclusion

- The runtime chain has advanced one step:
  - source/image drift resolved
  - flattened `/app/*.py` layout resolver bug resolved
- The current blocker is now specifically the missing Azure OpenAI env contract for the repo-rag
  proxy subprocess.
- The next code fix should ensure the prompt-executor passes a repo-rag-compatible Azure runtime
  environment when launching `repo-rag serve-codex-proxy`, or teach repo-rag to derive that
  runtime from the existing Codex Azure config payload already present in the worker.

## Checks Executed This Turn

Artifact inspection:

- `python - <<'PY' ... ../dataset/artifacts/upload_summary.json ../dataset/artifacts/redis_results.json ... PY` — pass
- `tar -xzf ../dataset/artifacts/all_artifacts.tar.gz ...` — pass
- `python - <<'PY' ... repo_rag_proxy_status ... PY` — pass

External inspection:

- `gh run view 25209573387 --json ... -R realagiorganization/dataset` — pass
- `az account show -o json` — pass
- Azure Blob inspection commands listed above — pass

## Missing Or Not Run This Turn

- Coverage: not run
- Lint: not run
- Type checking: no dedicated type-check suite was run
- UI validation: no dedicated UI suite exists for this repository surface
- End-to-end AKS rerun after an Azure-runtime-env fix: not run
