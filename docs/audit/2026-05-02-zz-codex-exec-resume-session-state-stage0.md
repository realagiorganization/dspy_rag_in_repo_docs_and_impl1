# Repository audit note for 2026-05-02 codex exec resume session state stage 0

## Scope

- Added the first worker-side slice for persistent Codex session continuity in `../dataset`.
- Kept the current repository planning and narrative surfaces aligned with that pivot.

## What changed

- Added [docs/planning/codex-exec-resume-plan.md](../planning/codex-exec-resume-plan.md) with a
  dedicated roadmap for moving workers from fresh `codex exec` starts to PVC-backed
  `codex exec resume` continuity.
- Confirmed locally that the current worker still starts fresh `codex exec` sessions while the
  installed Codex binary already exposes `codex exec resume`.
- Implemented hook order for worker temp Codex homes in `../dataset`:
  1. restore persisted session state into a fresh temp `CODEX_HOME`
  2. regenerate ephemeral `auth.json` / `config.toml`
  3. run guard preflight
  4. start Codex
  5. persist the non-credential session snapshot back to the PVC-backed cache root
- Added a first resumed execution path that uses `codex exec resume --last` when a restored
  session snapshot exists.
- Added a PVC-root `session-index.json` contract so each lane records restore metadata and the
  latest observed Codex session-file hint.
- Added a worker artifact surface `codex_session_state.json` so runs can report whether the worker
  used a fresh or resumed Codex session and whether guard/credential hydration succeeded.
- Added an initial restore-compatibility guard so the worker skips resume when persisted lane
  metadata no longer matches the current working directory or auth/config contract.
- Wired the worker manifest default `DATASET_CODEX_SESSION_STATE_DIR=/app/artifacts/_codex_sessions`
  so AKS runs pin Codex session snapshots to the actual artifacts PVC mount explicitly rather than
  relying on an implicit `exec_dir.parent` layout.
- Tightened the persisted snapshot scope to a current minimal durable allowlist:
  - `history.jsonl`
  - `sessions/`
  - `state_*.sqlite*`
  - `logs_*.sqlite*`
  - `shell_snapshots/`
  - `memories/`
  - `models_cache.json`
  - `installation_id`
  - `version.json`
- Added richer lane metadata:
  - repository fingerprint metadata derived from git state when available
  - resolved model/profile summary
  - explicit session mode transitions `fresh`, `reset`, `resumed`, `resumed-then-reset`
- Added a snapshot manifest guard so a partial or inconsistent persisted snapshot falls back to
  `reset` instead of attempting a broken resume.
- Added richer restore rejection rules so persisted snapshots now refuse resume when lane metadata
  shows:
  - repo-root mismatch
  - repo-branch mismatch
  - repo-drift threshold exceeded for same-lane git-head + dirty-state change
  - parsed model/profile mismatch beyond raw config-digest checks
- Added explicit reset controls and repeated-failure handling:
  - `DATASET_CODEX_SESSION_RESET` / `DATASET_CODEX_FORCE_FRESH` force one run to rebuild the lane
    from a fresh `codex exec`
  - `DATASET_CODEX_MAX_RESUME_FAILURES` blocks resume after repeated resume-fallback events until
    one clean reset run rebuilds the durable snapshot
  - `DATASET_CODEX_REPO_DRIFT_RESET_THRESHOLD` lets operators tune how much same-lane repository
    drift is tolerated before the worker forces `reset`
- Persisted `resume_failure_count` and `session_mode` through both lane metadata and
  `codex_session_state.json`, so a worker can report not only that it resumed/reset, but also why
  a reset happened and whether the lane is currently in a repeated-failure cooldown.
- Added explicit PVC sync-health telemetry in `codex_session_state.json`:
  - `restore_status`
  - `persist_status`
  - `pvc_sync_health`
- Added a local two-run worker proof in `../dataset` so the current suite now covers:
  - first run creates one durable Codex snapshot
  - second run on the same lane restores that snapshot and switches to `codex exec resume --last`
- Added divergent lane forking for Codex session reuse:
  - operators can hint a new lane through `DATASET_CODEX_SESSION_LANE`
  - prompts can override it with `codex_session_lane` / `session_lane`
  - when a hinted lane has no snapshot yet but the base repository lane does, the worker restores
    from that base lane and reports `codex_session_mode=forked`
  - persisted lane metadata plus `codex_session_state.json` now record `base_lane_key`,
    `fork_origin_lane_key`, `lane_hint`, and `forked_from_base`
- Added lane-level token telemetry to `codex_session_state.json`:
  - current usage metrics for the run
  - delta versus the previous run on the lane
  - delta versus the lane's last fresh baseline
  - persisted `latest_usage` / `last_fresh_usage` in lane metadata and `session-index.json`
- Added transcript-level path/read telemetry to `codex_session_state.json`:
  - `transcript_path_summary` now records path mentions, documentation-path mentions, read-like
    command counts, diff counts, and top repeated paths from the saved Codex transcript
  - `transcript_path_delta_vs_previous` and `transcript_path_delta_vs_last_fresh` allow later
    AKS validation to compare repeated file-reading behavior between fresh and resumed lanes
  - persisted lane metadata and `session-index.json` now retain both the latest transcript
    summary and the lane's last fresh transcript baseline
- Added downstream trace/outcome compatibility for resumed lanes:
  - Codex proxy trace exports now embed `codex_session_mode` and `codex_session_state`
  - `repo_rag_outcome.json` now carries the same Codex lane provenance, so trainer-side queued
    traces can distinguish `fresh`, `resumed`, and `forked` outcomes
- Added rollover policy controls for long-lived lanes:
  - `DATASET_CODEX_MAX_RESUMED_RUNS` forces `reset` when one lane has already resumed too many
    times
  - `DATASET_CODEX_MAX_SESSION_AGE_SECONDS` forces `reset` when a lane grows older than the
    configured wall-clock age
  - `DATASET_CODEX_PROMPT_TOKEN_GROWTH_RESET_RATIO` forces `reset` when the prior persisted
    `prompt_tokens` exceed a multiple of the lane's last fresh baseline
  - lane metadata now tracks `first_created_at_epoch`, `last_success_at_epoch`,
    `total_run_count`, `successful_run_count`, `fresh_run_count`, `resumed_run_count`,
    `reset_run_count`, and `forked_run_count`
- Added automatic task-family lane derivation:
  - `DATASET_CODEX_AUTO_SESSION_LANE_MODE` now derives a lane hint automatically when no explicit
    `DATASET_CODEX_SESSION_LANE` / `codex_session_lane` / `session_lane` override exists
  - supported modes are `queue_label`, `prompt_slug`, `queue_or_slug`, `slug_or_queue`, and
    `queue_and_slug`
  - this lets the worker keep unrelated queue families and prompt slugs out of one shared lane,
    reducing broad-context accumulation before rollover thresholds need to force `reset`
  - persisted lane state now also records `lane_source`, so later AKS/debug analysis can tell
    whether a lane came from an explicit operator/prompt hint or automatic prompt-family routing
- Wired those Codex session rollover env vars through the AKS worker manifest, so live workers can
  actually consume the new policy knobs instead of keeping them local-only.

## Verification executed in this turn

- `python -m compileall /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_codex_cli_helpers.py /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_codex_cli_exec.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_execute_worker_prompts_helpers_extra.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_worker_codex_cli_exec_small.py`
  - `pass`
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/unit/test_execute_worker_prompts_helpers_extra.py tests/unit/test_worker_codex_cli_exec_small.py -q`
  - `pass` (`51 passed`)
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/test_aks_module_generator_generate_modules.py tests/unit/test_execute_worker_prompts_helpers_extra.py tests/unit/test_worker_codex_cli_exec_small.py -q`
  - `pass` (`89 passed`)
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/unit/test_worker_codex_cli_exec_small.py -q`
  - `pass` (`27 passed`)
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/test_aks_module_generator_generate_modules.py tests/unit/test_execute_worker_prompts_helpers_extra.py tests/unit/test_worker_codex_cli_exec_small.py -q`
  - `pass` (`92 passed`)
- `python -m compileall /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_codex_cli_exec.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_worker_codex_cli_exec_small.py`
  - `pass`
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/unit/test_worker_codex_cli_exec_small.py -q`
  - `pass` (`32 passed`)
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/test_aks_module_generator_generate_modules.py tests/unit/test_execute_worker_prompts_helpers_extra.py tests/unit/test_worker_codex_cli_exec_small.py -q`
  - `pass` (`97 passed`)
- `python -m compileall /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_codex_cli_exec.py /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_execution_prompt.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_worker_codex_cli_exec_small.py`
  - `pass`
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/unit/test_worker_codex_cli_exec_small.py -q`
  - `pass` (`33 passed`)
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/test_aks_module_generator_generate_modules.py tests/unit/test_execute_worker_prompts_helpers_extra.py tests/unit/test_worker_codex_cli_exec_small.py -q`
  - `pass` (`98 passed`)
