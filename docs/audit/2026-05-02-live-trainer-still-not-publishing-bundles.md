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

## 2026-05-07 current live reason: trainer is healthy, but no new candidate reached recompile, and gates are still red

The current live state is no longer the old `failed_cycle_count > 0` / invalid-sample crash loop.
The trainer service is healthy now:

- `cycles_executed = 112`
- `successful_cycle_count = 112`
- `failed_cycle_count = 0`
- `total_publish_count = 0`
- `total_recompiled_run_count = 0`
- `total_skipped_recompile_count = 112`
- `last_cycle_command_status = "success"`

The latest cycle record (`artifacts/trainer/history/20260507T160549Z-cycle-0112.json`) shows the
new immediate blocker:

1. queue drain succeeded and found no errors
2. trainer recovered `75` processed trace records successfully
3. `training_candidates.new_candidate_count = 0`
4. `recompile_status = "skipped-no-new-candidates"`
5. no publish run was requested, so bundle publication never started

This behavior is exactly what the current trainer-cycle code does:

- `src/repo_rag_lab/utilities.py`
  - `new_candidate_count` is loaded from `materialize_training_candidates(...)`
  - if it is `0`, trainer sets `recompile_status = "skipped-no-new-candidates"` and does not
    enter the recompile path
- `src/repo_rag_lab/training_samples.py`
  - new candidates are counted only when a prompt family is new or when the family champion
    actually changes
  - exact snapshot ids that are already known are treated as duplicates and skipped

The newest recovered trace files confirm why the latest runs did not count as new:

- tail of `artifacts/trainer/recovered-imported-traces/` contains only already-known prompt ids:
  - `prompts_shards_of_lokar_game-p00000-355cca`
  - `prompts_goat_labs-p00000-298625`
- both prompt families already exist in `artifacts/trainer/training-candidates.yaml`
- the worker upload the user asked about (`prompts_shards_of_lokar_game-p00000-355cca`) is not a
  new trainer prompt family; it is another trace on an already-existing family

So the current direct reason no new DSPy bundle was published is:

- **the latest live trainer cycles saw zero new training candidates**, therefore
- **recompile was skipped**, therefore
- **publish was never requested**

There is also a second blocker waiting behind that first one:

- the same latest cycle still records retrieval/bundle gate failures even while the cycle itself is
  otherwise successful:
  - retrieval benchmark `status = "fail"`
  - best pass rate `0.875`
  - average source recall `0.75`
  - failing case: `Where are inspired implementation summaries stored?`
  - bundle gate `status = "fail"`
  - bundle-manifest pass rate `0.9333333333333333`

That means even if the next run finally produced `new_candidate_count > 0`, the publish path would
still be at risk of being blocked by the trainer-side benchmark gates unless those retrieval
threshold failures are addressed too.

Operational evidence collected for this updated diagnosis:

