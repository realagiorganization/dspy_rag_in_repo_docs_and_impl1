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

## 2026-05-08 live result: the drift fix worked, but publish is now blocked by retrieval and bundle gates

Fresh worker artifacts under `../dataset/artifacts/` and current live trainer state show that the
trainer is no longer stuck in `skipped-no-new-candidates`.

Current live trainer service state:

- `cycles_executed = 2`
- `successful_cycle_count = 0`
- `failed_cycle_count = 2`
- `total_recompiled_run_count = 2`
- `total_publish_count = 0`
- `total_skipped_recompile_count = 0`
- `latest_cycle_record_path = "artifacts/trainer/history/20260508T100904Z-cycle-0002.json"`
- `last_cycle_command_status = "fail"`
- `last_cycle_warnings` include:
  - `Bundle publish was blocked by trainer-side DSPy benchmark gates.`
  - `Promotion to \`stable\` was blocked by retrieval gate failures.`

So the unpublished-champion drift fix is working in the live trainer:

1. the cycle is re-entering recompilation even with `queued_count_before = 0`
2. a fresh DSPy bundle is being generated locally
3. publish is requested
4. promotion to `stable` is blocked later by failing gates

The newest live cycle generated a fresh local bundle:

- `artifacts/dspy/20260508T101020034403Z/program.json`
- `artifacts/dspy/20260508T101020034403Z/metadata.json`
- `artifacts/dspy/20260508T101020034403Z/bundle.json`

But that bundle was not published or promoted:

- `publish_requested = true`
- `publish = null`
- `publish_error = null`
- `promotion_requested = true`
- `promotion_status = "blocked"`
- `promotion = null`
- `promotion_error = null`

The current live retrieval gate failed with:

- `status = "fail"`
- `best_pass_rate = 0.875`
- `threshold_failures`:
  - `Benchmark pass rate 0.88 is below required threshold 1.00.`
  - `Benchmark average source recall 0.75 is below required threshold 1.00.`

The concrete failing retrieval benchmark question is:

- `Where are inspired implementation summaries stored?`

Its expected sources are:

- `docs/architecture/inspired/dspy-rag-tutorial.md`
- `docs/architecture/inspired/implementing-rag-with-dspy-technical-guide.md`

But the retrieved sources did not include either inspired-document path.

The current live bundle gate also failed for the newly recompiled bundle:

- `status = "fail"`
- `run_name = "20260508T101020034403Z"`
- `bundle_version = "20260508T101020034403Z"`
- `benchmark_pass_rate = 0.2857142857142857`
- `benchmark_status = "fail"`
- `bundle_path = "artifacts/dspy/20260508T101020034403Z/bundle.json"`
- `metadata_path = "artifacts/dspy/20260508T101020034403Z/metadata.json"`

So the current direct reason the user still does not see a fresh bundle is now:

- **recompilation is finally happening again**
- **but trainer-side retrieval and bundle benchmark gates are blocking publication and stable promotion**

## 2026-05-08 worker-side confirmation: worker fixes are no longer the blocker

The same `../dataset/artifacts/` upload confirms that the worker-side MCP and resume fixes are
working and are not the reason a new bundle is missing.

For `prompts_debt_relief-p00000-22fc5b`:

- `execution_status = "success"`
- `acceptance_status = "candidate"`
- `codex_session_mode = "resumed"`
- `restore_status = "restored"`
- `rag_status = "success"`
- `dspy_status = "success"`
- `bundle_resolved = true`
- `bundle_version = "20260502T122127191445Z"`
- `mcp_used = true`
- `discovery_via_mcp = true`
- `search_repo_call_count = 1`
- `ask_repo_call_count = 1`
- `prompt_tokens = 34765`

The corresponding MCP debug and usage artifacts show both preflight and live tool calls
succeeding, and the transcript churn is low:

- `diff --git = 5`
- `sed -n = 5`
- `README.md = 9`

So as of this turn:

- worker-side `resume + MCP + DSPy` worked
- trainer-side unpublished-champion drift recompilation worked
- the remaining blocker is entirely the trainer publish gates