- `python -m compileall /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_execution_prompt.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py`
  - `pass`
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py -q`
  - `pass` (`11 passed`)
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/test_aks_module_generator_generate_modules.py tests/unit/test_execute_worker_prompts_helpers_extra.py tests/unit/test_worker_codex_cli_exec_small.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py -q`
  - `pass` (`109 passed`)
- `python -m compileall /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_codex_cli_exec.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_worker_codex_cli_exec_small.py`
  - `pass`
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/unit/test_worker_codex_cli_exec_small.py -q`
  - `pass` (`36 passed`)
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/test_aks_module_generator_generate_modules.py tests/unit/test_execute_worker_prompts_helpers_extra.py tests/unit/test_worker_codex_cli_exec_small.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py -q`
  - `pass` (`112 passed`)
- `python -m compileall /home/standard/Desktop/realagi_work/dataset/aks_module_generator/mixins/k8s_manifests.py /home/standard/Desktop/realagi_work/dataset/tests/test_aks_module_generator_generate_modules.py /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_codex_cli_exec.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_worker_codex_cli_exec_small.py`
  - `pass`
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/test_aks_module_generator_generate_modules.py tests/unit/test_execute_worker_prompts_helpers_extra.py tests/unit/test_worker_codex_cli_exec_small.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py -q`
  - `pass` (`113 passed`)
- `python -m compileall /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_execution_prompt.py /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_codex_cli_exec.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_worker_codex_cli_exec_small.py /home/standard/Desktop/realagi_work/dataset/tests/test_aks_module_generator_generate_modules.py`
  - `pass`
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/unit/test_worker_codex_cli_exec_small.py tests/test_aks_module_generator_generate_modules.py -q`
  - `pass` (`87 passed`)
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/test_aks_module_generator_generate_modules.py tests/unit/test_execute_worker_prompts_helpers_extra.py tests/unit/test_worker_codex_cli_exec_small.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py -q`
  - `pass` (`115 passed`)
- `uv run python -m compileall src tests`
  - `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`41 passed`)
- `uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`

### Deep live root-cause analysis after the latest failed `resume` run

The newest uploaded artifacts plus direct cluster inspection finally narrow the remaining failure
to one specific layer.

#### What the latest run proves

- The worker image **did** contain the newest `resume` diagnostics and command-selection code.
  The latest `codex_session_state.json` already includes:
  - `resume_target_session_id`
  - `resume_command_mode`
  - `restore_probe`
- The live prompt-worker job **did** mount the expected guild-scoped artifacts PVC:
  - namespace: `prompt-exec-1353735964635435100`
  - claim: `artifacts-g1353735964635435100`
  - mount: `/app/artifacts`
  - env:
    - `ARTIFACTS_DIR=/tmp/artifacts`
    - `DATASET_CODEX_SESSION_STATE_DIR=/app/artifacts/_codex_sessions`
- The current worker run **did** persist a valid Codex session snapshot into that PVC:
  - `/artifacts/_codex_sessions/session-index.json`
  - `/artifacts/_codex_sessions/realagiorganization_shards_of_lokar_game-a3fbd616bb4892c8/session_state.json`
  - `/artifacts/_codex_sessions/.../home_snapshot/installation_id`
  - `/artifacts/_codex_sessions/.../home_snapshot/logs_2.sqlite`
  - `/artifacts/_codex_sessions/.../home_snapshot/state_5.sqlite`
  - `/artifacts/_codex_sessions/.../home_snapshot/sessions/2026/05/04/rollout-2026-05-04T16-41-36-019df3dd-dc71-7aa1-b95b-ecad8cdae5af.jsonl`

#### What the latest run also proves

- The failure is **not** in the Codex on-disk layout anymore.
  The persisted snapshot already includes the JSONL session transcript plus the two SQLite files
  that match the normal Codex home shape.
- The failure is **not** a wrong-claim / wrong-namespace mount on the current worker.
  The captured live worker job manifest shows the same guild PVC claim and the explicit
  `DATASET_CODEX_SESSION_STATE_DIR=/app/artifacts/_codex_sessions` env that the code expects.
- The failure is **not** in the `resume` command assembly for this specific run.
  The worker never reached a state where resume was even attempted:
  - `resume_candidate_present = false`
  - `resume_attempted = false`
  - `resume_used = false`
  - `restore_status = fresh-no-snapshot`

#### The actual current blocker

For the latest failed run, startup inspection inside the worker reported:

- `persistent_root_exists = false`
- `lane_dir_exists = false`
- `index_path_exists = false`
- `persistent_root_parent_entries = ["runs", "worker_execution.log"]`
- `nested_session_root_count = 0`
- `nested_session_metadata_count = 0`

So, on **this** startup, the mounted `/app/artifacts` view contained only the run tree and the
root worker log. There was no pre-existing `_codex_sessions` subtree visible to restore from.

That aligns with the persisted session metadata now sitting on the PVC after the run:

- `first_created_at_epoch = 1777912896`
- `total_run_count = 1`
- `fresh_run_count = 1`
- `resumed_run_count = 0`

This is the critical correction to the earlier investigation:

- the recent worker-side fixes around explicit `latest_session_id`, localhost proxy normalization,
  nested search, and helper cleanup were **real**, but they addressed later restore/selection
  stages
- the latest live evidence shows those stages were never reached, because the new worker had no
  prior `_codex_sessions` snapshot visible on the mounted claim at startup

In other words, the current failed run was still a **seed run on the correct durable root**, not a
real second-run `resume` attempt on an already-seeded root.

#### Why the previous effort looked ineffective

The previous debugging rounds were too optimistic about what counted as a valid “next run”
verification. The root mistake in the investigation order was:

1. fixing restore guards / session-id targeting first
2. before proving that the exact live guild-scoped PVC root already contained a previous
   `_codex_sessions` snapshot visible to the next worker

The newest cluster-level inspection corrects that:

- current live PVC root now unquestionably contains the session snapshot
- current live worker manifest unquestionably points to that PVC root
- but the latest failed worker startup still saw no prior `_codex_sessions`
- therefore this run did **not** exercise the intended `resume` path yet

#### What remains unresolved after this deep analysis

The remaining open question is no longer “how should `codex exec resume` be invoked?”.
It is now strictly one of cross-run storage continuity:

- either older runs were still writing session state somewhere else (for example before the
  explicit `/app/artifacts/_codex_sessions` path became live in the worker image), or
- some external lifecycle step is removing or replacing `_codex_sessions` between runs before the
  next worker starts

The normal workflow code path inspected in this turn still does **not** show an automatic
root-level wipe of the artifacts PVC during a standard run:

- no normal workflow step invokes `tools/pvc_artifact_sync.sh reset`
- the only `--delete-extra` syncs target:
  - `.repo_rag_cache`
  - `.repo_rag_bundle_store`
- the worker manifest directly mounts `artifacts-g1353735964635435100` at `/app/artifacts`
  without a `subPath`

So the remaining bug is best described as:

- **live cross-run session continuity on the guild-scoped artifacts PVC has not yet been proven**
- **the latest run still seeded the durable root instead of restoring from an older lane snapshot**


## Local bundle-resolution follow-up after the worker artifact review

The next blocker investigation found two separate worker-side reasons that `bundle_resolved`
remained `false` even though `stable.json` existed on the trainer side:

- The staged worker mirror under `/tmp/artifacts/.repo_rag_bundle_store` uses the remote-store
  layout:
  - `channels/stable.json`
  - `versions/<bundle-version>/{bundle,metadata,program,published}.json`
- The local `repo-rag` fallback path still expected repo-style local artifacts under:
  - `artifacts/dspy/channels/*.json`
  - `artifacts/dspy/<run-name>/bundle.json`
- Separately, the live worker namespace secret `repo-rag-storage-config` currently contains only:
  - `DATASET_REPO_RAG_BUNDLE_CONTAINER`
  - `DATASET_REPO_RAG_TRACE_CONTAINER`
  - `DATASET_REPO_RAG_TRACE_QUEUE_NAME`
  and does **not** contain `AZURE_STORAGE_*` / `REPO_RAG_AZURE_STORAGE_*` credentials. That means
  worker-side global bundle lookup cannot rely on Blob credentials being present in the pod.

### Local fixes applied for bundle lookup

- current repository
  - `src/repo_rag_lab/runtime_artifacts.py`
  - `tests/test_runtime_artifacts_azure.py`
  - `repo-rag` local bundle lookup now supports both layouts:
    - repo-local `artifacts/dspy/...`
    - staged worker mirror `channels/...` + `versions/...`
  - `inspect_bundle_channel(...)` now also returns `channel_path` for found channels, which makes
    mirror-layout diagnostics explicit.
