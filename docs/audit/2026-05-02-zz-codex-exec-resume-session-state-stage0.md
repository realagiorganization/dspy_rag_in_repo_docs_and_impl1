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
- Wired the worker manifest default `DATASET_CODEX_SESSION_STATE_DIR=/tmp/artifacts/_codex_sessions`
  so AKS runs pin Codex session snapshots to the artifacts PVC explicitly rather than relying on an
  implicit `exec_dir.parent` layout.
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
    `DATASET_CODEX_SESSION_STATE_DIR=/tmp/artifacts/_codex_sessions`,
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