## Verification Commands

Repository-local checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` -> `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` -> `pass` (`43 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test` -> `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`

Operational evidence collected in this turn:

- local artifact inspection under `../dataset/artifacts/`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'cat /workspace/repo-rag/artifacts/trainer/service-state.json'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'f=$(ls -1 /workspace/repo-rag/artifacts/trainer/history | sort | tail -n 1); echo $f; cat /workspace/repo-rag/artifacts/trainer/history/$f'`

## 2026-05-08 local root cause and fix: trainer pod `hybrid-vector` semantic blending overrides strong lexical document hits

The current live trainer failure is now reproducible as a retrieval-ranking bug, not as a queue,
publish, or candidate-ingestion bug.

Direct execution inside the live trainer pod showed:

- `lexical` retrieval for `Where are inspired implementation summaries stored?` returns:
  - `docs/architecture/inspired/implementing-rag-with-dspy-technical-guide.md`
  - `docs/architecture/inspired/dspy-rag-tutorial.md`
- `idf-rerank` returns the same two inspired documents first
- but `hybrid-vector` returns unrelated semantic neighbors first:
  - `publication/exploratorium_translation/README.md`
  - `utilities/README.md`
  - `src/repo_rag_lab/benchmarks.py`
  - `src/repo_rag_lab/exploratorium_translation.py`

At the same time, trainer-pod path scoring for the same question already strongly prefers the
expected inspired-doc paths:

- `docs/architecture/inspired/implementing-rag-with-dspy-technical-guide.md` -> `5.05`
- `docs/architecture/inspired/dspy-rag-tutorial.md` -> `5.05`
- `publication/exploratorium_translation/README.md` -> `3.1`
- `src/repo_rag_lab/benchmarks.py` -> `0.6`

So the live failure is not caused by wrong lexical scoring or missing path bonuses. It is caused by
the `hybrid-vector` combiner using only rank positions plus a very small semantic-score term,
allowing semantic-only neighbors to outrank much stronger lexical/path-aware document matches in
the trainer pod environment.

The repository now contains a local fix for that blend:

- `src/repo_rag_lab/retrieval.py`
  - `_hybrid_ranked_chunks(...)` now includes one normalized lexical-score component in the hybrid
    score instead of relying only on lexical position + semantic position
  - this keeps `hybrid-vector` from discarding strong lexical document hits when the semantic branch
    overgeneralizes

Regression coverage added:

- `tests/test_retrieval.py`
  - new test:
    - `test_retrieve_hybrid_vector_keeps_strong_lexical_doc_hits_ahead_of_semantic_noise`
  - it simulates a misleading semantic ranking and asserts that the top-2 hybrid results remain the
    two inspired docs instead of semantic-noise files