- `../dataset`
  - `aks_module_generator/templates/deployment_script/part_1.txt`
  - `aks_module_generator/templates/deployment_script/part_2.txt`
  - `tests/test_aks_module_generator_manifests.py`
  - The worker deployment script now refreshes `repo-rag-storage-config` at deploy time from the
    current Azure environment, including:
    - `AZURE_STORAGE_ACCOUNT`
    - `AZURE_STORAGE_KEY`
    - `AZURE_STORAGE_CONNECTION_STRING`
    - `REPO_RAG_AZURE_STORAGE_*`
    - bundle/trace container names and queue name
  - If only `AZURE_STORAGE_ACCOUNT` is present, the script now tries to resolve
    `AZURE_STORAGE_KEY` through `az storage account keys list`, matching the trainer-side pattern.

### Verification executed for those local fixes

- `uv run python -m compileall src tests`
  - `pass`
- `uv run pytest tests/test_runtime_artifacts_azure.py -q`
  - `pass` (`10 passed`)
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`41 passed`)
- `uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`
- `cd /home/standard/Desktop/realagi_work/dataset && python -m compileall aks_module_generator/templates/deployment_script/part_1.txt aks_module_generator/templates/deployment_script/part_2.txt tests/test_aks_module_generator_manifests.py`
  - `pass`
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/test_aks_module_generator_manifests.py -q`
  - `pass` (`31 passed`)

### Updated remaining blockers after this local slice

- Live worker-side DSPy bundle resolution still needs one rebuilt image plus redeploy/run to verify
  the new mirror-layout lookup and refreshed storage secret path in AKS.
- Live Codex session resume reuse still needs a second run against the same lane to prove that
  `_codex_sessions` now persists and restores end-to-end.
- `make files-sync`
  - `pass`
- `make verify-surfaces`
  - `pass`

## Current limitations

- The resumed path now supports one explicit divergent-lane trigger, but it still keys the base
  lane from the resolved repository working directory rather than a richer prompt-family plus
  repository-fingerprint contract.
- The worker records the latest observed session-file hint, not a formally documented Codex
  session-id contract, because this slice still resumes through `codex exec resume --last`.
- The compatibility guard now enforces working-directory, repo-root / branch, parsed
  model-profile, auth/config consistency, and a tunable same-lane repository-drift threshold.
- The remaining reset/fork work is now about post-rollover child-lane generation and live AKS
  validation, not about basic restore-vs-reset correctness or prompt-family lane splitting.
- Token-delta telemetry now exists locally, but no live AKS evidence exists yet showing that those
  deltas translate into materially lower paid input usage for real prompt families.
- Additional child-lane creation after rollover thresholds is still open; broad-context handling
  now splits prompt families automatically through `DATASET_CODEX_AUTO_SESSION_LANE_MODE`, but a
  lane that already exceeded age/resume-count/token-growth thresholds still rolls over through
  `reset`, not through a second-generation automatic child lane.
- Local coverage now proves `fresh -> resumed`, corruption fallback, operator reset, repeated
  resume-failure cooldown, and repo-drift reset, but it still does not prove AKS PVC behavior or

## 2026-05-03 live follow-up after rebuilt images and trainer redeploy

### Live actions executed

- `cd /home/standard/Desktop/realagi_work/dataset && BUILD_MODE=acr ./build_and_push_images.sh`
  - `pass`
  - produced:
    - `llmpromptsacr.azurecr.io/repo-rag-runtime:20260503-153814`
    - `llmpromptsacr.azurecr.io/prompt-executor:20260503-153814`
    - `llmpromptsacr.azurecr.io/queue-initializer:20260503-153814`
- `cd /home/standard/Desktop/realagi_work/dataset && IMAGE_TAG=20260503-153814 ./deploy_repo_rag_trainer.sh`
  - `pass`
  - live trainer rollout completed onto `repo-rag-runtime:20260503-153814`

### Live trainer observations

- New service pod:
  - `repo-rag-trainer-service-7b8c8fbf8-f7qnv`
  - image `llmpromptsacr.azurecr.io/repo-rag-runtime:20260503-153814`
- New trainer cycle history now proves the stale-queue skip is live:
  - `artifacts/trainer/history/20260503T155304Z-cycle-0001.json`
  - `queue_drain.failed_count = 0`
  - `queue_drain.skipped_count = 1`
  - skipped item tagged as:
    - `skip_reason = "stale-queue-blob"`
    - `error_type = "ResourceNotFoundError"`
- This confirms the rebuilt image now skips the old missing queue blob instead of treating it as a
  drain failure.

### Remaining live issue after the stale-queue fix

- The new live cycle still recorded `command_status = "fail"` even though the stale blob was
  skipped cleanly and no new training candidates were imported.
- Root cause from local code inspection:
  - `trainer-cycle` still treated `promote_channel=stable` as enough reason to require
    `minimum_bundle_pass_rate`
  - when no new bundle candidate existed, `_build_bundle_benchmark_gate(...)` fell back to the
    last local bundle manifest (`20260502T180452813814Z`) and failed the cycle on that old gate
  - this left `promotion_status = "blocked"` and `command_status = "fail"` for a no-op cycle

### Local fix applied after that live observation

- `src/repo_rag_lab/utilities.py`
  - bundle-gate requirement is now enabled only when there is an explicit bundle candidate:
    - explicit `run_name` / `bundle_version`
    - or a trainer-side recompilation that actually produced a bundle candidate
  - `promotion_requested` is now explicit and false for `stable`-configured no-op cycles
  - retrieval gate failure no longer marks the cycle as failed when there is no bundle candidate
    to publish or promote
- `tests/test_utilities.py`
  - added coverage for:
    - no new candidates + `promote_channel=stable` + failed retrieval gate -> `command_status=success`
    - no publish / no promotion side effects in that case

### Verification executed for that local fix

- `uv run python -m compileall src tests`
  - `pass`
- `uv run pytest tests/test_utilities.py -k 'run_trainer_cycle and (skips_recompile_and_publish_without_new_candidates or does_not_fail_promotion_without_new_bundle_candidate or bundle_gate_failure)' -q`
  - `pass` (`2 passed`)
- `uv run pytest tests/test_utilities.py -k 'run_trainer_service' -q`
  - `pass` (`2 passed`)
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`42 passed`)
- `uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`

### Current repository state after this follow-up

- Live trainer image rebuild and redeploy are confirmed.
- Live stale-queue skipping is confirmed.
- The no-op-cycle false-fail fix is local-only until the repository is pushed and the trainer image
  is rebuilt once more.
- Worker-side DSPy bundle resolution and worker-side `codex exec resume` still need one fresh AKS
  worker run after the updated images and deployment script are used by the prompt-execution path.
  token-cost reduction under a real worker rollout.
- No live AKS proof exists yet for resumed Codex sessions, PVC restoration, or token-cost
  reduction. This slice is local-code and unit-test verified only.

## Repository state after this slice

- The architectural pivot is now explicit in repository planning and narrative docs.
- The first worker implementation slice exists for:
  - restoring persisted Codex state into a new temp home,
  - hydrating fresh credentials into that home,
  - running guard preflight on resumed runs,
  - resuming the last local Codex session when a snapshot exists,
  - writing back the updated non-credential session state for the next worker run,
  - surfacing lane metadata through `session-index.json` and `codex_session_state.json`,
  - pinning the default AKS session root to the artifacts PVC through
    `DATASET_CODEX_SESSION_STATE_DIR=/app/artifacts/_codex_sessions`,
  - skipping restore automatically when the persisted auth/config contract no longer matches the
    current worker run,
  - using a current minimal durable snapshot allowlist instead of a whole-home copy,
  - validating restored snapshots against an explicit snapshot manifest before attempting resume,
  - exposing richer session modes and repo/model lane metadata for later live validation,
  - allowing explicit operator reset and repeated-failure cooldown through documented worker env
    controls,
  - forking a new lane from an existing repository lane through `DATASET_CODEX_SESSION_LANE` or
    prompt-level lane hints while preserving fork provenance in worker artifacts,
  - deriving automatic task-family lanes from `queue_label` / `prompt_slug` through
    `DATASET_CODEX_AUTO_SESSION_LANE_MODE` while surfacing `lane_source` in persisted state,
  - reporting lane-local token deltas versus the previous run and the last fresh baseline in
    `codex_session_state.json`,
  - carrying Codex lane provenance forward into repo-RAG trace/outcome payloads so downstream DSPy
    training can correlate trainer candidates with `fresh`, `resumed`, and `forked` worker lanes,
  - forcing `reset` instead of resume when lane age, resumed-run count, or prompt-token growth
    show that the existing session is likely too broad to remain efficient,
  - exposing those rollover env knobs in the AKS worker manifest so live deployments can opt in
    without another code change.

## Live artifact check on 2026-05-03

The latest uploaded worker artifacts and the live trainer pod show that the repository-level
resume design is implemented, but the end-to-end worker/trainer loop is still only partially
working in AKS.

### Worker outcome

- The latest worker run completed successfully and recorded `328850` prompt tokens in
  `dataset/artifacts/redis_results.json`.
- `repo_rag_backend.json` reported:
  - `backend = codex_cli_repo_rag_proxy`
  - `rag_status = success`
  - `dspy_status = heuristic`
  - `bundle_resolved = false`
  - `trace_handoff_status = queued`
- `repo_rag_trace.json` reported:
  - `program_loaded = false`
  - `bundle_version = null`
  - `codex_session_mode = fresh`
- `codex_session_state.json` reported:
  - `resume_candidate_present = false`
  - `resume_attempted = false`
  - `resume_used = false`
  - `restore_status = fresh-no-snapshot`
  - `persist_status = persisted-empty`
  - `pvc_sync_health = degraded`
  - `persisted_files = 0`
- The exported artifact tarball did **not** contain `_codex_sessions/`, `session-index.json`, or
  any restored snapshot payloads, so this AKS run did not yet prove durable Codex session reuse.

### RAG and transcript behavior

- `repo_rag_codex_proxy_last.json` showed clean repo-grounded retrieval sources:
  - `README.md`
  - `docs/AGENTS.md`
  - `docs/ASSUMPTIONS.md`
  - `docs/USAGE.md`
- `prompt_artifacts/...` no longer appeared in the retrieval sources and did not appear in the
  exported `codex_response.txt`.
- The transcript still remained documentation-heavy because the worker contract explicitly requires
  those docs on each run. In the latest `codex_response.txt`:
  - `README.md` appeared `47` times
  - `docs/DEVPLAN.md` appeared `41` times
  - `docs/AGENTS.md` appeared `42` times
  - `docs/ENVS.md` appeared `39` times
  - `docs/USAGE.md` appeared `42` times
  - `docs/ASSUMPTIONS.md` appeared `41` times
  - each of those files had one direct `sed -n` read and seven repeated `diff --git` blocks
- The `# Environment Variables` heading from `docs/ENVS.md` appeared once in the transcript, from
  one explicit `sed -n '1,260p' docs/ENVS.md` read.

