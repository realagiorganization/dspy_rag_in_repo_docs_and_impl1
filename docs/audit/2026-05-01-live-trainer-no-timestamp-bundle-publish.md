# Live Trainer No Timestamp Bundle Publish

- Date: `2026-05-01`
- Scope: explain why the live AKS trainer did not publish a new immutable bundle under
  `repo-rag-bundles/versions/<timestamp>/...` after the timestamp-versioning contract landed
- Preceding note: `2026-05-01-dspy-bundle-version-pinning-contract.md`

## Summary

The current live trainer has not published any new timestamp-versioned bundle yet.

Two independent facts explain it:

1. The running trainer image is stale relative to the timestamp-versioning change, so its code path
   still works against `trainer-auto`-named local bundle artifacts instead of immutable
   timestamp-only bundle versions.
2. The live trainer cycles are currently failing before publish anyway, because the running image is
   still attempting trainer-side recompilation against invalid training samples and never reaches a
   successful publish step.

As a result, Azure Blob still contains only the older bundle directories:

- `versions/trainer-auto/...`
- `versions/trainer-auto-remoteupload/...`

There are no `versions/<timestamp>/...` bundle blobs yet.

## Live Evidence

Bundle container readback from Azure:

- `uv run python - <<'PY' ... BlobServiceClient(...).get_container_client("repo-rag-bundles").list_blobs(name_starts_with="versions/") ... PY`
- observed blobs:
  - `versions/trainer-auto/bundle.json`
  - `versions/trainer-auto/metadata.json`
  - `versions/trainer-auto/program.json`
  - `versions/trainer-auto/published.json`
  - `versions/trainer-auto-remoteupload/bundle.json`
  - `versions/trainer-auto-remoteupload/metadata.json`
  - `versions/trainer-auto-remoteupload/program.json`
  - `versions/trainer-auto-remoteupload/published.json`
- observed channel aliases:
  - none under `channels/`

Live trainer job template:

- `kubectl -n repo-rag get job repo-rag-trainer-cycle-29627835 -o yaml`
- image:
  - `llmpromptsacr.azurecr.io/repo-rag-runtime:20260501-174423`
- trainer args still include:
  - `--recompile-run-name trainer-auto`

Live trainer ConfigMap:

- `kubectl -n repo-rag get configmap repo-rag-trainer-config -o yaml`
- still resolves:
  - `TRAINER_RECOMPILE_RUN_NAME: trainer-auto`
  - `TRAINER_PROMOTE_CHANNEL: ""`

Live trainer container code inspection:

- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'python - <<\"PY\" ... text.find(...) ... PY'`
- the running container source did **not** contain:
  - `def _versioned_training_run_name`
  - `resolved_recompile_run_name = _versioned_training_run_name(recompile_run_name)`
  - `bundle_version=resolved_recompile_run_name`

That directly confirms the live image predates commit `a354af3` (`Pin DSPy bundles by immutable version`).

## Current Failure Mode

The trainer is not merely “publishing the wrong directory name.” It is currently not producing a
fresh publish at all.

Live trainer state:

- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'cat /workspace/repo-rag/artifacts/trainer/service-state.json'`
- salient values:
  - `successful_cycle_count = 0`
  - `failed_cycle_count = 23`
  - `total_recompiled_run_count = 0`
  - `total_publish_count = 0`
  - `last_cycle_command_status = "fail"`

Latest live history records:

- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'sed -n "1,260p" /workspace/repo-rag/artifacts/trainer/history/20260501T211946Z-cycle-0023.json'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'sed -n "1,260p" /workspace/repo-rag/artifacts/trainer/history/20260501T212301Z-cycle-0024.json'`

Those cycles show:

- `command_status = "fail"`
- `artifact_metadata.generated_paths` still point at:
  - `artifacts/dspy/trainer-auto/bundle.json`
- `recompile = null`
- `recompile_error.type = "ValueError"`
- `recompile_error.message` reports invalid training samples, including:
  - duplicate questions
  - missing expected sources such as:
    - `docs/architecture/inspired/dspy-rag-tutorial.md`
    - `utilities/README.md`
    - `prompt_artifacts/prompts_shards_of_lokar_game-p00000-355cca.txt`
    - `docs/USAGE.md`

One earlier cycle also recorded a queue-drain failure:

- `queue_drain.failed_count = 1`
- `error_type = "ResourceNotFoundError"`
- the missing blob was already under the `failed/repo-rag-training/...` prefix

That queue-drain issue is secondary. The main blocker is trainer-side recompile failure in the
stale image before publish can occur.

## Interpretation

The missing timestamp bundle directory is **not** caused by Azure Blob refusing uploads.

The actual chain is:

1. The live trainer Deployment is still on an image older than the timestamp-versioning change.
2. That image still targets `trainer-auto`-style bundle artifacts locally.
3. The same image also still reaches a failing trainer-side recompilation path on every recent
   cycle.
4. Because recompilation fails, no fresh publish happens.
5. Because no fresh publish happens, Azure Blob keeps only the older
   `versions/trainer-auto/...` and `versions/trainer-auto-remoteupload/...` artifacts.

## Minimal Next Step

The next live step is not another worker run.

The minimum required sequence is:

1. rebuild `repo-rag-runtime` from the repository state at or after commit `a354af3`
2. redeploy the trainer Deployment and CronJob with that new image
3. re-run one trainer cycle
4. verify separately whether:
   - the new image now produces `versions/<timestamp>/...`
   - trainer-side sample validation still blocks publish

If validation still fails after the redeploy, the remaining bug is no longer deployment drift; it
is the trainer candidate/sample normalization path.

## Verification Commands

Repository-local checks executed in this turn:

- `uv run python -m compileall src tests` — `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — `40 passed`
- `uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`

Operational evidence collected in this turn:

- `kubectl -n repo-rag get deploy,po,cronjob,job,cm,secret`
- `kubectl -n repo-rag get job repo-rag-trainer-cycle-29627835 -o yaml`
- `kubectl -n repo-rag get configmap repo-rag-trainer-config -o yaml`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'cat /workspace/repo-rag/artifacts/trainer/service-state.json'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'sed -n "1,260p" /workspace/repo-rag/artifacts/trainer/history/20260501T211946Z-cycle-0023.json'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'sed -n "1,260p" /workspace/repo-rag/artifacts/trainer/history/20260501T212301Z-cycle-0024.json'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'find /workspace/repo-rag/artifacts/dspy -maxdepth 3 -type f | sort'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'python - <<\"PY\" ... text.find(...) ... PY'`
- `uv run python - <<'PY' ... BlobServiceClient(...).get_container_client(\"repo-rag-bundles\").list_blobs(...) ... PY`

Verification categories not exercised in this turn:

- linting: no dedicated lint command was run
- type checking: no dedicated type-check command was run
- coverage: no coverage command was run
- notebook execution: no notebook execution suite was run
- end-to-end fixed-image AKS validation: not run in this turn