Local verification after the fix:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_retrieval.py -q` -> `pass` (`15 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_benchmarks_and_notebook_scaffolding.py::test_repository_benchmarks_pass_with_current_training_samples tests/test_benchmarks_and_notebook_scaffolding.py::test_evaluate_retrieval_quality_suite_reports_top_k_summaries -q` -> `pass` (`2 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run python - <<'PY' ... evaluate_retrieval_quality_suite(..., top_k=8) ... PY` ->
  - `retrieval_mode = "idf-rerank"`
  - `default_summary.pass_rate = 1.0`
  - `default_summary.average_source_recall = 1.0`
  - the inspired benchmark retrieves:
    - `docs/architecture/inspired/implementing-rag-with-dspy-technical-guide.md`
    - `docs/architecture/inspired/dspy-rag-tutorial.md`
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` -> `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_benchmarks_and_notebook_scaffolding.py::test_repository_benchmarks_pass_with_current_training_samples tests/test_benchmarks_and_notebook_scaffolding.py::test_evaluate_retrieval_quality_suite_reports_top_k_summaries -q` -> `pass` (`45 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test` -> `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`

This remains a local code fix until a rebuilt trainer image proves it in AKS, but the current
remaining blocker is now sharply isolated:

- before this fix, trainer-side `hybrid-vector` ranking itself was capable of blocking publish even
  after recompilation resumed
- after deployment, the same live benchmark should stop failing on the inspired-doc question

## 2026-05-08 current live state: a new local bundle is compiled, but publish/promote is blocked by the trainer-side bundle gate

The newest live trainer cycle confirms that the current blocker is no longer candidate drift and no
longer the retrieval gate.

Live trainer service state now reports:

- `cycles_executed = 2`
- `successful_cycle_count = 0`
- `failed_cycle_count = 2`
- `total_recompiled_run_count = 2`
- `total_publish_count = 0`
- `total_promotion_count = 0`
- `last_cycle_command_status = "fail"`
- `last_cycle_warnings`:
  - `Bundle publish was blocked by trainer-side DSPy benchmark gates.`
  - `Promotion to \`stable\` was blocked by trainer-side DSPy benchmark gates.`

The newest cycle record is:

- `artifacts/trainer/history/20260508T112754Z-cycle-0002.json`

That cycle proves a new bundle was in fact formed locally inside the trainer workspace:

- `artifacts/dspy/20260508T112905566179Z/program.json`
- `artifacts/dspy/20260508T112905566179Z/metadata.json`
- `artifacts/dspy/20260508T112905566179Z/bundle.json`

At the same time, the published surfaces remain unchanged:

- `artifacts/dspy/published/20260502T122127191445Z.json` is still the newest published timestamped
  record
- `artifacts/dspy/channels/stable.json` still points to
  `current_bundle_version = "20260502T122127191445Z"`
- there is no published record for `20260508T112905566179Z`

So the direct answer to “why is there no new visible bundle?” is:

- **a new bundle was compiled locally**
- **it was not published**
- **the stable channel did not move**

The critical gate split in the live cycle is now:

- retrieval gate: `pass`
  - `best_pass_rate = 1.0`
  - `threshold_failures = []`
  - the previously failing inspired-doc benchmark now retrieves:
    - `docs/architecture/inspired/implementing-rag-with-dspy-technical-guide.md`
    - `docs/architecture/inspired/dspy-rag-tutorial.md`
- bundle gate: `fail`
  - `bundle_version = "20260508T112905566179Z"`
  - `benchmark_pass_rate = 0.2857142857142857`
  - `benchmark_status = "fail"`
  - `bundle_gate_passed = false`
  - `publish_requested = true`
  - `promotion_requested = true`
  - `publish = null`
  - `promotion = null`
  - `promotion_status = "failed"`

The bundle metadata for `20260508T112905566179Z` shows why the bundle gate still blocks publish:

- `training_example_count = 21`
- `benchmark_summary.case_count = 21`
- `benchmark_summary.pass_count = 6`
- `benchmark_summary.pass_rate = 0.2857142857142857`

Representative failing benchmark rows include both core repo prompts and imported trainer-candidate
prompts:

- `What does this repository research?`
  - sources are correct, but the compiled answer still fails the benchmark contract
- `How do you build the publication PDF locally?`
  - the compiled answer says `make paper-build`, which does not satisfy the benchmark expectation
- multiple `trainer-candidate` Discord-family prompts
  - especially `prompts_shards_of_lokar_game`
  - these still fail even though they are present in the compiled training set

That means the current blocker has shifted again:

- **the trainer now recompiles**
- **the retrieval gate now passes**
- **but the compiled DSPy bundle itself still fails its benchmark suite, so publish/promote are
  intentionally blocked**

Operational evidence collected for this update:

- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'cat /workspace/repo-rag/artifacts/trainer/service-state.json'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'latest=$(ls -1 /workspace/repo-rag/artifacts/trainer/history | sort | tail -n 1); echo "$latest"; cat "/workspace/repo-rag/artifacts/trainer/history/$latest"'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'find /workspace/repo-rag/artifacts/dspy/published -maxdepth 1 -type f | sort | tail -n 10; printf "\\n---\\n"; for f in /workspace/repo-rag/artifacts/dspy/channels/*; do [ -f "$f" ] || continue; echo "===${f}==="; cat "$f"; echo; done'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'cat /workspace/repo-rag/artifacts/dspy/20260508T112905566179Z/metadata.json'`

## 2026-05-08 local root cause and fix: the trainer bundle gate was benchmarking the merged Discord/candidate trainset instead of the curated repo-local benchmark bank

The newest live metadata makes the remaining publish blocker structurally clear:

- `training_example_count = 21`
- `benchmark_summary.case_count = 21`

That equality is the bug. The trainer was using the same merged compile input
`artifacts/trainer/generated-training.yaml` for both:

1. DSPy compilation
2. bundle publish benchmarking

But that merged training file intentionally contains imported `trainer-candidate` rows from worker
traces, including prompts about external repositories such as:

- `prompts_shards_of_lokar_game`
- `prompts_goat_labs`
- `prompts_debt_relief`

Those rows are valid as compile-time supervision for the trainer lineage, but they are **not valid
repo-local publication benchmarks** for this repository-grounded DSPy bundle. Their expected
answers describe work done in other repositories, while the compiled program still retrieves only
from the current repository corpus. As a result, the bundle gate was forced to score impossible
cases and could never publish reliably even after retrieval itself recovered.

The repository now contains a local fix for that split:

- `src/repo_rag_lab/dspy_training.py`
  - `DSPyTrainingConfig` now accepts an explicit `benchmark_path`
  - `train_repository_program(...)` now loads compile examples from `training_path`, but evaluates
    the compiled program against `benchmark_path` when provided
  - training metadata now records:
    - `training_path`
    - `benchmark_path`
    - `training_example_count`
    - `benchmark_example_count`
- `src/repo_rag_lab/utilities.py`
  - trainer-side recompilation now compiles from
    `artifacts/trainer/generated-training.yaml`
  - but bundle publish benchmarking now evaluates against the curated base bank
    `samples/training/repository_training_examples.yaml`

The same pass also tightened two overly brittle repo-local benchmark answers inside
`samples/training/repository_training_examples.yaml`:

- `What does this repository research?`
  - shortened to `It researches repository-grounded RAG over repository files.`
- `How do you build the publication PDF locally?`
  - shortened to `Use make paper-build to build the publication PDF locally.`

Those changes keep the repo-local publish gate focused on the stable contract it is supposed to
enforce, while still allowing the trainer to learn from the larger imported candidate corpus during
compilation.

Local verification for this fix:

- `uv run python -m compileall src tests` -> `pass`
- `uv run pytest tests/test_dspy_training.py tests/test_utilities.py -q` -> `pass` (`63 passed`)
- `uv run pytest tests/test_repository_rag_bdd.py tests/test_benchmarks_and_notebook_scaffolding.py::test_repository_benchmarks_pass_with_current_training_samples tests/test_benchmarks_and_notebook_scaffolding.py::test_evaluate_retrieval_quality_suite_reports_top_k_summaries -q` -> `pass` (`5 passed`)
- `uv run pytest tests/test_cli_and_dspy.py::test_cli_main_dspy_train_command tests/test_cli_and_dspy.py::test_cli_main_trainer_recompile_command -q` -> `pass` (`2 passed`)
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` -> `pass` (`43 passed`)
- `uv run repo-rag smoke-test` -> `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`

This is still a local code fix until the next rebuilt trainer image proves it in AKS, but the
remaining live publish diagnosis is now much sharper:

- retrieval gate failure has already been removed
- champion drift recompilation is already working again
- the next live question is whether a trainer image with this benchmark-path split can finally
  publish a fresh bundle instead of scoring external Discord-family prompts as repo-local gate
  failures

This audit note should not be read as changing the long-term bundle contract. The repo-local
`benchmark_path` split is only a temporary unblocker. The standing requirement remains:

- one global universal DSPy bundle
- incremental updates whenever an accepted/candidate run improves a family champion
- inclusion of completely new prompt families in the next bundle candidate
- future publication logic driven by request deltas plus retrieved-context deltas across prompt
  families, not by hard dependence on repo/branch replay identity

## 2026-05-08 local trainer-state follow-up: prompt-family assignment is now delta-aware instead of exact-question-only

The current local trainer slice now makes one additional step toward that contract:

- prompt-family assignment is no longer treated as “exact normalized question or nothing”
- the trainer still keeps a durable candidate pool
- champions are still materialized incrementally from that pool
- bundle recompilation may still rebuild from the current champion set without violating the
  incremental contract

The local implementation now adds an explicit prompt-similarity layer beside the existing
context-similarity layer:

- close prompt variants can be grouped into one prompt family instead of always forking on exact
  question text
- larger prompt deltas now create a fresh family path instead of silently collapsing into the
  incumbent family
- context-group creation remains separate from family-champion replacement, so a new
  context-group champion path does not automatically become the family champion unless the
  family-level score/support comparison also prefers it

The current code path uses explicit similarity bands rather than a dedicated user-facing
`20% delta` knob, and that is the more correct long-term shape. One hard cutoff is too blunt for
prompt/context grouping. The better contract is:

- a strong-match band that confidently merges into the same family/group
- a weak-match band that confidently splits into a new family/group
- a gray zone in between where additional overlap heuristics decide the outcome

So the trainer state model has now moved in the right direction: prompt identity is treated as a
delta-aware grouping problem rather than as exact normalized-question equality or as one rigid
percentage threshold.

Local verification for this follow-up:

- `uv run python -m compileall src tests` -> `pass`
- `uv run pytest tests/test_training_samples.py -q` -> `pass` (`20 passed`)
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` -> `pass` (`43 passed`)

## 2026-05-08 local trainer-state follow-up: bundle benchmarking now follows the generated champion set while trainer-candidate rows may carry benchmark context

The previous local bridge that pointed trainer benchmarking back at the curated repo-local bank was
useful as a temporary diagnosis aid, but it did not satisfy the standing product requirement for
one global incremental bundle. The current local slice moves the trainer one step closer to that
contract without reintroducing repo/branch replay coupling.

The current implementation now does three concrete things:

1. imported trainer-candidate rows preserve benchmark evidence directly in the materialized
   champion set:
   - `benchmark_context`
   - `benchmark_context_sources`
2. trainer-side recompilation still compiles from
   `artifacts/trainer/generated-training.yaml`
3. trainer-side benchmarking now also evaluates the generated champion set, but each benchmark row
   may answer from stored benchmark context instead of forcing live retrieval against the current
   repo

That means the trainer can now benchmark a global champion set in a mixed mode:

- repo-local benchmark rows still run through normal repository retrieval
- external prompt-family champion rows can be evaluated from stored benchmark context
- the publication contract is therefore driven more by request/context deltas than by repository
  identity

The local code changes behind this slice are:

- `src/repo_rag_lab/training_samples.py`
  - `TrainingExample` now carries `benchmark_context` and `benchmark_context_sources`
  - imported trace materialization extracts benchmark context from `context` /
    `retrieved_context`
  - normalized/materialized candidate records preserve those fields through champion-index and
    generated-training flows
- `src/repo_rag_lab/dspy_training.py`
  - `DSPyTrainingConfig` accepts a distinct `benchmark_path`
  - `RepositoryRAGProgram` exposes `answer_from_context(...)`
  - `evaluate_repository_program(...)` uses stored benchmark context when available instead of
    always forcing live retrieval
- `src/repo_rag_lab/utilities.py`
  - trainer recompile now benchmarks `artifacts/trainer/generated-training.yaml`, so bundle
    evaluation follows the current champion set rather than a repo-local bridge file

Local verification for this slice:

- `uv run python -m compileall src tests` -> `pass`
- `uv run pytest tests/test_training_samples.py tests/test_dspy_training.py tests/test_utilities.py -q` -> `pass` (`84 passed`)
- `uv run pytest tests/test_repository_rag_bdd.py -q` -> `pass` (`3 passed`)
- `uv run repo-rag smoke-test` -> `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`

This is still only a local code change until a rebuilt trainer image proves it in AKS, but it
changes the remaining question substantially. The trainer is no longer blocked on “repo-local
benchmark bank versus global trainset” as a structural contradiction. The next live question is
whether the generated champion set, evaluated with preserved benchmark context where needed, is
sufficiently strong to publish a new global bundle.

## 2026-05-08 fresh artifact review: the new worker trace was recovered, but the family champion did not refresh to the richer benchmark-context-bearing record

Fresh `dataset/artifacts` for `prompts_debt_relief-p00000-22fc5b` show that the worker-side path
is now healthy and cheap:

- `success = true`
- `execution_status = "success"`
- `acceptance_status = "candidate"`
- `prompt_tokens = 23769`
- `bundle_resolved = true`
- `bundle_version = "20260502T122127191445Z"`
- `mcp_used = true`
- `discovery_via_mcp = true`
- `search_repo_call_count = 1`
- `ask_repo_call_count = 1`
- `trusted_trace_handoff_summary.json` reported `queued = 1`, `failed = 0`

The key trainer-side question was whether that new queued trace turned into either:

1. a new prompt family
2. a better family champion
3. a published/promoted bundle

The live trainer state says no.

Observed live state:

- `artifacts/trainer/recovered-imported-traces/20260508T132324Z-prompts_debt_relief-p00000-22fc5b.json`
  now exists inside the trainer workspace
- so the new worker trace **was** recovered by the trainer
- but `training-candidates-summary.json` still reports:
  - `candidate_count = 13`
  - `new_candidate_count = 0`
  - `replaced_count = 0`
  - `new_prompt_family_count = 0`
- the latest trainer cycle
  `artifacts/trainer/history/20260508T131838Z-cycle-0002.json` reports:
  - `bundle_gate.status = "fail"`
  - `bundle_gate.run_name = "20260508T132001843054Z"`
  - `bundle_gate.bundle_version = "20260508T132001843054Z"`
  - `bundle_gate.benchmark_pass_rate = 0.38095238095238093`
  - `publish_requested = true`
  - `publish = null`
  - `promotion_requested = true`
  - `promotion = null`
  - `promotion_status = "failed"`
- `artifacts/dspy/channels/stable.json` still points to:
  - `current_bundle_version = "20260502T122127191445Z"`

The decisive new detail is why the newer worker trace did not change the benchmark surface.

The recovered imported trace `20260508T132324Z-prompts_debt_relief-p00000-22fc5b.json` already
contains retrieval context:

- `context` rows are present
- `retrieved_context` rows are present
- the trace also carries:
  - `retrieval_mode = "lexical"`
  - `sources = ["README.md", "package-lock.json", "package.json", "tsconfig.json"]`
  - `program_loaded = true`

But the live compile-facing champion set still does **not** carry that context through:

- `generated-training.yaml` currently contains `21` rows
- rows with non-empty `benchmark_context`: `0`
- the current `prompts_debt_relief` family champion in `champion-index.json` still points to the
  older recovered trace:
  - `artifacts/trainer/recovered-imported-traces/20260506T201606Z-prompts_debt_relief-p00000-22fc5b.json`
- that champion row still has:
  - `benchmark_context_len = 0`
  - `benchmark_context_sources_len = 0`

So the present live blocker is sharper than “bundle gate still fails.”

The live trainer is now doing all of this correctly:

- resolving the old stable bundle for worker runtime
- queueing the fresh trace
- recovering the fresh trace into the trainer workspace
- recompiling bundle candidates
- re-running bundle publication gates

What it is **not** doing yet is refreshing the compile-facing family champion when the newer trace
mostly confirms the same family outcome but adds richer benchmark context. Because that champion
record still points at the older empty-context snapshot, the current generated champion set remains
context-poor:

- `training_example_count = 21`
- `benchmark_example_count = 21`
- `benchmark_path = "artifacts/trainer/generated-training.yaml"`
- `benchmark_summary.pass_count = 8`
- `benchmark_summary.pass_rate = 0.38095238095238093`

That explains why the bundle still does not publish:

- the trainer is benchmarking the right global surface again
- but the materialized champion rows are still stale with respect to benchmark-context enrichment
- so the benchmark gate is not yet benefiting from the newer recovered evidence

Verification and inspection commands executed in this turn:

- `uv run python -m compileall src tests` -> `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` -> `pass` (`43 passed`)
- `uv run repo-rag smoke-test` -> `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`
- `tar -tf /home/standard/Desktop/realagi_work/dataset/artifacts/all_artifacts.tar.gz`
- `tar -xOf ... execution_artifacts/trusted_trace_handoff_summary.json`
- `tar -xOf ... execution_artifacts/all_results.json`
- `tar -xOf .../repo_rag_backend.json`
- `tar -xOf .../repo_rag_outcome.json`
- `tar -xOf .../repo_rag_trace.json`
- `kubectl -n repo-rag get deploy,pods,cronjob`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'cat /workspace/repo-rag/artifacts/trainer/service-state.json'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'cat /workspace/repo-rag/artifacts/trainer/history/20260508T131838Z-cycle-0002.json'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'find /workspace/repo-rag/artifacts/trainer/recovered-imported-traces -maxdepth 1 -type f | sort | tail -n 30'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'cat /workspace/repo-rag/artifacts/trainer/training-candidates-summary.json'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'cat /workspace/repo-rag/artifacts/dspy/channels/stable.json'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'grep -n "benchmark_context" /workspace/repo-rag/artifacts/trainer/generated-training.yaml | sed -n "1,20p"'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'python - <<\"PY\" ... count nonempty benchmark_context rows ... PY'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'python - <<\"PY\" ... inspect debt_relief row in training-candidates.yaml ... PY'`
- `kubectl -n repo-rag exec deploy/repo-rag-trainer-service -- sh -lc 'python - <<\"PY\" ... inspect debt_relief family champion in champion-index.json ... PY'`

Current conclusion:

- the new worker trace did arrive
- the new trace did not become a new or replacement family champion
- the champion set still carries empty benchmark-context payloads
- the bundle gate still fails on that stale champion set
- therefore no new published bundle or `stable` promotion occurred

## 2026-05-08 same-key champion refresh now treats richer benchmark context as a material update

The remaining trainer-side bug has now been reproduced and fixed locally.

The failing live pattern was:

- an older family champion already existed for `prompts_debt_relief`
- a newer trace arrived with the same question/answer/status key
- that newer trace carried richer `benchmark_context` and `benchmark_context_sources`
- but `materialize_training_candidates(...)` only incremented support for same-key variants
- so the family champion record stayed pinned to the older empty-context snapshot
- therefore the compile-facing champion set still benchmarked as if no richer evidence had ever
  arrived

The local fix changes two things in `src/repo_rag_lab/training_samples.py`:

- same-key champion variants are now merged with `_merge_equivalent_candidate_records(...)`, so a
  later trace with richer benchmark context can replace the context-poorer record even when the
  question/answer key is unchanged
- `new_candidate_count` and `replaced_count` now key off a materialized champion signature that
  includes benchmark-context payloads, not only the question/answer tuple

That means “same family, same answer, richer retrieved evidence” now counts as a meaningful
champion refresh and will trigger downstream recompile/publish logic instead of disappearing as a
mere support-count increment.

Verification commands executed after this local fix:

- `uv run python -m compileall src tests` -> `pass`
- `uv run pytest tests/test_training_samples.py -q` -> `pass` (`21 passed`)
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` -> `pass`
  (`43 passed`)
- `uv run repo-rag smoke-test` -> `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`

The new regression test covers the exact live-shaped case:

- first materialize an older champion with no benchmark context
- then import a same-key trace with richer benchmark context
- assert that the family champion now refreshes to the richer trace
- assert that `new_candidate_count = 1` and `replaced_count = 1`
- assert that the materialized training row now contains non-empty benchmark context

Current conclusion after the local fix:

- worker-side MCP/recovery remains healthy
- trainer-side global champion evaluation remains in place
- the remaining stale-champion blocker has been removed locally
- the next live rebuild/redeploy should determine whether this was the last blocker before bundle
  publication resumes