### Trainer state

- The worker-side trusted handoff succeeded:
  - `trusted_trace_handoff_summary.json` reported `queued = 1`, `failed = 0`
- The live trainer pod recovered the latest processed trace
  `20260503T085906Z-prompts_shards_of_lokar_game-p00000-355cca.json`, so the new run did reach
  trainer-side durable recovery.
- The trainer service is still unhealthy overall. Live `artifacts/trainer/service-state.json`
  showed:
  - `cycles_executed = 71`
  - `successful_cycle_count = 0`
  - `failed_cycle_count = 71`
  - `total_recompiled_run_count = 0`
  - `total_skipped_recompile_count = 71`
  - `total_publish_count = 0`
  - `total_promotion_count = 0`
- The latest cycle failed because:
  - queue drain still hits one stale `failed/...` blob with `BlobNotFound`
  - `new_candidate_count = 0`, so recompilation was skipped
  - the retrieval gate still blocks promotion
- The live stable channel still points at bundle `20260502T122127191445Z`, so worker-side DSPy
  fallback remains expected until bundle resolution and trainer health are fixed.

### Verification executed for this live check

- `uv run python -m compileall src tests`
  - `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`41 passed`)
- `uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`
- `kubectl -n repo-rag exec repo-rag-trainer-service-766448db7b-hj4j6 -- sh -lc 'cd /workspace/repo-rag && sed -n "1,260p" artifacts/trainer/service-state.json'`
  - `pass`
- `kubectl -n repo-rag exec repo-rag-trainer-service-766448db7b-hj4j6 -- sh -lc 'cd /workspace/repo-rag && latest=$(ls -1t artifacts/trainer/history | head -n 1); sed -n "1,260p" artifacts/trainer/history/$latest'`
  - `pass`
- `kubectl -n repo-rag exec repo-rag-trainer-service-766448db7b-hj4j6 -- sh -lc 'cd /workspace/repo-rag && sed -n "1,220p" artifacts/dspy/channels/stable.json'`
  - `pass`

### Updated status summary

- Live RAG isolation: `pass`
- Live DSPy bundle use in worker: `fail`
- Live Codex session resume reuse in worker: `not yet demonstrated`
- Live trainer queue recovery of the latest trace: `pass`
- Live trainer service health / publish-promote loop: `fail`

## Local fixes after the live artifact review

Two follow-up fixes were applied locally after the 2026-05-03 live artifact inspection:

- `../dataset`
  - `docker/prompt-executor/worker_codex_cli_helpers.py`
  - `docker/prompt-executor/worker_codex_cli_exec.py`
  - The worker now flushes Codex HOME persistence before writing `codex_session_state.json` and
    returning the result payload. This fixes the stale telemetry case where the live artifact could
    report `persisted-empty` / `degraded` even though the actual persist hook ran later during
    context-manager teardown.
- current repository
  - `src/repo_rag_lab/runtime_artifacts.py`
  - `tests/test_runtime_artifacts_azure.py`
  - Trainer queue drain now treats any Azure queue pointer whose target blob already disappeared as
    a harmless stale queue message, not just stale `failed/...` pointers. Missing `queued/...`
    blobs now produce `skip_reason = stale-queue-blob` and no longer needlessly poison the cycle
    with `failed_count = 1`.

### Verification executed for those local fixes

- `cd /home/standard/Desktop/realagi_work/dataset && python -m compileall docker/prompt-executor/worker_codex_cli_exec.py docker/prompt-executor/worker_codex_cli_helpers.py tests/unit/test_worker_codex_cli_exec_small.py`
  - `pass`
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/unit/test_worker_codex_cli_exec_small.py -q`
  - `pass` (`36 passed`)
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/test_aks_module_generator_generate_modules.py tests/unit/test_worker_codex_cli_exec_small.py -q`
  - `pass` (`74 passed`)
- `uv run python -m compileall src tests`
  - `pass`
- `uv run pytest tests/test_runtime_artifacts_azure.py -q`
  - `pass` (`8 passed`)
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`41 passed`)
- `uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`

## 2026-05-03 live follow-up after trainer no-op cycle rebuild

After the local `trainer-cycle` no-op promotion fix was committed, a fresh ACR build and live
trainer redeploy were completed from `../dataset`:

- `BUILD_MODE=acr ./build_and_push_images.sh`
  - `pass`
  - built and pushed:
    - `llmpromptsacr.azurecr.io/repo-rag-runtime:20260503-160343`
    - `llmpromptsacr.azurecr.io/prompt-executor:20260503-160343`
    - `llmpromptsacr.azurecr.io/queue-initializer:20260503-160343`
- `cd /home/standard/Desktop/realagi_work/dataset && IMAGE_TAG=20260503-160343 ./deploy_repo_rag_trainer.sh`
  - `pass`

### Live trainer state after redeploy

- The live trainer service deployment now uses
  `llmpromptsacr.azurecr.io/repo-rag-runtime:20260503-160343`.
- The trainer CronJob template also now points at
  `llmpromptsacr.azurecr.io/repo-rag-runtime:20260503-160343`.
- The new service pod wrote its first service-cycle file:
  - `artifacts/trainer/history/20260503T161713Z-cycle-0001.json`

### Live validation of the no-op trainer-cycle fix

The new service-cycle from `20260503T161713Z-cycle-0001.json` confirms that a no-op cycle no
longer fails just because `promote_channel=stable` is configured:

- `command_status = success`
- `training_candidates.new_candidate_count = 0`
- `recompile.recompile_status = skipped-no-new-candidates`
- `publish_requested = false`
- `promotion_requested = false`
- `promotion_status = not-requested`
- `queue_drain.status = success`
- `queue_drain.failed_count = 0`

The only warning left in that cycle is the expected no-op warning:

- `Trainer-side bundle recompilation was skipped because no new training candidates were imported during this cycle.`

This removes the previous false-negative service behavior where the cycle ended with:

- `command_status = fail`
- `promotion_status = blocked`
- a stale `bundle_gate` failure against the historical local manifest
  `artifacts/dspy/20260502T180452813814Z/bundle.json`

### Operational cleanup after redeploy

- A stale pre-redeploy CronJob execution was still running on the older image and inherited the
  old false-failing behavior.
- The old job `repo-rag-trainer-cycle-29630400` was deleted so `concurrencyPolicy=Forbid` would
  stop blocking new scheduled jobs.
- A replacement job `repo-rag-trainer-cycle-29630415-mtpkl` then appeared and is now running on
  `llmpromptsacr.azurecr.io/repo-rag-runtime:20260503-160343`.

### Updated live trainer status summary

- Live trainer queue drain stale-pointer handling: `pass`
- Live trainer no-op cycle success semantics: `pass`
- Live worker-side DSPy bundle use: `still failing`
- Live worker-side Codex session resume reuse: `still not demonstrated`

## 2026-05-03 worker artifact follow-up after the rebuilt trainer/service fixes

Fresh worker artifacts from `../dataset/artifacts` now show that worker-side DSPy bundle
resolution is live:

- `repo_rag_backend.json`
  - `bundle_resolved = true`
  - `bundle_version = 20260502T122127191445Z`
  - `mediation_mode = dspy_rag`
  - `rag_status = success`
  - `dspy_status = success`
- `repo_rag_trace.json`
  - `program_loaded = true`
  - `program_path = artifacts/dspy/remote/20260502T122127191445Z/program.json`

That means the earlier worker-side `stable`/bundle lookup gap is now closed for the current AKS
path. Trainer-side recovered traces confirm the same outcome: the live service now reports
`retrieval_mode_counts.dspy_rag = 2` and `bundle_version_counts.20260502T122127191445Z = 2`.

### RAG behavior in this run

- Retrieval remained clean and repo-grounded:
  - `README.md`
  - `docs/AGENTS.md`
  - `docs/ASSUMPTIONS.md`
  - `docs/USAGE.md`
- `prompt_artifacts/...` no longer appeared in either retrieval sources or the exported
  `codex_response.txt`.

So the current live repo-RAG path is no longer polluting evidence with worker-generated prompt
artifacts.

### Codex session reuse state in this run

`codex_session_state.json` still shows a first-run lane rather than a resumed lane:

- `session_mode = fresh`
- `restore_status = fresh-no-snapshot`
- `resume_candidate_present = false`
- `resume_attempted = false`
- `resume_used = false`
- `persist_status = persisted`
- `pvc_sync_health = healthy`
- `persisted_files = 4`

This is expected for the first run on a new lane. The worker did persist a durable session
snapshot successfully, so the next run against the same lane is the one that should prove
`codex exec resume`.

### Token cost and transcript behavior

The run still consumed very high prompt tokens:

- `redis_results.json`
  - `prompt_tokens = 995058`
  - `total_tokens = 995058`

The main cost driver remains the autonomous Codex transcript, not retrieval pollution:

- `codex_response.txt` size: `1,255,938` bytes
- repeated document references:
  - `README.md`: `245`
  - `docs/DEVPLAN.md`: `42`
  - `docs/AGENTS.md`: `42`
  - `docs/ENVS.md`: `42`
  - `docs/USAGE.md`: `42`
  - `docs/ASSUMPTIONS.md`: `44`
- command repetition:
  - `diff --git`: `169`
  - `sed -n`: `42`

The `# Environment Variables` heading still appeared twice in the transcript because `docs/ENVS.md`
is still read and then reappears in later diff blocks. That is no longer a repo-RAG retrieval
problem; it is a fresh-session Codex execution-contract problem.

