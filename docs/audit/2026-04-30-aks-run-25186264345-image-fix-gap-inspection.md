# 2026-04-30 AKS Run 25186264345 Image/Fix Gap Inspection

## Summary

- Inspected the newer dataset AKS workflow run `25186264345` through GitHub Actions metadata, the
  user-supplied deployment log, local re-exported artifacts under `../dataset/artifacts`, and live
  Azure Blob storage.
- Confirmed that the run completed successfully on GitHub Actions and deployed the newer worker
  image tag `prompt-executor:20260430-183813`, so this run is not stale relative to the older
  `20260430-123514` image diagnosed earlier.
- Confirmed that `repo-rag-training-traces` and `repo-rag-bundles` are still empty in live Azure
  storage after this run.
- Confirmed from the local `redis_results.json` and the uploaded artifact tarball that the worker
  still executed plain `codex_cli`, not `codex_cli_repo_rag_proxy`: `backend_used` stayed
  `codex_cli`, `bundle_version` was `null`, `trace_handoff_status` was `null`, `warnings` stayed
  empty, and the result payload did not even include the `repo_rag_proxy_status` key.
- Confirmed that the workflow source checkout on `main` had already moved to merge commit
  `a6ae9addfe7a069d95e9a59f632340cb772a2ede`, whose commit message includes
  `Diagnose codex repo-rag proxy fallback`, but the deployed worker image tag
  `20260430-183813` was built earlier in the day before that diagnostic commit existed.

## Main Interpretation

- This run is newer than the previously stale `123514` deployment, but it still does **not**
  validate the latest diagnostic repo-rag fallback instrumentation.
- The decisive clue is the artifact schema itself:
  - if the `6af864e` diagnostic worker code had been present, the plain `codex_cli` fallback path
    should have surfaced `repo_rag_proxy_status` in the worker result envelope, even when the
    proxy layer was skipped
  - the actual result payload from this run has no `repo_rag_proxy_status` key at all
- That means the user's AKS rerun still exercised a worker image that predates the diagnostic
  change, even though GitHub Actions checked out a `main` commit that already contains that change
  in source control.

## Why The Blob Containers Stayed Empty Again

- Live Azure Blob inspection still returned zero objects for:
  - `repo-rag-training-traces`
  - `repo-rag-bundles`
- The local re-exported worker result from `../dataset/artifacts/redis_results.json` recorded:
  - `backend_used: "codex_cli"`
  - `method_used: "codex_cli"`
  - `bundle_version: null`
  - `trace_handoff_status: null`
  - `warnings: []`
  - no `repo_rag_proxy_status` key at all
- The local unpack of `../dataset/artifacts/all_artifacts.tar.gz` contained:
  - `execution_artifacts/prompt-worker-0-qrkk7/execution.log`
  - rehydrated `codex_response.txt`
  - summary files
  - no `repo_rag_codex_proxy_last.json`
  - no `repo_rag_trace*.json`
  - no `repo_rag_codex_proxy_stdout.log`
  - no `repo_rag_codex_proxy_stderr.log`
- So the worker again never persisted any sign that the repo-rag proxy path started, skipped with
  diagnostics, or exported a trainer trace.

## Source/Image Timeline Mismatch

- The user-reported image build completed with tag `20260430-183813`.
- The dataset diagnostic fallback commit in the local repository is
  `6af864e22dd38a1199ca5b34b1634a391f23e0f7` (`Diagnose codex repo-rag proxy fallback`).
- GitHub's `main` branch later advanced to merge commit
  `a6ae9addfe7a069d95e9a59f632340cb772a2ede`, which includes that diagnostic commit in its merge
  message.
- The latest AKS run therefore used:
  - newer workflow source on `main`
  - but a worker image tag built before the diagnostic code was added
- This is a narrower form of the same source/image drift diagnosed in the prior audit:
  the workflow source and the deployed worker runtime are still not guaranteed to be the same code.

## Additional CI Context

- Dataset GitHub Actions `Tests` runs failed on both:
  - `develop` at `6af864e22dd38a1199ca5b34b1634a391f23e0f7`
  - `main` at `a6ae9addfe7a069d95e9a59f632340cb772a2ede`
- The failures are broad and not limited to repo-rag, but they do include a directly relevant unit
  failure:
  - `tests/unit/test_worker_execution_prompt_repo_rag_cli.py::test_dynamic_worker_keeps_codex_backend_and_prepares_repo_rag_proxy_spec`