- `kubectl -n repo-rag get deploy,pod`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'cat /workspace/repo-rag/artifacts/trainer/service-state.json'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'latest=$(ls -1 /workspace/repo-rag/artifacts/trainer/history | sort | tail -n 1); echo "$latest"; cat "/workspace/repo-rag/artifacts/trainer/history/$latest"'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'cat /workspace/repo-rag/artifacts/trainer/training-candidates-summary.json; printf "\\n---\\n"; cat /workspace/repo-rag/artifacts/trainer/generated-training-summary.json'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'ls -1 /workspace/repo-rag/artifacts/trainer/recovered-imported-traces | sort | tail -n 8'`

## 2026-05-07 blob proof: the published stable bundle is older than `goat_labs`, and `goat_labs` first failed during trainer recompile

Direct Azure Blob inspection confirms the user's suspicion that the current published bundle does
not contain the `prompts_goat_labs-p00000-298625` family.

The current stable channel blob (`channels/stable.json`) points to:

- `current_bundle_version = 20260502T122127191445Z`
- `current_publish_status = "published"`
- `current_bundle_status = "ready"`

That published bundle predates the first `goat_labs` trainer trace by multiple days. Direct blob
downloads of:

- `versions/20260502T122127191445Z/bundle.json`
- `versions/20260502T122127191445Z/published.json`
- `versions/20260502T122127191445Z/metadata.json`
- `versions/20260502T122127191445Z/program.json`

contain no occurrences of:

- `goat_labs`
- `prompts_goat_labs`
- `prompt_family_id`

The bundle lineage explains why. `versions/20260502T122127191445Z/bundle.json` includes only
trainer-recovered trace lineage from 2026-05-01 through 2026-05-02, all on the older
`prompts_shards_of_lokar_game-p00000-355cca` family.

The first trainer cycle that actually ingested `goat_labs` was
`artifacts/trainer/history/20260506T222213Z-cycle-0016.json`. That cycle shows:

- `new_candidate_count = 1`
- `new_prompt_family_count = 1`
- `new_context_group_count = 1`
- generated paths include:
  - `artifacts/trainer/recovered-imported-traces/20260506T221908Z-worker-0-prompts_goat_labs-p00000-298625-realagiorganization_goat_labs.json`
  - `artifacts/trainer/recovered-imported-traces/20260506T222028Z-prompts_goat_labs-p00000-298625.json`

So `goat_labs` did form a new trainer family when it first arrived.

However, the same cycle failed before publish:

- `command_status = "fail"`
- `warnings = ["Trainer-side bundle recompilation failed during trainer cycle."]`
- `recompile_error.type = "BadRequestError"`
- `recompile_error.message` reported Azure/LiteLLM input overflow:
  - configured limit `922000`
  - actual tokens `1126031`
- `publish_requested = false`

That is why the stable bundle in blob still does not contain `goat_labs`:

1. the currently published stable bundle was cut on 2026-05-02, before `goat_labs` existed
2. the first cycle that created the `goat_labs` family failed during trainer recompile
3. publish never started, so the stable channel never advanced past `20260502T122127191445Z`

Operational evidence collected for this blob-level proof:

- `python - <<'PY' ... BlobServiceClient(...).get_container_client("repo-rag-bundles").get_blob_client("channels/stable.json") ... PY`
- `python - <<'PY' ... download versions/20260502T122127191445Z/{bundle,published,metadata,program}.json ... PY`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'python - <<\"PY\" ... Path(\"/workspace/repo-rag/artifacts/trainer/history/20260506T222213Z-cycle-0016.json\") ... PY'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'python - <<\"PY\" ... Path(\"/workspace/repo-rag/artifacts/trainer/training-candidates.yaml\") ... PY'`

## 2026-05-07 local fix: recompile now triggers on unpublished champion drift, not only on `new_candidate_count`

The next trainer bug after the transcript-overflow fix was a state-machine dead end:

1. `goat_labs` first arrived and correctly created `new_prompt_family_count = 1`
2. that cycle failed during trainer recompilation before publish
3. the champion index still kept the new `goat_labs` family
4. later cycles reported `new_candidate_count = 0`
5. trainer skipped recompile forever with `skipped-no-new-candidates`, even though the published
   stable bundle was still the old 2026-05-02 lineage without `goat_labs`

The repository now contains a local trainer-side fix for that dead end:

- `src/repo_rag_lab/training_samples.py`
  - adds `summarize_champion_index(...)` so trainer-cycle can compare the current family-champion
    set against the last published bundle lineage
  - preserves champion metadata such as `prompt_family_id` and `exact_snapshot_id` while loading
    the persisted champion index
- `src/repo_rag_lab/utilities.py`
  - adds `_trainer_pending_recompile_summary(...)`
  - `run_trainer_cycle(...)` now triggers recompilation when the current champion set has drifted
    past the published stable bundle, even if `new_candidate_count == 0`
  - the cycle payload now records `pending_recompile` diagnostics so the next artifact set can show
    whether trainer recompilation was triggered by fresh candidates or by unpublished champion drift

This specifically covers the `goat_labs` scenario:

- if the stable bundle lineage only knows the old `shards_of_lokar_game` traces
- and the current champion index contains the newer
  `20260506T221908Z-worker-0-prompts_goat_labs-p00000-298625-realagiorganization_goat_labs.json`
  champion trace
- then trainer recompilation must run again instead of staying stuck on
  `skipped-no-new-candidates`

Repository-local verification executed for this fix:

- `uv run python -m compileall src tests` -> `pass`
- `uv run pytest tests/test_training_samples.py tests/test_utilities.py -q` -> `pass` (`58 passed`)
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` -> `pass` (`43 passed`)
- `uv run repo-rag smoke-test` -> `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`

This is still a local code fix at this point. The live trainer pod is running code that already
contains the transcript-normalization change, but it has not yet consumed this new unpublished
champion-drift trigger, so a rebuild/redeploy is still required before the AKS trainer can prove
the fix on the next cycle.