### Trainer-side handoff for this run

- `trusted_trace_handoff_summary.json`
  - `queued = 1`
  - `failed = 0`
- live trainer `recovered-imported-traces/` now includes:
  - `20260503T175254Z-worker-0-prompts_shards_of_lokar_game-p00000-355cca-realagiorganization_shards_of_lokar_game.json`
  - `20260503T175421Z-prompts_shards_of_lokar_game-p00000-355cca.json`

The latest live service cycle still ends as a no-op success with:

- `command_status = success`
- `new_candidate_count = 0`
- `recompile_status = skipped-no-new-candidates`

### Verification executed for this follow-up

- `uv run python -m compileall src tests`
  - `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`42 passed`)
- `uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`

### Updated status summary after this run

- Live RAG isolation: `pass`
- Live worker-side DSPy bundle resolution/use: `pass`
- Live worker-side Codex session resume reuse: `not yet demonstrated`
- Live trainer queue handoff and recovery: `pass`
- Live trainer no-op publish/promote semantics: `pass`
- Token-efficiency goal: `still failing`

## 2026-05-04 worker artifact follow-up after another fresh run

Another worker artifact export from `../dataset/artifacts` confirms that the improved worker path
is stable, but the new run still started as a fresh lane instead of a resumed lane.

### Worker-side runtime results

- `repo_rag_backend.json`
  - `bundle_resolved = true`
  - `bundle_version = 20260502T122127191445Z`
  - `mediation_mode = dspy_rag`
  - `rag_status = success`
  - `dspy_status = success`
- `repo_rag_trace.json`
  - `program_loaded = true`
  - `program_path = artifacts/dspy/remote/20260502T122127191445Z/program.json`
- `repo_rag_outcome.json`
  - `codex_session_mode = fresh`

### RAG and transcript quality

- Retrieval sources remained clean:
  - `README.md`
  - `docs/AGENTS.md`
  - `docs/ASSUMPTIONS.md`
  - `docs/USAGE.md`
- `prompt_artifacts/...` did not appear in retrieval sources or `codex_response.txt`.

The transcript was still documentation-heavy, but materially smaller than the previous
2026-05-03 fresh run:

- `redis_results.json`
  - `prompt_tokens = 173495`
  - `total_tokens = 173495`
- `codex_response.txt` size: `768616` bytes
- repeated document references:
  - `README.md`: `48`
  - `docs/DEVPLAN.md`: `38`
  - `docs/AGENTS.md`: `35`
  - `docs/ENVS.md`: `39`
  - `docs/USAGE.md`: `37`
  - `docs/ASSUMPTIONS.md`: `40`
- command repetition:
  - `diff --git`: `88`
  - `sed -n`: `33`

So token use is still high, but much lower than the prior `995058`-token fresh run. The main
remaining cost driver is still repetitive documentation reads/diffs inside the autonomous Codex
transcript rather than retrieval pollution.

### Codex session state for this run

`codex_session_state.json` still reports a first-run lane:

- `session_mode = fresh`
- `restore_status = fresh-no-snapshot`
- `resume_candidate_present = false`
- `resume_attempted = false`
- `resume_used = false`
- `persist_status = persisted`
- `pvc_sync_health = healthy`
- `persisted_files = 4`

The lane key is still stable:

- `lane_key = realagiorganization_shards_of_lokar_game-a3fbd616bb4892c8`

but the exported artifact tarball still does **not** include `_codex_sessions/` or
`session-index.json`. That means the worker is persisting some Codex session files internally,
yet the current artifact export still does not prove that the next worker pod can see the prior
lane snapshot.

### Trainer-side state after this run

The trusted handoff succeeded again:

- `trusted_trace_handoff_summary.json`
  - `queued = 1`
  - `failed = 0`

The live trainer service remained healthy:

- latest service cycle: `20260504T082430Z-cycle-0536.json`
- `command_status = success`
- `new_candidate_count = 0`
- `processed_count = 23`
- `restored_count = 23`
- `retrieval_mode_counts`
  - `dspy_rag = 4`
  - `rag_heuristic_dspy = 19`
- `bundle_version_counts`
  - `20260502T122127191445Z = 4`

So trainer-side recovery clearly sees the newer DSPy-backed worker traces.

### Verification executed for this follow-up

- `uv run python -m compileall src tests`
  - `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`42 passed`)
- `uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`

### Updated status summary after the 2026-05-04 run

- Live RAG isolation: `pass`
- Live worker-side DSPy bundle resolution/use: `pass`
- Live trainer queue handoff and recovery: `pass`
- Live trainer no-op publish/promote semantics: `pass`
- Live worker-side Codex session resume reuse: `still not demonstrated`
- Token-efficiency goal: `improved but still failing`

## Root cause analysis for the repeated `fresh` Codex session starts

The 2026-05-04 run was expected to resume the existing lane
`realagiorganization_shards_of_lokar_game-a3fbd616bb4892c8`, but it still reported:

- `session_mode = fresh`
- `restore_status = fresh-no-snapshot`
- `resume_candidate_present = false`
- `resume_attempted = false`
- `resume_used = false`

The root cause is now clear from the current `dataset` wiring:

- `dataset/aks_module_generator/mixins/k8s_manifests.py`
  - worker env exports:
    - `ARTIFACTS_DIR=/tmp/artifacts`
    - `DATASET_CODEX_SESSION_STATE_DIR=/tmp/artifacts/_codex_sessions`
- `dataset/aks_module_generator/mixins/attachments.py`
  - the shared artifacts PVC is mounted only at:
    - `/app/artifacts`

So the worker was writing its Codex session snapshot into `/tmp/artifacts/_codex_sessions`, while
the durable RWX artifacts PVC is mounted at `/app/artifacts`. A new worker pod gets a fresh `/tmp`,
so the next run could not see the previous lane snapshot even though the worker reported:

- `persist_status = persisted`
- `persisted_files = 4`
- `pvc_sync_health = healthy`

Those values only describe the local write into the configured session root; they do **not** prove
that the configured root itself is on the shared PVC.

### Supporting evidence

- The lane key stayed stable across runs:
  - `realagiorganization_shards_of_lokar_game-a3fbd616bb4892c8`
