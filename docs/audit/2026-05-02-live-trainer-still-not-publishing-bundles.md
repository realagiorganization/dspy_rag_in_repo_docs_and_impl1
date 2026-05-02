# Live Trainer Still Not Publishing Bundles

- Date: `2026-05-02`
- Scope: current live reason the AKS trainer still does not emit a fresh bundle version
- Preceding note: `2026-05-01-live-trainer-no-timestamp-bundle-publish.md`

## Summary

As of `2026-05-02`, the live trainer is still not publishing any new bundle version.

The direct blocker is no longer ambiguous:

1. trainer cycles are still failing before publish
2. trainer-side recompilation is still blocked by invalid training samples
3. no successful recompile means no fresh publish
4. Azure Blob therefore still contains only the old bundle directories:
   - `versions/trainer-auto/...`
   - `versions/trainer-auto-remoteupload/...`

## Live Evidence

Live trainer state:

- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'cat /workspace/repo-rag/artifacts/trainer/service-state.json'`
- current salient values:
  - `cycles_executed = 15`
  - `successful_cycle_count = 0`
  - `failed_cycle_count = 15`
  - `total_publish_count = 0`
  - `total_recompiled_run_count = 0`
  - `total_new_training_candidate_count = 0`
  - `last_cycle_command_status = "fail"`

Latest live cycle record:

- `artifacts/trainer/history/20260502T072723Z-cycle-0015.json`
- salient values:
  - `command_status = "fail"`
  - `queue_drain.failed_count = 1`
  - `training_candidates.candidate_count = 15`
  - `training_candidates.new_candidate_count = 0`
  - `training_candidates.duplicate_count = 10`
  - `recompile = null`
  - `recompile_error.type = "ValueError"`

The recompile error still reports invalid training samples, including:

- duplicate questions
- missing expected sources under current repo layout, including:
  - `docs/architecture/inspired/dspy-rag-tutorial.md`
  - `docs/architecture/inspired/implementing-rag-with-dspy-technical-guide.md`
  - `AGENTS.md`
  - `utilities/README.md`
  - `docs/architecture/package-api.md`
  - `docs/operations/azure-deployment.md`
  - `publication/README.md`
  - prompt-artifact paths such as:
    - `prompt_artifacts/prompts_shards_of_lokar_game-p00000-355cca.txt`
    - `prompt_artifacts/prompts_shards_of_lokar_game-p00000-9dc50a.txt`
    - `prompt_artifacts/prompts_shards_of_lokar_game.txt`
    - `docs/USAGE.md`

Bundle container readback from Azure:

- `uv run python - <<'PY' ... BlobServiceClient(...).get_container_client("repo-rag-bundles").list_blobs(name_starts_with="versions/") ... PY`
- observed blobs remain:
  - `versions/trainer-auto/bundle.json`
  - `versions/trainer-auto/metadata.json`
  - `versions/trainer-auto/program.json`
  - `versions/trainer-auto/published.json`
  - `versions/trainer-auto-remoteupload/bundle.json`
  - `versions/trainer-auto-remoteupload/metadata.json`
  - `versions/trainer-auto-remoteupload/program.json`
  - `versions/trainer-auto-remoteupload/published.json`
- no `channels/*`

## Interpretation

The live trainer is not blocked by Azure upload permissions.

It is blocked earlier in the cycle:

1. queue drain sees one stale failed item and records a `BlobNotFound` cleanup failure
2. trainer candidate ingestion produces only duplicates and zero new candidates
3. trainer-side sample validation still raises `ValueError`
4. recompilation never completes
5. publish never starts

So the current reason a new bundle version is not appearing is:

- **trainer-side sample/candidate state is still invalid for recompilation**, and
- therefore **no publish path is reached at all**

## Worker Cost Context

This also means the live spend is still dominated by worker-side `codex exec`, not by trainer.

Current worker evidence from `../dataset/artifacts/redis_results.json`:

- `backend_used = "codex_cli_repo_rag_proxy"`
- `success = true`
- `prompt_tokens = 456612`
- `completion_tokens = 0`
- `total_tokens = 456612`

Current trainer evidence:

- `total_recompiled_run_count = 0`
- `total_publish_count = 0`

So the trainer is still failing cheaply, while the worker path is spending on very large input
contexts.

## Minimal Next Step

The next meaningful fix is not another worker rerun.

The live trainer needs one of these before it can publish again:

1. normalize candidate/source expectations so trainer samples reference paths that actually exist in
   the trainer repo root
2. prevent duplicate worker traces for the same question from being promoted into invalid
   recompile inputs
3. clean up the stale failed queue item so the cycle stops re-reporting the same `BlobNotFound`

Until the trainer can complete one successful recompile, Azure Blob will not get a fresh bundle
version regardless of the bundle naming scheme.

## Local Fix Applied

The repository now contains a trainer-side normalization fix for the compile-input bridge:

1. `materialize_combined_training_examples(...)` now merges base examples plus trainer candidates
   by **question identity**, not by the broader `(question, answer, sources, status)` tuple
2. trainer-candidate-tagged records now also drop legacy worker-only `expected_sources` such as
   `prompt_artifacts/...` and `docs/USAGE.md` before entering `generated-training.yaml`
3. when the same question appears multiple times, the newest candidate replaces the earlier
   question entry instead of producing an invalid duplicate question in the final DSPy training set

This does not yet prove the live AKS trainer is fixed, because the running trainer image must still
be rebuilt and redeployed. But it closes the current local code path that was capable of
reintroducing duplicate questions and stale worker source paths during recompile input assembly.

## Verification Commands

Repository-local checks executed in this turn:

- `uv run python -m compileall src tests` -> `pass`
- `uv run pytest tests/test_training_samples.py tests/test_utilities.py -q` -> `pass` (`46 passed`)
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` -> `pass` (`40 passed`)
- `uv run pytest tests/test_dspy_training.py -q` -> `pass` (`22 passed`)
- `uv run repo-rag smoke-test` -> `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`

Operational evidence collected in this turn:

- `kubectl -n repo-rag get deploy,po,cronjob,job,cm,secret`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'cat /workspace/repo-rag/artifacts/trainer/service-state.json'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'ls -1 /workspace/repo-rag/artifacts/trainer/history | sort | tail -n 4 | while read f; do ...; done'`
- `uv run python - <<'PY' ... BlobServiceClient(...).get_container_client("repo-rag-bundles").list_blobs(...) ... PY`
- local artifact inspection under `../dataset/artifacts/`
