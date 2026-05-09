# Trainer Context-Group Champion Index Stage 1

- Date: `2026-05-02`
- Scope: replace question-level `last write wins` trainer candidate materialization with a
  prompt-family/context-group/family-champion state model that remains compatible with the current
  DSPy compile contract
- Preceding note: `2026-05-02-hybrid-vector-retrieval-default.md`

## Summary

The trainer no longer treats `training-candidates.yaml` as a pure question-level overwrite file.

Instead, imported worker traces now flow through a new persistent trainer state surface:

- `artifacts/trainer/champion-index.json`

That state groups imported traces in two stages:

1. `prompt_family`
   - stable identity derived from the normalized visible question
2. `context_group`
   - stable-ish grouping derived from retrieval-context similarity, currently using retrieved source
     overlap plus retrieval mode

Each context group keeps one context-group champion. Each prompt family then keeps one
family champion across those context groups. The compile-facing
`artifacts/trainer/training-candidates.yaml` file is materialized only from the family champions.

This is a deliberate first-stage constraint: the current DSPy compile dataset still behaves like
`question -> expected_answer`, so it is not yet safe to materialize multiple conflicting answers
for the exact same visible question into the generated compile set.

## Code Changes

Primary implementation surfaces:

- `src/repo_rag_lab/training_samples.py`
- `src/repo_rag_lab/runtime_artifacts.py`
- `tests/test_training_samples.py`
- `docs/planning/trainer-context-group-champion-plan.md`
- `docs/architecture/research-narrative.md`
- `docs/planning/dataset-integration-plan.md`

Important behavior changes:

- imported traces now receive:
  - `prompt_family_id`
  - `exact_snapshot_id`
  - `quality_score`
  - `context_snapshot`
- trainer candidate materialization now persists:
  - `artifacts/trainer/champion-index.json`
- family champion selection now replaces `last write wins` for compile-facing candidate updates
- `new_candidate_count` now reflects effective family-champion changes instead of raw ledger replay
- legacy `training-candidates.yaml` snapshots can still seed the champion index during migration
- trainer-cycle and trainer-service payloads now also expose:
  - `prompt_family_count`
  - `context_group_count`
  - `champion_index_path`
- repeated traces for the same answer variant inside one context group now accumulate explicit
  support for that champion variant instead of only incrementing group-wide `trace_count`
- context-group summaries now also merge gradual retrieval-source drift, so a prompt whose
  retrieved sources evolve from `README.md` to `README.md + docs/USAGE.md` to `docs/USAGE.md`
  can remain in one stable training group instead of fragmenting into new groups on every small
  retrieval shift
- runtime traces now also carry `evidence_fingerprints`, and `trace-export` backfills them from
  stored `context` / `retrieved_context` rows when older command envelopes do not include them
  explicitly; trainer grouping can therefore distinguish same-source retrievals that actually used
  different chunk evidence
- family-champion selection now also applies a stability gate across context groups: a new group
  must clear the score delta or win on support/evidence tie-breaks before it can replace the
  existing family champion, so one earlier high-score trace does not permanently lock in the
  family champion and one later low-support trace does not flip it by arrival order alone
- trainer-cycle and trainer-service now also expose `min_new_candidates_for_recompile`, and
  recompile can be skipped as `skipped-below-new-candidate-threshold` when the current cycle
  produces some new family-champion changes but not enough to justify a new bundle compile yet
- trainer Kubernetes manifest generation now also threads
  `TRAINER_MIN_NEW_CANDIDATES_FOR_RECOMPILE` through the generated ConfigMap plus
  `trainer-cycle` / `trainer-service` command lines, and the sibling `dataset`
  `deploy_repo_rag_trainer.sh` helper now forwards the same threshold into the AKS deployment path

## Verification

Repository-local checks executed in this turn:

- `uv run python -m compileall src tests` -> `pass`
- `uv run pytest tests/test_training_samples.py -q` -> `pass` (`11 passed`)
- `uv run pytest tests/test_training_samples.py -q` -> `pass` (`12 passed`)
- `uv run pytest tests/test_training_samples.py -q` -> `pass` (`13 passed`)
- `uv run pytest tests/test_training_samples.py -q` -> `pass` (`14 passed`)
- `uv run pytest tests/test_training_samples.py -q` -> `pass` (`15 passed`)
- `uv run pytest tests/test_dspy_training.py -q` -> `pass` (`22 passed`)
- `uv run pytest tests/test_utilities.py -k 'trainer_cycle or materialize_training_candidates or trainer_recompile_from_candidates' -q` -> `pass` (`5 passed`)
- `uv run pytest tests/test_utilities.py -k 'run_trainer_candidates or run_trainer_cycle or run_trainer_service' -q` -> `pass` (`8 passed`)
- `uv run pytest tests/test_utilities.py -k 'run_trace_export or run_trainer_candidates or run_trainer_cycle or run_trainer_service' -q` -> `pass` (`9 passed`)
- `uv run pytest tests/test_runtime_artifacts_azure.py tests/test_cli_and_dspy.py tests/test_mcp_server.py -k 'trace_export or ask_repo or publish_trace or queue_trace_record or drain_trace_queue or restore_processed_trace_records' -q` -> `pass` (`9 passed`)
- `uv run pytest tests/test_utilities.py -k 'run_trainer_candidates or run_trainer_cycle or run_trainer_service' -q` -> `pass` (`9 passed`)
- `uv run pytest tests/test_cli_and_dspy.py -k 'trainer_cycle_command or trainer_service_command' -q` -> `pass` (`2 passed`)
- `uv run pytest tests/test_utilities.py -k 'trainer_k8s or run_trainer_candidates or run_trainer_cycle or run_trainer_service' -q` -> `pass` (`10 passed, 28 deselected`)
- `uv run pytest tests/test_cli_and_dspy.py -k 'trainer_k8s_manifests or trainer_cycle_command or trainer_service_command' -q` -> `pass` (`3 passed, 29 deselected`)
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` -> `pass` (`41 passed`)
- `uv run repo-rag smoke-test` -> `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`
- `make files-sync` -> `pass`
- `make verify-surfaces` -> `pass`
- `bash -n deploy_repo_rag_trainer.sh && uv run pytest tests/unit/test_deploy_repo_rag_trainer_script.py -q` (in sibling `dataset`) -> `pass` (`4 passed`)

Focused regression now covered:

- one prompt family can now contain multiple context groups in `champion-index.json`
- only one family champion is materialized into `training-candidates.yaml`
- replaying unchanged imported traces no longer implies new compile work
- repeated same-answer traces inside one context group now increase champion support instead of
  being counted only as anonymous group volume
- gradual source drift inside one prompt family now updates the existing context-group summary
  instead of forcing a new context group whenever the retrieval sources shift slightly
- same-source traces with clearly different retrieved snippets can now split into separate context
  groups because grouping also uses snippet-level evidence fingerprints, not only source paths
- family champions now resist small score-only flips across context groups until a challenger
  either clears the score delta or wins on support/evidence tie-breaks
- trainer recompilation can now be intentionally batched behind a minimum new-candidate threshold
  instead of recompiling immediately on every single family-champion change
- trainer deployment manifests plus the sibling `dataset` AKS deploy helper now preserve that same
  batching threshold instead of silently dropping back to per-cycle recompilation in live deploys
- legacy worker-only expected sources remain stripped from trainer-candidate rows

## Limits

This first stage does **not** yet solve every context-drift problem.

Still deferred:

- chunk-hash-aware context grouping
- evidence-summary semantic similarity
- multi-answer compile datasets for one visible question
- exemplar-memory retrieval of similar historical traces at runtime

Still not covered by a current-turn deployment check:

- no live AKS redeploy or end-to-end trainer rollout was rerun after adding
  `TRAINER_MIN_NEW_CANDIDATES_FOR_RECOMPILE` to the deployment surfaces; current evidence for that
  piece is local manifest/script verification only

What this stage does solve immediately:

- parallel or repeated worker traces for the same prompt no longer automatically overwrite the
  trainer compile example by arrival order alone
- trainer-side recompile gating now keys off meaningful family-champion change instead of raw trace
  replay

## Latest Live Artifact Inspection

Fresh `dataset/artifacts` evidence from the latest worker run shows a mixed live result.

Confirmed from run artifacts:

- retrieval no longer injected `prompt_artifacts/...` into the repo-rag evidence shortlist
- `repo_rag_codex_proxy_last.json` reported only repo/docs sources:
  - `README.md`
  - `docs/USAGE.md`
  - `docs/AGENTS.md`
  - `docs/ASSUMPTIONS.md`
- `execution.log` recorded the expected cleanup and off-repo prompt-trace path:
  - `Removed stale runtime scaffolding from .../prompt_artifacts`
  - `Persisted prompt trace at /tmp/artifacts/.../prompt_artifacts/...`
- trusted downstream handoff succeeded:
  - `trace_handoff_status = queued`
  - `trusted_trace_handoff_summary.json` reported `queued = 1`, `failed = 0`

Still not working in that live run:

- `repo_rag_backend.json` reported:
  - `bundle_resolved = false`
  - `bundle_version = null`
- `repo_rag_codex_proxy_last.json` reported:
  - `mediation_mode = rag_heuristic_dspy`
  - `dspy_status = heuristic`
- `repo_rag_trace.json` reported:
  - `program_loaded = false`
  - `program_path = null`

One remaining nuance from `codex_response.txt`:

- `prompt_artifacts/*` still appeared in the model transcript, but only as deleted legacy files in
  `git status` output (`D prompt_artifacts/...`), not as retrieved repo-rag evidence
- this means retrieval isolation worked, but the cached repository checkout still contained tracked
  stale prompt-artifact paths that the autonomous Codex session noticed later through its own
  repository inspection

## Additional Verification

Repository-local checks rerun in this turn:

- `uv run python -m compileall src tests` -> `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` -> `pass` (`41 passed`)
- `uv run repo-rag smoke-test` -> `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`

Artifact-inspection commands executed in this turn:

- `tar -xOf /home/standard/Desktop/realagi_work/dataset/artifacts/all_artifacts.tar.gz execution_artifacts/prompt-worker-0-rehydrated/artifacts/prompts_shards_of_lokar_game-p00000-355cca/repo_rag_backend.json | jq ...`
- `tar -xOf /home/standard/Desktop/realagi_work/dataset/artifacts/all_artifacts.tar.gz execution_artifacts/prompt-worker-0-rehydrated/artifacts/prompts_shards_of_lokar_game-p00000-355cca/repo_rag_codex_proxy_last.json | jq ...`
- `tar -xOf /home/standard/Desktop/realagi_work/dataset/artifacts/all_artifacts.tar.gz execution_artifacts/prompt-worker-0-rehydrated/artifacts/prompts_shards_of_lokar_game-p00000-355cca/repo_rag_trace.json | jq ...`
- `tar -xOf /home/standard/Desktop/realagi_work/dataset/artifacts/all_artifacts.tar.gz execution_artifacts/trusted_trace_handoff_summary.json | jq .`
- `tar -xOf /home/standard/Desktop/realagi_work/dataset/artifacts/all_artifacts.tar.gz execution_artifacts/prompt-worker-0-lnj5r/execution.log | rg -n "prompt_artifacts|_context_repos|repo_rag|bundle|stable|codex exec|Persisted prompt trace|Removing stale"`
- `tar -xOf /home/standard/Desktop/realagi_work/dataset/artifacts/all_artifacts.tar.gz execution_artifacts/prompt-worker-0-rehydrated/artifacts/prompts_shards_of_lokar_game-p00000-355cca/codex_response.txt | rg -n "prompt_artifacts|_context_repos|\\.repo_rag_cache|README\\.md|docs/USAGE\\.md|docs/AGENTS\\.md|docs/ASSUMPTIONS\\.md"`

Verification categories still not covered in this turn:

- lint: no dedicated lint command was run
- type checking: no dedicated type-check suite was run
- coverage: no coverage tool was run
- UI / Godot runtime integration: not exercised
- live AKS redeploy / post-fix worker rerun with a successfully resolved DSPy bundle: still not
  confirmed

## Latest Live Trainer Queue State

Fresh live inspection after the latest worker run shows that the newest queued trace is stuck
because the live trainer workload is crashing before it can drain the queue.

Observed live state:

- `repo-rag-trainer-service` in namespace `repo-rag` is `CrashLoopBackOff`
- the queued blob is still present:
  - `queued/repo-rag-training/20260502T174448Z-prompts_shards_of_lokar_game-p00000-355cca.json`
- the trainer CronJob last scheduled at `2026-05-02T17:45:00Z`, but its newest Job hit
  `BackoffLimitExceeded`
- the CronJob status still reports `lastSuccessfulTime: 2026-05-02T12:47:27Z`, so no successful
  trainer drain/publish cycle has happened since the newer deployment wiring was applied

Root cause from live logs:

- both `trainer-service` and the generated `trainer-cycle` Job are launched with
  `--min-new-candidates-for-recompile 1`
- the live image `llmpromptsacr.azurecr.io/repo-rag-runtime:20260502-135903` exits immediately
  with:
  - `repo-rag: error: unrecognized arguments: --min-new-candidates-for-recompile 1`

That means the cluster manifests were updated, but the running image still contains an older
`repo-rag` CLI build that does not recognize the new argument. The result is straightforward:

- worker-side trusted handoff succeeds
- the trace lands in `queued/...`
- trainer service crashes on startup
- trainer cycle Jobs also fail
- the queued trace remains queued

Live commands executed in this turn:

- `kubectl get pods,deploy,cronjob -n repo-rag -o wide`
- `az storage blob list --account-name ... --container-name repo-rag-training-traces --prefix queued/repo-rag-training/ --num-results 20 --auth-mode key --output table`
- `az storage blob list --account-name ... --container-name repo-rag-training-traces --prefix processed/repo-rag-training/ --num-results 10 --auth-mode key --output table`
- `kubectl logs -n repo-rag deployment/repo-rag-trainer-service --tail=200`
- `kubectl logs -n repo-rag deployment/repo-rag-trainer-service --previous --tail=200`
- `kubectl describe pod -n repo-rag repo-rag-trainer-service-5c587db4bd-cdtl7`
- `kubectl get cronjob repo-rag-trainer-cycle -n repo-rag -o yaml`
- `kubectl get job -n repo-rag repo-rag-trainer-cycle-29629065 -o yaml`

Immediate deployment blocker now confirmed:

- the trainer image in AKS must be rebuilt from code that already includes
  `--min-new-candidates-for-recompile`, then redeployed, before queued traces will start draining
  again

## Latest Live Token-Cost Diagnosis

Fresh `dataset/artifacts` from the newest worker run show that retrieval quality and token spend
are now decoupled:

- `repo_rag_codex_proxy_last.json` still reported clean repo-rag evidence:
  - `README.md`
  - `docs/USAGE.md`
  - `docs/AGENTS.md`
  - `docs/ASSUMPTIONS.md`
- `repo_rag_outcome.json` reported:
  - `prompt_tokens = 1058957`
  - `completion_tokens = 0`
  - `total_tokens = 1058957`
- `repo_rag_trace.json` still reported:
  - `bundle_version = null`
  - `program_loaded = false`
  - `retrieval_mode = rag_heuristic_dspy`

That means DSPy still contributed no runtime savings in this live run because the worker again fell
back to heuristic mode instead of loading a compiled bundle.

The large token bill does **not** come from the repo-rag retrieval shortlist. The retrieved context
was only four sources with three evidence previews. The large bill comes from the long-running
`codex exec` transcript itself:

- `codex_response.txt` was `2115734` bytes
- the transcript explicitly includes the autonomous execution contract requiring
  `DEVPLAN.md`, `AGENTS.md`, `ENVS.md`, `USAGE.md`, `README.md`, and `ASSUMPTIONS.md` on every run
- the model then opened and revisited those docs repeatedly during its own repo exploration and
  diff loops

Measured directly from `codex_response.txt`:

- `# Environment Variables` appeared `3` times
- `docs/ENVS.md` appeared `72` times
- `diff --git a/docs/ENVS.md b/docs/ENVS.md` appeared `14` times
- `diff --git a/docs/USAGE.md b/docs/USAGE.md` appeared `18` times
- `diff --git a/docs/AGENTS.md b/docs/AGENTS.md` appeared `10` times

The transcript shows at least three direct full-file reads of `docs/ENVS.md`:

- line `157`: `sed -n '1,260p' docs/ENVS.md`
- line `24281`: `sed -n '1,220p' docs/ENVS.md`
- line `37694`: `sed -n '1,220p' docs/ENVS.md`

So the current cost story is:

- repo-rag retrieval no longer injects obviously wrong garbage like `prompt_artifacts/...`
- but the worker prompt contract still forces a broad documentation-maintenance workflow
- `codex exec` then repeatedly reads and diffs those docs, and that growing transcript dominates
  input-token spend

Additional artifact-inspection commands executed in this turn:

- `tar -xOf .../repo_rag_outcome.json | jq '{backend,bundle_version,token_usage,warnings,artifact_metadata}'`
- `tar -xOf .../repo_rag_codex_proxy_last.json | jq '{mediation_mode,rag_status,dspy_status,sources,evidence_previews,warnings}'`
- `tar -xOf .../repo_rag_trace.json | jq '{answer_length,source_count,context_count,evidence_count,sources,evidence_fingerprints,retrieval_mode,bundle_version,program_loaded}'`
- `tar -xOf .../codex_response.txt | rg -n '^# Environment Variables|docs/ENVS.md|ENVS.md|prompt_artifacts|docs/USAGE.md|docs/AGENTS.md|docs/ASSUMPTIONS.md'`
- `tar -xOf .../codex_response.txt | grep -o '# Environment Variables' | wc -l`
- `tar -xOf .../codex_response.txt | grep -o 'docs/ENVS.md' | wc -l`
- `tar -xOf .../codex_response.txt | grep -o 'diff --git a/docs/ENVS.md b/docs/ENVS.md' | wc -l`
- `tar -xOf .../codex_response.txt | grep -o 'diff --git a/docs/USAGE.md b/docs/USAGE.md' | wc -l`
- `tar -xOf .../codex_response.txt | grep -o 'diff --git a/docs/AGENTS.md b/docs/AGENTS.md' | wc -l`