- The pipeline namespace and artifacts PVC are long-lived:
  - namespace `prompt-exec-1353735964635435100`
  - PVC `artifacts-g1353735964635435100`
- Yet the next run still reported:
  - `restored_files = 0`
  - `resume_candidate_present = false`
  - a new `first_created_at_epoch`
- The exported artifact tarball still contains no `_codex_sessions/` or `session-index.json`,
  which matches the current broken persistence contract.

### Conclusion

The current blocker for live `codex exec resume` is **not** DSPy, lane hashing, or trainer
handoff. It is a storage-path mismatch:

- durable artifacts mount: `/app/artifacts`
- configured Codex session root: `/tmp/artifacts/_codex_sessions`

That mismatch is now fixed locally in `dataset` by retargeting the generated worker env to
`DATASET_CODEX_SESSION_STATE_DIR=/app/artifacts/_codex_sessions` while leaving prompt-scoped
execution artifacts under `/tmp/artifacts`. Live AKS validation is still pending; until a rebuilt
worker image is deployed and rerun, the latest uploaded runs should still be expected to show
`fresh-no-snapshot`.

## 2026-05-04 worker artifact follow-up after the PVC session-root fix

Fresh worker artifacts uploaded from `../dataset/artifacts` show that the rebuilt worker image is
now using the corrected Codex session root:

- `codex_session_state.json`
  - `persistent_root = /app/artifacts/_codex_sessions`
  - `lane_dir = /app/artifacts/_codex_sessions/realagiorganization_shards_of_lokar_game-a3fbd616bb4892c8`
  - `index_path = /app/artifacts/_codex_sessions/session-index.json`

That confirms the current worker image includes the path fix from `dataset`.

### What worked

- `repo_rag_backend.json`
  - `bundle_resolved = true`
  - `bundle_version = 20260502T122127191445Z`
  - `mediation_mode = dspy_rag`
  - `rag_status = success`
  - `dspy_status = success`
- `repo_rag_trace.json`
  - `program_loaded = true`
  - `program_path = artifacts/dspy/remote/20260502T122127191445Z/program.json`
- `trusted_trace_handoff_summary.json`
  - `queued = 1`
  - `failed = 0`

Retrieval remained clean and repo-grounded:

- `README.md`
- `docs/AGENTS.md`
- `docs/ASSUMPTIONS.md`
- `docs/USAGE.md`

`prompt_artifacts/...` did not appear in `repo_rag_codex_proxy_last.json` retrieval sources. The
runtime still emits prompt traces under the worker artifact tree, which is expected, but retrieval
did not use them.

### What did not work

`codex exec resume` still did not activate in this run:

- `session_mode = fresh`
- `restore_status = fresh-no-snapshot`
- `resume_candidate_present = false`
- `resume_attempted = false`
- `resume_used = false`
- `restored_files = 0`
- `persisted_files = 4`
- `persist_status = persisted`
- `pvc_sync_health = healthy`

This is now a different situation from the previous broken runs. Earlier runs could never resume
because session snapshots were written under `/tmp/artifacts/_codex_sessions`, which was not on the
durable PVC. This run already writes to `/app/artifacts/_codex_sessions`, so the most likely
reading is:

- this run is the first live run on the corrected durable session root
- it seeded the durable lane snapshot successfully
- the **next** run on the same lane is the one that should finally prove `resumed`

The current artifact export still does not include `_codex_sessions/` or `session-index.json`,
only the per-run `codex_session_state.json`, so the uploaded tarball itself still cannot prove that
the next pod will see the snapshot. The state file, however, now points at the correct durable PVC
location.

## 2026-05-04 restore-path debug follow-up after inspecting the live PVC

The next uploaded run still started as `fresh`, so the session-root path mismatch is no longer a
sufficient explanation by itself. Live PVC inspection now confirms that the worker **is** writing
durable Codex lane state into the shared artifacts claim:

- namespace `prompt-exec-1353735964635435100`
- PVC `artifacts-g1353735964635435100`
- `_codex_sessions/session-index.json`
- `_codex_sessions/realagiorganization_shards_of_lokar_game-a3fbd616bb4892c8/session_state.json`
- `_codex_sessions/.../home_snapshot/history.jsonl`
- `_codex_sessions/.../home_snapshot/state_5.sqlite`
- `_codex_sessions/.../home_snapshot/logs_2.sqlite`
- `_codex_sessions/.../home_snapshot/sessions/2026/05/04/rollout-2026-05-04T10-29-28-019df289-272d-7401-8353-03aa49369449.jsonl`

That means the remaining blocker moved again: the worker startup path is still not discovering an
already-persisted lane snapshot at restore time even though the snapshot is present on the shared
PVC.

To harden that restore path locally, `dataset/docker/prompt-executor/worker_codex_cli_exec.py`
now adds:

- a `restore_probe` block in `codex_session_state.json` so the next live run can report what the
  worker actually saw under `persistent_root`, whether `session-index.json` existed, and which
  candidate source was selected
- an index-based fallback: if the direct `lane_dir` probe misses, restore now consults
  `session-index.json` for matching `lane_key`, `base_lane_key`, `working_dir`, and repo
  fingerprint entries
- a filesystem fallback: if the index is missing or stale, restore now scans
  `persistent_root/*/session_state.json` for matching workspace metadata before giving up and
  treating the run as `fresh`

This does **not** prove live `resumed` behavior yet. It does mean the next worker image should be
able to recover from lane/index drift cases that the previous implementation silently collapsed into
`fresh-no-snapshot`, and if it still fails the new `restore_probe` fields should identify whether
the worker saw the PVC root at all.

### Local verification for the restore-debug slice

Dataset-side checks executed after adding the new fallback/probe logic:

- `python -m compileall docker/prompt-executor/worker_codex_cli_exec.py tests/unit/test_worker_codex_cli_exec_small.py`
  - `pass`
- `uv run pytest tests/unit/test_worker_codex_cli_exec_small.py -q`
  - `pass` (`37 passed`)
- `uv run pytest tests/test_aks_module_generator_generate_modules.py -k disk_backed_paths -q`
  - `pass`

Repository-native checks rerun in this repo while updating the audit narrative:

- `uv run python -m compileall src tests`
  - `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`42 passed`)
- `uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`
- `make verify-surfaces`
  - `pass`

### Token cost and transcript behavior

Prompt-token spend is still far too high:

- `redis_results.json`
  - `result.prompt_tokens = 3427041`
  - `result.total_tokens = 3427041`
- `codex_response.txt` size: `2,205,535` bytes

The transcript remains heavily documentation/diff driven:

- `README.md`: `167`
- `docs/DEVPLAN.md`: `149`
- `docs/ENVS.md`: `115`
- `docs/AGENTS.md`: `124`
- `docs/USAGE.md`: `119`
- `docs/ASSUMPTIONS.md`: `76`
- `diff --git`: `380`
- `sed -n`: `44`
- `# Environment Variables`: `2`

So the current state is:

- live RAG isolation: `pass`
- live worker-side DSPy bundle use: `pass`
- live trainer handoff: `pass`
- live Codex resume path fix in image: `pass`
- live Codex session reuse proof: `not yet demonstrated`
- token-efficiency goal: `fail`

## 2026-05-04 latest worker artifact review after the restore-fallback patch

The next uploaded worker run still did **not** resume:

- `codex_session_mode = fresh`
- `restore_status = fresh-no-snapshot`
- `resume_candidate_present = false`
- `resume_attempted = false`
- `resume_used = false`
- `persist_status = persisted`
- `pvc_sync_health = healthy`
- `persisted_files = 6`

The new `restore_probe` block makes the failure mode narrower and clearer than before:

- `persistent_root_exists = false`
- `lane_dir_exists = false`
- `snapshot_dir_exists = false`
- `metadata_path_exists = false`
- `index_path_exists = false`
- `index_entry_count = 0`

So this latest live run did **not** merely fail to match a lane or read stale metadata. At worker
startup, the process reported that `/app/artifacts/_codex_sessions` itself was absent from its
filesystem view. That means the remaining live blocker has shifted from the restore-selection logic
into the pod runtime/storage path: the worker is still starting without seeing the durable session
root at restore time, even though the same run later persists a fresh snapshot there successfully.

### What worked in the latest run

- `repo_rag_backend.json`
  - `rag_status = success`
  - `dspy_status = success`
  - `mediation_mode = dspy_rag`
  - `bundle_resolved = true`
  - `bundle_version = 20260502T122127191445Z`
- `repo_rag_trace.json`
  - `program_loaded = true`
  - `program_path = artifacts/dspy/remote/20260502T122127191445Z/program.json`
- `repo_rag_trace_enqueue.json`
  - `queue_status = queued`