- Local targeted proxy-spec tests in the current dataset checkout still pass, so the remote CI red
  state is repository-wide and cannot, by itself, explain the empty trace container for this AKS
  run.

## Evidence

GitHub Actions:

- `gh run view 25186264345 --json ... -R realagiorganization/dataset` — pass
  - `workflowName: Parallel Prompt Execution on Azure AKS`
  - `headBranch: main`
  - `headSha: a6ae9addfe7a069d95e9a59f632340cb772a2ede`
  - `conclusion: success`
- User-supplied AKS log excerpt — reviewed
  - `Using prebuilt worker image: .../prompt-executor:20260430-183813`
  - `Success breakdown: codex_cli: 1`
  - `No artifacts in prompt-worker-0-qrkk7`
  - `Skipping repo-rag cache sync because tools/pvc_artifact_sync.sh is unavailable`

Azure:

- `az account show -o json` — pass
- `az storage blob list --account-name realagistorage --account-key "$KEY" --container-name repo-rag-training-traces --num-results 10 -o json` — pass, empty list
- `az storage blob list --account-name realagistorage --account-key "$KEY" --container-name repo-rag-bundles --num-results 10 -o json` — pass, empty list

Local re-exported artifacts:

- `../dataset/artifacts/redis_results.json` — pass
  - contains no `repo_rag_proxy_status` key in `result`
- `tar -xzf ../dataset/artifacts/all_artifacts.tar.gz ...` — pass
  - no `repo_rag_*` or `codex_proxy` files present
- `tar -xzf ../dataset/artifacts/processed.tar.gz ...` — pass
  - processed result payloads also omit `repo_rag_proxy_status`

Dataset source inspection:

- `git -C ../dataset rev-parse main develop` — pass
  - local `main` is still older (`f117809...`)
  - local `develop` is `6af864e...`
- `gh api repos/realagiorganization/dataset/commits/a6ae9addfe7a069d95e9a59f632340cb772a2ede` — pass
  - merge commit message includes `Diagnose codex repo-rag proxy fallback`

## Practical Conclusion

- The latest run still does not answer why repo-rag mediation was skipped, because the deployed
  worker image was built before the diagnostic result-field change.
- The immediate next valid validation step is:
  - rebuild `repo-rag-runtime` and `prompt-executor` after `6af864e`
  - rerun AKS with that newer tag
  - then inspect whether `repo_rag_proxy_status` appears in `redis_results.json`
- Until that happens, the continued emptiness of `repo-rag-training-traces` is still explained by
  a worker runtime that never emitted the new fallback diagnostics, never entered the proxy path,
  and never exported a trace.

## Checks Executed This Turn

Repo-local:

- `uv run python -m compileall src tests` — pass
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — pass (`37 passed`)
- `uv run repo-rag smoke-test` — pass
- `cargo build --manifest-path rust-cli/Cargo.toml` — pass
- `make files-sync` — pass

Dataset / external inspection:

- `gh run view 25186264345 --json ... -R realagiorganization/dataset` — pass
- `gh run view 25186076510 --json ... -R realagiorganization/dataset` — pass
- `gh run view 25186164085 --json ... -R realagiorganization/dataset` — pass
- `gh run view 25186168961 --json ... -R realagiorganization/dataset` — pass
- `gh run view 25186168961 --job 73843916549 --log -R realagiorganization/dataset` — pass
- `gh run view 25186076510 --job 73843595005 --log -R realagiorganization/dataset` — pass
- `gh api repos/realagiorganization/dataset/commits/a6ae9addfe7a069d95e9a59f632340cb772a2ede` — pass
- `az account show -o json` — pass
- `az storage blob list --account-name realagistorage --account-key "$KEY" --container-name repo-rag-training-traces --num-results 10 -o json` — pass, zero blobs returned
- `az storage blob list --account-name realagistorage --account-key "$KEY" --container-name repo-rag-bundles --num-results 10 -o json` — pass, zero blobs returned

## Missing Or Not Run This Turn

- Coverage: not run
- Lint: not run
- Type checking: no dedicated type-check suite was run
- UI validation: no dedicated UI suite exists for this repository surface
- End-to-end AKS rerun on a post-`6af864e` worker image: not run
- Trainer publish/promote cycle for bundle population: not run
