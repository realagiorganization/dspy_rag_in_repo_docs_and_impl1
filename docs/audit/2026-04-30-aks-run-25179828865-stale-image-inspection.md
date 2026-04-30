# 2026-04-30 AKS Run 25179828865 Stale Image Inspection

## Summary

- Inspected the latest successful dataset AKS workflow run `25179828865` through both GitHub
  Actions metadata/logs and Azure Blob storage.
- Confirmed that `repo-rag-training-traces` and `repo-rag-bundles` are both empty in the live
  `realagistorage` account.
- Confirmed that the run itself completed successfully and uploaded normal execution artifacts to
  the `execution-artifacts` container, so this is not a general Azure storage outage.
- Confirmed that the workflow checked out dataset `main` at commit
  `989286259926b9ac84d45ae573f4a00ff42f565c`, whose merged commit message includes
  `Add codex proxy trace handoff`.
- Confirmed that the worker pods did **not** validate that head commit in practice because the
  workflow auto-selected and deployed the older prebuilt image `prompt-executor:20260430-123514`
  from ACR instead of rebuilding an image from the checked-out source.
- Confirmed from the uploaded worker results that the live worker execution path was plain
  `codex_cli`, not `codex_cli_repo_rag_proxy`: `backend_used` stayed `codex_cli`,
  `bundle_version` was `null`, `trace_handoff_status` was `null`, and no
  `repo_rag_proxy_status` payload was present.

## Why The Repo-RAG Containers Stayed Empty

- The live worker result downloaded from Azure
  `execution-artifacts/executions/25179828865_20260430_180242/redis_results.json` recorded:
  - `method_used: "codex_cli"`
  - `backend_used: "codex_cli"`
  - `bundle_version: null`
  - `trace_handoff_status: null`
  - only two artifacts: `codex_response.txt` and the attached `.docx`
- The `aks-execution` job log also showed:
  - `Using prebuilt image tag: 20260430-123514`
  - `Using prebuilt worker image: .../prompt-executor:20260430-123514`
  - `No artifacts in prompt-worker-0-...`
  - `No codex_response.txt found for worker-0, attempting inline rehydration from Redis results...`
- Because the worker never entered the repo-rag proxy backend, no trace export or trace enqueue step
  ran for this workflow execution. That leaves `repo-rag-training-traces` empty even though the
  checked-out repository source already contains the trace-handoff code.
- `repo-rag-bundles` remaining empty is still expected unless a separate trainer publish/promote
  cycle writes bundle artifacts.

## Main Interpretation

- This run is **not** evidence that the current head implementation of the Codex-proxy trace
  handoff is broken.
- This run **is** evidence that the current AKS workflow/runtime contract still allows a mismatch
  between:
  - the dataset commit checked out by GitHub Actions, and
  - the older prebuilt worker image actually deployed into AKS.
- Until the workflow rebuilds or pins a worker image known to include the new dataset code, a
  successful workflow run can still exercise stale runtime behavior and completely bypass the
  repo-rag mediation path.

## Azure Evidence

- Management-plane inspection:
  - `az account show -o json` — pass
  - `az storage account show --name realagistorage --query resourceGroup -o tsv` — pass
  - `az storage account keys list -g AzureQuantumCredit -n realagistorage --query '[0].value' -o tsv` — pass
- Data-plane inspection with account key:
  - `az storage blob list --account-name realagistorage --account-key "$KEY" --container-name repo-rag-training-traces ...` — pass, zero blobs returned
  - `az storage blob list --account-name realagistorage --account-key "$KEY" --container-name repo-rag-bundles ...` — pass, zero blobs returned
  - `az storage blob download --account-name realagistorage --account-key "$KEY" --container-name execution-artifacts --name executions/25179828865_20260430_180242/redis_results.json ...` — pass
  - `az storage blob download --account-name realagistorage --account-key "$KEY" --container-name execution-artifacts --name executions/25179828865_20260430_180242/processed.tar.gz ...` — pass

## GitHub Evidence

- `gh run view 25179828865 --json ... -R realagiorganization/dataset` — pass
  - `workflowName: Parallel Prompt Execution on Azure AKS`
  - `headBranch: main`
  - `headSha: 989286259926b9ac84d45ae573f4a00ff42f565c`
  - `conclusion: success`
- `gh api repos/realagiorganization/dataset/commits/989286259926b9ac84d45ae573f4a00ff42f565c` — pass
  - merged commit message includes `Add codex proxy trace handoff`
- `gh run view 25179828865 --job 73821903041 --log -R realagiorganization/dataset | rg ...` — pass
  - captured the prebuilt image tag selection and stale worker image deployment
  - captured the lack of worker artifact files and the inline Redis rehydration fallback

## Comparison With Prior Audit

- `2026-04-30-codex-proxy-trace-handoff.md` established that the default Codex path now exports
  and hands off traces in the dataset source tree.
- This newer note adds the missing deployment-layer evidence: the latest observed AKS workflow run
  did not actually execute that new worker code because it reused an older prompt-executor image.

## Checks Executed This Turn

Repo-local:

- `uv run python -m compileall src tests` — pass
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — pass (`37 passed`)
- `uv run repo-rag smoke-test` — pass
- `cargo build --manifest-path rust-cli/Cargo.toml` — pass

External inspection:

- `gh auth status` — pass
- `az account show -o json` — pass
- GitHub Actions run metadata/log inspection commands listed above — pass
- Azure Blob inspection and download commands listed above — pass

## Missing Or Not Run This Turn

- Coverage: not run
- Lint: not run
- Type checking: not run
- UI validation: no dedicated UI suite exists for this repository surface
- End-to-end rerun on a freshly rebuilt prompt-executor image: not run
- Trainer publish/promote cycle for bundle population: not run

## Practical Conclusion

- The user-facing statement for this run is:
  - the latest workflow did not validate the new repo-rag trace-handoff path,
  - the empty `repo-rag-training-traces` container is explained by a stale deployed worker image,
  - and the empty `repo-rag-bundles` container remains expected without a trainer publish cycle.