- `repo_rag_codex_proxy_last.json`
  - retrieval sources stayed clean:
    - `docs/AGENTS.md`
    - `docs/ASSUMPTIONS.md`
    - `README.md`
    - `docs/USAGE.md`
- `prompt_artifacts` did not leak back into retrieval or the visible Codex transcript.

### What still did not work

- `codex exec resume` still did not activate.
- The worker still started from a `fresh` session with no cached input reuse visible in usage:
  - `prompt_tokens = 559267`
  - `completion_tokens = 0`
  - `total_tokens = 559267`
  - `cached_input_tokens = null`

### Token cost and transcript behavior in this latest run

The transcript remains doc-heavy and diff-heavy, which means the dominant cost is still the
growing internal `codex exec` conversation rather than the initial `RAG` / `DSPy` mediation
payload:

- `codex_response.txt` size: `1,382,973` bytes
- repeated mentions:
  - `README.md`: `81`
  - `docs/DEVPLAN.md`: `97`
  - `docs/ENVS.md`: `48`
  - `docs/AGENTS.md`: `42`
  - `docs/USAGE.md`: `71`
  - `docs/ASSUMPTIONS.md`: `84`
  - `diff --git`: `198`
  - `sed -n`: `50`

The first read commands in the transcript show the same pattern as earlier fresh runs:

- `sed -n '1,260p' docs/USAGE.md`
- `sed -n '1,220p' docs/AGENTS.md`
- `sed -n '1,220p' docs/ASSUMPTIONS.md`
- `sed -n '1,260p' README.md`
- `sed -n '1,260p' docs/DEVPLAN.md`
- `sed -n '1,240p' docs/ENVS.md`

That is consistent with:

- live `RAG` isolation: `pass`
- live `DSPy` mediation: `pass`
- live trainer handoff: `pass`
- live restore-fallback code path in image: `present`
- live session-root visibility at worker startup: `fail`
- live resume proof: `fail`
- token-efficiency goal: `fail`

### Repository-native verification rerun in this turn

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`42 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`

### Latest local continuity-marker and guard-preflight isolation follow-up

The newest local debug slice in `../dataset` intentionally does two things that the prior rounds
did not do:

- it writes two durable continuity markers on every successful session persist:
  - `/app/artifacts/_codex_sessions/resume-root-marker.json`
  - `/app/artifacts/resume-root-parent-marker.json`
- it writes a dedicated per-run `codex_restore_probe.json` artifact alongside
  `codex_session_state.json`, so later artifact inspection can separate:
  - startup never saw `_codex_sessions`
  - startup saw `_codex_sessions` but rejected the snapshot
  - startup restored a snapshot and selected a specific resume source

This turns the remaining live question into a binary one on the next worker image:

- if the next failed run shows the parent marker but not the root marker, `_codex_sessions`
  disappeared specifically between runs
- if the next failed run shows both markers and still reports `fresh-no-snapshot`, the worker is
  still skipping a visible snapshot
- if the next run reports `root_marker_exists=true`, `parent_marker_exists=true`, and
  `selected_source=...`, then the continuity problem has moved from storage visibility to resume
  acceptance/selection

One additional implementation defect also surfaced locally while adding that instrumentation:

- `_ensure_codex_guard_verified()` used the same `_codex_home()` lifecycle as the real run while
  `_active_codex_session_spec` was still populated
- that meant guard preflight could perform its own restore/persist cycle around `codex --version`
  before the real worker exec started
- the duplicate startup/completed restore logs visible in local tests came from that nested
  preflight path

The latest local fix now explicitly suspends `_active_codex_session_spec` during guard preflight,
so `codex --version` checks cannot seed, reset, or overwrite a PVC-backed lane on their own. This
does not yet prove the live resume path, but it removes one source of false churn and one way a
failed or aborted run could have damaged the lane before the real `codex exec` started.

### Verification executed in this turn

