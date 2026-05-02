# Hybrid Vector Retrieval Default

- Date: `2026-05-02`
- Scope: replace the repository-only lexical RAG baseline with a real Azure OpenAI embedding-backed
  semantic retrieval path while preserving safe lexical fallback
- Preceding note: `2026-05-02-live-trainer-still-not-publishing-bundles.md`

## Summary

The repository now has a real vector retrieval implementation instead of only lexical retrieval.

The new retrieval contract is:

1. lookup-first narrowing through Rust/SQLite FTS still runs first
2. lexical retrieval still exists as `lexical`
3. lexical reranking still exists as `idf-rerank`
4. new semantic retrieval now exists as `vector`
5. new hybrid retrieval now exists as `hybrid-vector`
6. the repo-local default profile now requests `hybrid-vector`
7. when semantic runtime is unavailable, retrieval falls back to `idf-rerank` and records an
   explicit warning instead of silently pretending vector retrieval ran

## Code Changes

Primary implementation surfaces:

- `src/repo_rag_lab/semantic_retrieval.py`
- `src/repo_rag_lab/retrieval.py`
- `src/repo_rag_lab/azure_runtime.py`
- `src/repo_rag_lab/workflow.py`
- `src/repo_rag_lab/dspy_training.py`
- `src/repo_rag_lab/benchmarks.py`
- `src/repo_rag_lab/cli.py`
- `src/repo_rag_lab/mcp_server.py`
- `config/retrieval-profile.json`

Important behavior changes:

- semantic retrieval now uses Azure OpenAI embeddings through:
  - `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME`
  - optional `AZURE_OPENAI_EMBEDDING_API_VERSION`
  - existing `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY`
- the repo now persists a local semantic chunk index at:
  - `artifacts/retrieval/semantic-index.json`
- ask-family results now include:
  - `retrieval_warnings`
- Codex mediation now inherits those retrieval warnings, so worker-side artifacts can show when
  semantic retrieval fell back to lexical ranking
- benchmark and notebook-facing retrieval quality summaries now report the **effective** retrieval
  mode after semantic fallback instead of only echoing the requested profile mode
- corpus loading and benchmark-corpus selection now both exclude runtime-generated worker
  scaffolding such as `prompt_artifacts/`, `_context_repos/`, and `.repo_rag_cache/`, so
  retrieval cannot win by rereading its own prompt echoes or temporary repo-link/cache state

## Verification

Repository-local checks executed in this turn:

- `uv run python -m compileall src tests` -> `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` -> `pass` (`40 passed`)
- `uv run pytest tests/test_retrieval.py tests/test_workflow.py tests/test_workflow_live.py tests/test_mcp_server.py tests/test_lookup_first.py tests/test_dspy_training.py tests/test_cli_and_dspy.py tests/test_benchmarks_and_notebook_scaffolding.py tests/test_project_surfaces.py tests/test_training_samples.py -q` -> `pass` (`137 passed`)
- `uv run repo-rag smoke-test` -> `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`
- `make files-sync` -> `pass`
- `make verify-surfaces` -> `pass`

Follow-up hardening checks executed in the current turn:

- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_retrieval.py tests/test_benchmarks_and_notebook_scaffolding.py -q` -> `pass` (`66 passed`)
- `make verify-surfaces` -> `pass`

## Limits

This note does **not** claim live Azure embedding retrieval was exercised end to end.

Specifically not verified in this turn:

- live `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME` round trips
- first-build latency or spend for `artifacts/retrieval/semantic-index.json`
- live worker-side AKS mediation using the new semantic retrieval mode

What is verified here is:

- code compiles
- retrieval/workflow/MCP fallback behavior is covered by local tests
- the repository default now requests `hybrid-vector`
- runtime-generated worker prompt traces and context-link scaffolding are now outside the live
  retrieval/benchmark corpus contract

## Latest Live Deployment Check

- Checked artifact upload `executions/25250270123_20260502_111853` from local
  `../dataset/artifacts/`.
- Re-ran the repository-native baseline locally in this turn:
  - `uv run python -m compileall src tests` -> `pass`
  - `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` -> `pass`
    (`40 passed`)
  - `uv run repo-rag smoke-test` -> `pass`
  - `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`

Live conclusions from the uploaded worker artifacts and the running `repo-rag` trainer:

1. The latest worker run did **not** exercise the updated prompt-artifact isolation or the new
   retrieval exclusion policy.
   - `repo_rag_codex_proxy_last.json` still retrieved:
     - `prompt_artifacts/prompts_shards_of_lokar_game-p00000-355cca.txt`
     - `prompt_artifacts/prompts_shards_of_lokar_game-p00000-9dc50a.txt`
     - `prompt_artifacts/prompts_shards_of_lokar_game.txt`
     - `README.md`
   - `execution.log` from the same run still shows:
     - `Persisted prompt trace at /tmp/repositories/realagiorganization_shards_of_lokar_game/prompt_artifacts/...`
   - That means the AKS worker image used for this run still contained the old worker-side prompt
     trace placement, so the repo-local exclusion and prompt-artifact relocation fixes present in
     the current worktree had not been deployed yet.

2. DSPy still did **not** run in compiled-bundle mode in that worker run.
   - `repo_rag_backend.json` shows:
     - `bundle_resolved = false`
     - `bundle_version = null`
     - `dspy_status = "heuristic"`
   - `repo_rag_trace.json` shows:
     - `program_loaded = false`
     - `program_path = null`
   - Azure blob inspection confirmed:
     - `channels/stable.json` -> `BlobNotFound`
     - `channels/canary.json` -> `BlobNotFound`
   - The current live trainer env still has `TRAINER_PROMOTE_CHANNEL=""`, so workers do not have
     an active global channel pointer to resolve by default.

3. The trainer is now publishing versioned bundles, but it is publishing **too many** of them.
   - Live `service-state.json` at `2026-05-02T11:31:37Z` shows:
     - `cycles_executed = 18`
     - `successful_cycle_count = 2`
     - `failed_cycle_count = 16`
     - `total_recompiled_run_count = 18`
     - `total_publish_count = 18`
     - `total_drained_count = 1`
   - The latest bundle versions present in Azure include timestamps such as:
     - `20260502T112224258019Z`
     - `20260502T112740532590Z`
     - `20260502T113020328758Z`
   - The live cycle records show why this is happening:
     - `durable_trace_recovery` restores the same processed trace ledger every cycle
     - `training_candidates.new_candidate_count` still reports work every cycle
     - `recompile.recompile_status = "compiled"` and publish happens again on the same effective
       training set
   - This **does not** match the intended training behavior. The expected contract is to publish a
     new immutable bundle only when the effective candidate set changes, not once per poll cycle on
     a stable recovered ledger.

4. There is still a stale trainer-queue failure unrelated to the main worker result.
   - Live cycle records continue to show one `BlobNotFound` against an old
     `failed/repo-rag-training/...trainer-validation-seed...json` blob.
   - That failure is noisy, but it is not the primary reason the worker missed DSPy. The primary
     blockers are:
     - no promoted `stable`/`canary` channel pointer
     - trainer-side republish churn on unchanged recovered traces

Current live state therefore differs from the repository-local target in two ways:

- worker-side retrieval isolation changes are locally implemented and tested, but were not present
  in the last uploaded AKS worker artifacts
- trainer-side versioned bundle publishing is live, but the change-detection gate for recompilation
  and publish is still too permissive, causing churn

## Repository-Local Hardening After The Live Check

The current worktree now closes the gaps identified above, even though those fixes were not yet in
the last uploaded AKS artifacts:

1. Worker-side prompt traces are expected to stay under execution artifacts instead of being
   written into the analyzed repository tree, and repo-rag corpus loading/benchmark selection now
   excludes runtime-generated scaffolding such as `prompt_artifacts/`, `_context_repos/`, and
   `.repo_rag_cache/`.
2. Trainer-side candidate materialization now seeds from the existing materialized candidate YAML
   when replaying the durable processed-trace ledger, so one unchanged recovered ledger no longer
   reports fresh `new_candidate_count` work every poll cycle.
3. Azure queue drain now treats already-missing `failed/...` blob pointers as stale queue noise,
   deletes the queue message, and records a `stale-failed-blob` skip instead of poisoning the
   trainer cycle with another synthetic failure.
4. Repository-local trainer deployment defaults now assume `TRAINER_PROMOTE_CHANNEL=stable`,
   making the intended global worker path “publish immutable version -> promote `stable` ->
   workers resolve `stable` unless a version pin overrides it”.
5. Worker-side bundle resolution now treats placeholder pins such as `DSPY_BUNDLE_VERSION=0` as
   unset, so a forgotten placeholder no longer blocks fallback resolution through the promoted
   bundle channel.

Repository-local checks executed after those follow-up fixes:

- `uv run python -m compileall src tests` -> `pass`
- `uv run pytest tests/test_training_samples.py tests/test_runtime_artifacts_azure.py tests/test_utilities.py tests/test_retrieval.py tests/test_benchmarks_and_notebook_scaffolding.py -q` -> `pass` (`80 passed`)
- `uv run repo-rag smoke-test` -> `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`
- `make verify-surfaces` -> `pass`
- `make files-sync` -> `pass`

## Latest Live Worker And Trainer Check

- Checked local worker artifact export `../dataset/artifacts/` for Azure upload
  `executions/25252299455_20260502_131144`.
- Re-ran the repository-native verification baseline in this turn:
  - `uv run python -m compileall src tests` -> `pass`
  - `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` -> `pass`
    (`40 passed`)
  - `uv run repo-rag smoke-test` -> `pass`
  - `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`

### Worker-Side Results

The latest worker run now confirms that the updated worker image and retrieval-isolation changes are
live:

1. Prompt traces are no longer written into the analyzed repository tree.
   - `execution.log` now shows:
     - `Persisted prompt trace at /tmp/artifacts/prompts_shards_of_lokar_game-p00000-355cca/prompt_artifacts/...`
   - The earlier `/tmp/repositories/.../prompt_artifacts/...` placement is gone from the latest
     run.

2. Retrieval no longer pulls `prompt_artifacts/...` back into the mediation context.
   - `repo_rag_codex_proxy_last.json` now reports:
     - `sources = ["README.md", "docs/USAGE.md", "docs/AGENTS.md", "docs/ASSUMPTIONS.md"]`
   - That means the corpus exclusion for runtime-generated worker scaffolding is active in the live
     worker path.

3. The worker still runs repo-rag successfully, but DSPy still falls back to heuristic synthesis.
   - `repo_rag_backend.json` shows:
     - `backend = "codex_cli_repo_rag_proxy"`
     - `rag_status = "success"`
     - `dspy_status = "heuristic"`
     - `bundle_resolved = false`
     - `bundle_version = null`
   - `repo_rag_codex_proxy_last.json` still warns:
     - `DSPy mediation was unavailable; using heuristic synthesis instead. (No compiled DSPy bundle is available.)`

4. Trusted trace handoff still works correctly.
   - `trusted_trace_handoff_summary.json` shows:
     - `attempted = 1`
     - `queued = 1`
     - `failed = 0`
   - Azure queue/blob inspection shows the same item later under:
     - `processed/repo-rag-training/20260502T131143Z-prompts_shards_of_lokar_game-p00000-355cca.json`

### Trainer-Side Results

The live trainer now has an active global bundle channel:

- `artifacts/dspy/channels/stable.json` exists in the running trainer pod
- `stable.json` currently points at:
  - `current_bundle_version = "20260502T122127191445Z"`
- Azure blob inspection confirms:
  - `repo-rag-bundles/channels/stable.json` exists
  - immutable bundle files exist under:
    - `versions/20260502T120805498593Z/...`
    - `versions/20260502T122127191445Z/...`

A manual trainer cycle run on the current image also succeeded and produced a valid `stable`
channel pointer earlier in this turn.

### Remaining Live Gap

The remaining live problem is now narrower and clearer:

- the trainer can publish and promote `stable`
- the worker can run repo-rag and improved retrieval
- but the worker still does **not** resolve the promoted bundle before calling `repo-rag ask`

The reason is visible in the live worker job spec and the current worker code contract:

1. The worker pod only receives this repo-rag storage config secret:
   - `DATASET_REPO_RAG_BUNDLE_CONTAINER=repo-rag-bundles`
   - `DATASET_REPO_RAG_TRACE_CONTAINER=repo-rag-training-traces`
   - `DATASET_REPO_RAG_TRACE_QUEUE_NAME=repo-rag-training`

2. The worker does **not** receive:
   - `AZURE_STORAGE_ACCOUNT`
   - `AZURE_STORAGE_KEY`
   - `AZURE_STORAGE_CONNECTION_STRING`
   - any repo-rag trainer root / shared bundle root mount

3. Worker-side bundle lookup only runs when one of these is true:
   - `trainer_root is not None`
   - `_repo_rag_bundle_store_configured()` is true

4. In the live worker pod, neither condition is met, so the worker never runs `bundle-inspect`
   against the promoted `stable` channel and therefore falls back to heuristic DSPy every time.

This means the current live architecture now has:

- working live retrieval isolation
- working live trusted trace handoff
- working live trainer publish/promote to `stable`
- **missing live worker-side access path to the promoted bundle**

The next fix therefore should not target retrieval quality again. It should provide one safe
worker-readable bundle-distribution path, for example:

- sync the promoted bundle into a non-secret shared mount available to workers, or
- provide a tightly scoped read-only bundle-store credential path that lets workers resolve
  `stable` without exposing broad write-capable Azure storage credentials.

## Repository-Local Safe Stable-Bundle Follow-Up

The current worktree now implements the first of those worker-side fixes without giving blob
credentials to `codex` or the worker pod itself.

Repository-local behavior is now:

1. the runner-side deployment script stages a local mirror of:
   - `channels/stable.json`
   - `versions/<stable_bundle_version>/{bundle.json,metadata.json,program.json,published.json}`
   - optionally an explicitly pinned bundle version when a non-placeholder
     `DSPY_BUNDLE_VERSION` / `DATASET_REPO_RAG_BUNDLE_VERSION` is set
2. that mirror is synced into the existing artifacts PVC under:
   - `.repo_rag_bundle_store/`
3. worker pods receive a non-secret env default:
   - `DATASET_REPO_RAG_BUNDLE_ROOT=/tmp/artifacts/.repo_rag_bundle_store`
4. worker-side repo-rag execution now:
   - treats placeholder pins such as `0`, `null`, `none`, or `unset` as not configured
   - tries an explicit bundle version first when one is valid
   - falls back to `bundle-inspect --channel stable` against the local mirrored bundle root when
     the explicit version is invalid or absent
5. Codex proxy bundle resolution now also understands that local staged bundle root directly,
   instead of only fetching remote bundles or falling back to repository-local `artifacts/dspy`

This means the repository-local contract is now:

- no worker-side blob credentials
- no requirement for a shared trainer root mount
- stable-channel fallback still works, but from a safe runner-staged local mirror

Repository-local checks executed for that follow-up:

- `uv run python -m compileall src tests` -> `pass`
- `uv run pytest tests/test_codex_proxy.py tests/test_utilities.py tests/test_repository_rag_bdd.py -q` -> `pass` (`46 passed`)
- `uv run repo-rag smoke-test` -> `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`

What is still **not** claimed here:

- a fresh live AKS worker run that consumes `stable.json` through the new artifacts-PVC mirror
- end-to-end proof that a worker with empty/invalid `DSPY_BUNDLE_VERSION` now resolves the
  promoted stable bundle in production

## Latest Build And Trainer Redeploy Check

The dataset-side image build and trainer redeploy for the safe worker bundle-mirror path have now
been completed live.

Commands executed in this turn:

- `BUILD_MODE=acr IMAGE_TAG=20260502-135903 ./build_and_push_images.sh` from
  `../dataset` -> `pass`
- `IMAGE_TAG=20260502-135903 ./deploy_repo_rag_trainer.sh` from `../dataset` -> `pass`

Built images:

- `llmpromptsacr.azurecr.io/repo-rag-runtime:20260502-135903`
- `llmpromptsacr.azurecr.io/prompt-executor:20260502-135903`
- `llmpromptsacr.azurecr.io/queue-initializer:20260502-135903`

Live trainer deployment evidence after redeploy:

- `kubectl -n repo-rag get deploy repo-rag-trainer-service -o yaml` shows:
  - `image: llmpromptsacr.azurecr.io/repo-rag-runtime:20260502-135903`
  - `--promote-channel stable`
- `kubectl -n repo-rag get deploy,po,cm,secret` shows:
  - `deployment.apps/repo-rag-trainer-service` -> `READY 1/1`
  - running pod `repo-rag-trainer-service-5b856bf894-f7jl4`
- Azure bundle-channel inspection of `repo-rag-bundles/channels/stable.json` still resolves to:
  - `current_bundle_version = "20260502T122127191445Z"`
  - `current_program_path = "artifacts/dspy/20260502T122127191445Z/program.json"`

What this redeploy check confirms:

- the current repo-rag runtime image now exists in ACR for the safe stable-bundle fallback work
- the live trainer is running that new runtime image
- the live trainer still promotes to `stable`
- the global `stable` channel pointer remains intact after redeploy

What this redeploy check still does **not** confirm:

- a new worker/pipeline run using `prompt-executor:20260502-135903`
- end-to-end worker resolution of the promoted bundle through the new artifacts-PVC bundle mirror
- live compiled-DSPy execution after removing or invalidating `DSPY_BUNDLE_VERSION`