- `python -m compileall /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_codex_cli_exec.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_worker_codex_cli_exec_small.py`
  - `pass`
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/unit/test_worker_codex_cli_exec_small.py -q`
  - `pass` (`41 passed`)
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/test_aks_module_generator_generate_modules.py tests/test_aks_module_generator_manifests.py -q`
  - `pass` (`69 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`42 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`
- `make verify-surfaces`
  - `pass`

Verification categories not executed in this turn:

- coverage
- lint / formatting
- type checking
- UI or notebook execution
- deployment or AKS integration checks

## 2026-05-04 second post-seed worker artifact review

The next uploaded run was expected to be the first real `resume` check after the earlier seed run,
but it still started as `fresh`:

- `codex_session_mode = fresh`
- `restore_status = fresh-no-snapshot`
- `resume_candidate_present = false`
- `resume_attempted = false`
- `resume_used = false`
- `persist_status = persisted`
- `pvc_sync_health = healthy`
- `persisted_files = 4`

### Live PVC and job inspection

Live cluster inspection in namespace `prompt-exec-1353735964635435100` confirms:

- worker job still mounts the stable PVC
  - claim: `artifacts-g1353735964635435100`
  - mount path: `/app/artifacts`
  - env: `DATASET_CODEX_SESSION_STATE_DIR=/app/artifacts/_codex_sessions`
- after the run, the shared PVC again contains:
  - `/artifacts/_codex_sessions/session-index.json`
  - `/artifacts/_codex_sessions/realagiorganization_shards_of_lokar_game-a3fbd616bb4892c8/session_state.json`
  - `/artifacts/_codex_sessions/.../home_snapshot/{installation_id,logs_2.sqlite,state_5.sqlite,snapshot_manifest.json}`

But the persisted `session-index.json` still shows this run as a brand-new lane snapshot:

- `total_run_count = 1`
- `fresh_run_count = 1`
- `resumed_run_count = 0`
- `restored_files = 0`
- `resume_candidate_present = false`
- `restore_status = fresh-no-snapshot`

That means `_codex_sessions` did **not** survive into worker startup as a usable preexisting
directory for this run. The worker did not merely reject a candidate; it began with no visible lane
snapshot and then seeded a fresh one again.

### Additional hidden blocker found during code inspection

Even after the storage/root-visibility issue is fixed, the current restore guard is still too
strict for the live proxy configuration:

- `_build_codex_session_spec()` stores `config_payload_digest` from the full
  `codex_config_payload`
- `_model_profile_metadata()` stores `base_url_origin`
- in this worker path that origin is the local repo-rag proxy on `127.0.0.1:<ephemeral-port>`

So a normal new run can change both:

- `config_payload_digest`
- `model_profile.base_url_origin`

without any meaningful change in the real Codex auth/model contract. Once restore begins seeing the
previous snapshot again, these fields are likely to trigger:

- `config-payload-mismatch`
- or `model-profile-mismatch`

unless the comparison is relaxed to ignore the ephemeral localhost proxy port.

### Current state after this second post-seed run

- live `RAG` isolation: `pass`
- live `DSPy` mediation: `pass`
- live trainer handoff: `pass`
- live worker mount/env wiring for `_codex_sessions`: `present`
- live session-root continuity between runs: `fail`
- live restore-guard stability against ephemeral proxy ports: `fail`
- live `resume` proof: `fail`

### Token cost in this second post-seed run

The run still consumed high input tokens without cached resume reuse:

- `prompt_tokens = 561834`
- `completion_tokens = 0`
- `total_tokens = 561834`
- `cached_input_tokens = null`

The transcript stayed documentation-first:

- `README.md`: `55`
- `docs/DEVPLAN.md`: `50`
- `docs/ENVS.md`: `48`
- `docs/AGENTS.md`: `48`
- `docs/USAGE.md`: `43`
- `docs/ASSUMPTIONS.md`: `49`
- `diff --git`: `82`
- `sed -n`: `45`

So the dominant cost is still fresh-session Codex exploration, not the initial `RAG` / `DSPy`
developer-block payload.

## 2026-05-04 local restore hardening after the second post-seed run

The next local worker slice hardens two restore edges found in that live review:

- Azure/session compatibility now normalizes repo-rag localhost proxy origins before storing
  `model_profile.base_url_origin` or deriving the session config digest. In practice, a proxy move
  from `http://127.0.0.1:44973/openai` to `http://127.0.0.1:40111/openai` now maps to the stable
  sentinel `repo-rag-proxy://local` instead of forcing:
  - `config-payload-mismatch`
  - `model-profile-mismatch`
- Worker restore search now goes beyond the direct current `lane_dir`, base lane, PVC-root
  `session-index.json`, and root `*/session_state.json` scan:
  - `restore_probe` now records whether the parent artifacts root existed
  - it also records nested `_codex_sessions` roots / metadata discovered below that parent
  - restore can now recover from nested `**/_codex_sessions/*/session_state.json` locations when
    the direct `persistent_root` is absent but a valid older lane snapshot still exists elsewhere
    under `/app/artifacts`

### Verification executed in this turn

- `python -m compileall /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_codex_cli_exec.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_worker_codex_cli_exec_small.py`
  - `pass`
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/unit/test_worker_codex_cli_exec_small.py -q`
  - `pass` (`39 passed`)
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/test_aks_module_generator_generate_modules.py tests/test_aks_module_generator_manifests.py -q`
  - `pass` (`69 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`42 passed`)
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`

### Remaining live question after this local hardening

The next worker run is now expected to answer one narrower question:

- does startup still see an actually empty `/app/artifacts/_codex_sessions`, or was the remaining
  blocker only the unstable localhost-proxy compatibility guard?

## 2026-05-04 latest live artifact review after the restore-guard hardening push

The newest uploaded worker artifacts still show a `fresh` Codex session, but the run is otherwise
healthier than the earlier multi-hundred-thousand to multi-million token outliers.

### What worked in the newest run

- live `RAG` isolation: `pass`
  - retrieval sources stayed limited to:
    - `docs/AGENTS.md`
    - `docs/ASSUMPTIONS.md`
    - `README.md`
    - `docs/USAGE.md`
  - `repo_rag_codex_proxy_last.json` reported:
    - `mediation_mode = dspy_rag`
    - `rag_status = success`
    - `dspy_status = success`
    - `bundle_version = 20260502T122127191445Z`
    - `summary_len = 2821`
    - `question_len = 2766`
- live `DSPy` mediation: `pass`
  - `repo_rag_backend.json` again reported:
    - `bundle_resolved = true`
    - `program_loaded = true`
    - `dspy_status = success`
- live trainer handoff: `pass`
  - `trusted_trace_handoff_summary.json` reported:
    - `attempted = 1`
    - `queued = 1`
    - `failed = 0`
    - blob:
      `queued/repo-rag-training/20260504T152730Z-prompts_shards_of_lokar_game-p00000-355cca.json`

### What still failed

- live `codex exec resume`: `fail`
  - `codex_session_mode = fresh`
  - `restore_status = fresh-no-snapshot`
  - `resume_candidate_present = false`
  - `resume_attempted = false`
  - `resume_used = false`
  - `restored_files = 0`
  - `persisted_files = 4`
- the latest `restore_probe` still shows no visible durable session root at worker startup:
  - `persistent_root_exists = false`
  - `lane_dir_exists = false`
  - `metadata_path_exists = false`
  - `index_path_exists = false`
  - `nested_session_root_count = 0`
  - `nested_session_metadata_count = 0`
  - `persistent_root_parent_entries = [\"runs\", \"worker_execution.log\"]`

This means the guard-hardening fix did not yet produce a live resumed run. The worker still starts
with no visible `_codex_sessions` subtree and seeds a new fresh snapshot by the end of the run.

### Token cost in the newest run

The newest run consumed much less input than the previous documented outliers, but the reduction
did **not** come from session resume reuse:

- `prompt_tokens = 144135`
- `completion_tokens = 0`
- `total_tokens = 144135`
- `codex_response.txt` size = `1611976` bytes

Transcript-level path telemetry and direct transcript counts both show a much shorter,
documentation-aware session than earlier runs:

- `codex_session_state.json`
  - `path_mention_count = 13`
  - `documentation_mention_count = 12`
  - `read_like_command_count = 0`
  - `diff_command_count = 1`
- `codex_response.txt` direct counts
  - `README.md`: `70`
  - `docs/DEVPLAN.md`: `59`
  - `docs/ENVS.md`: `59`
  - `docs/USAGE.md`: `65`
  - `docs/AGENTS.md`: `60`
  - `docs/ASSUMPTIONS.md`: `68`
  - `diff --git`: `165`
  - `sed -n`: `33`
  - `prompt_artifacts`: absent

The run therefore improved token usage primarily because the worker session itself was shorter and
less repetitive, not because `resume` finally engaged.

### Verification executed in this turn

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`42 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`

### Additional local/live diagnosis after the newest artifact review

Local inspection of the workstation Codex CLI home and live inspection of the shared artifacts PVC
now narrow the remaining `resume` problem further:

- local `~/.codex` layout contains the same top-level surfaces we attempt to persist:
  - `history.jsonl`
  - `sessions/`
  - `state_5.sqlite`
  - `logs_2.sqlite`
  - `installation_id`
  - `models_cache.json`
  - `memories/`
  - `shell_snapshots/`
- the current live PVC helper pod (`artifacts-sync-run` mounting
  `artifacts-g1353735964635435100`) now shows that `_codex_sessions` is really being written into
  the root of the claim:
  - `/artifacts/_codex_sessions/session-index.json`
  - `/artifacts/_codex_sessions/realagiorganization_shards_of_lokar_game-a3fbd616bb4892c8/session_state.json`
  - `/artifacts/_codex_sessions/.../home_snapshot/{installation_id,logs_2.sqlite,state_5.sqlite}`
  - `/artifacts/_codex_sessions/.../home_snapshot/sessions/2026/05/04/rollout-2026-05-04T15-10-27-019df38a-6681-7761-bc5b-4f2525fe200a.jsonl`
- `snapshot_manifest.json` for that lane reports exactly four persisted files:
  - `installation_id`
  - `logs_2.sqlite`
  - `sessions/2026/05/04/rollout-2026-05-04T15-10-27-019df38a-6681-7761-bc5b-4f2525fe200a.jsonl`
  - `state_5.sqlite`

So the remaining live blocker is **not** “Codex session files are being written under the wrong
relative directory inside `CODEX_HOME`”. The persisted layout already matches the normal
Codex-on-disk shape closely enough to include the session JSONL plus the two SQLite databases.

The live blocker is now narrower:

- the worker still begins startup with `restore_probe` reporting no visible `_codex_sessions`
  subtree at `/app/artifacts`
- yet after the run, the same PVC root clearly contains `_codex_sessions`

That means the failure is currently between:

1. visibility of the previously persisted root snapshot to the new worker at startup, and/or
2. the worker's decision logic for selecting and restoring that snapshot once visible

One additional implementation weakness also remains:

- the worker currently resumes via `codex exec resume --last`
- local Codex CLI help confirms that `--last` picks the most recent recorded session and exposes
  `--all` specifically to disable cwd filtering
- once startup restore is stable, the worker should prefer the persisted explicit
  `latest_session_id` over `--last` so resume selection does not depend on Codex's own
  most-recent/cwd heuristics

### Latest local follow-up on resume command selection and helper-pod cleanup

The newest local hardening pass in `../dataset` closed two concrete implementation gaps that were
still visible after the live artifact review:

- `worker_codex_cli_exec.py`
  - restore now reloads `latest_session_file` / `latest_session_id` from persisted lane metadata
    before command assembly
  - if metadata does not carry those fields but the restored snapshot contains `sessions/*.jsonl`,
    the worker now redetects the latest session file from the restored temp `CODEX_HOME`
  - the worker now prefers `codex exec resume <latest_session_id>` when a usable session id exists
  - only older snapshots that still lack a usable session id fall back to
    `codex exec resume --last --all`
  - per-run `codex_session_state.json` now records:
    - `resume_target_session_id`
    - `resume_command_mode`
- `tools/pvc_artifact_sync.sh`
  - helper pods now self-clean on script exit through an `EXIT` trap
  - explicit `cleanup` also deletes helper pods by
    `app=artifacts-sync,claim=<claim>` label instead of only by one derived pod name
  - the helper suffix now falls back to the PVC claim when no real run slug is present, avoiding
    generic long-lived names like `artifacts-sync-run` during deploy-time artifact sync

The live `artifacts-sync-run` pod attached to `artifacts-g1353735964635435100` now has a clear
postmortem:

- it carried labels:
  - `app=artifacts-sync`
  - `claim=artifacts-g1353735964635435100`
  - `guild=unknown`
- its age substantially exceeded the latest worker job age
- that combination matches a helper created by a claim-based sync path without `--guild-id`,
  which meant the workflow cleanup step deriving the helper pod name from `--guild-id` /
  `--run-slug` could miss it even after the pipeline completed
- a direct cleanup check using
  `bash tools/pvc_artifact_sync.sh cleanup --claim artifacts-g1353735964635435100 --namespace prompt-exec-1353735964635435100`
  removed the lingering helper, and a follow-up
  `kubectl -n prompt-exec-1353735964635435100 get pods -l app=artifacts-sync`
  returned no remaining helper pods

### Verification executed in this turn

- `python -m compileall /home/standard/Desktop/realagi_work/dataset/docker/prompt-executor/worker_codex_cli_exec.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_worker_codex_cli_exec_small.py /home/standard/Desktop/realagi_work/dataset/tests/unit/test_pvc_artifact_sync_small.py`
  - `pass`
- `cd /home/standard/Desktop/realagi_work/dataset && uv run pytest tests/unit/test_worker_codex_cli_exec_small.py tests/unit/test_pvc_artifact_sync_small.py -q`
  - `pass` (`48 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`42 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`
