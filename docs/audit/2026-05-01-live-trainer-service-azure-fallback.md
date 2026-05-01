# Live Trainer Service Azure Fallback

- Date: `2026-05-01`
- Scope: live AKS trainer-side consumption and bundle publication after trusted downstream trace handoff
- Preceding note: `2026-05-01-dataset-trusted-trace-handoff-postprocess-fix.md`

## Summary

Fresh worker-side evidence now shows the secure downstream handoff is working:

- the latest `../dataset` execution artifacts include `repo_rag_trace_enqueue.json`
- the handoff summary reports `attempted = 1`, `queued = 1`, `failed = 0`
- the queued blob path is
  `queued/repo-rag-training/20260501T135609Z-prompts_shards_of_lokar_game-p00000-355cca.json`
- the queue item metadata references the global trace container `repo-rag-training-traces`
  and queue `repo-rag-training`

The remaining live problem is no longer worker-side queueing. It is trainer-side consumption and
publication:

- the live `repo-rag-trainer-service` Deployment and `repo-rag-trainer-cycle` CronJob are present
  in namespace `repo-rag`
- both still run image `llmpromptsacr.azurecr.io/repo-rag-runtime:20260430-123514`
- the trainer secret contains `AZURE_STORAGE_ACCOUNT`, queue/container names, and Azure OpenAI
  settings, but **does not** contain `AZURE_STORAGE_KEY` or
  `AZURE_STORAGE_CONNECTION_STRING`
- the trainer therefore falls back to the filesystem queue backend instead of the global Azure
  Blob + Queue transport
- the latest trainer history record reports `queue_backend = "filesystem"`,
  `queue_found = false`, `drained_count = 0`, and warning
  `No queued trace items were available for this trainer cycle.`

So the latest worker run successfully stages a global queue item, but the live trainer is not
looking at that global queue.

## Live Cluster Evidence

AKS cluster:

- `az aks get-credentials -g LLM -n prompt-execution-cluster --overwrite-existing`
- `kubectl get deploy,cronjob,pods -A | rg 'repo-rag-trainer|trainer'`

Observed runtime surfaces:

- `repo-rag` namespace contains:
  - `deployment.apps/repo-rag-trainer-service`
  - `cronjob.batch/repo-rag-trainer-cycle`
  - running service pod plus successful cycle-job pods

Deployment configuration:

- `kubectl get deploy -n repo-rag repo-rag-trainer-service -o yaml`
- `kubectl get cronjob -n repo-rag repo-rag-trainer-cycle -o yaml`

Key findings from those manifests:

- queue name is `repo-rag-training`
- trainer image tag is `20260430-123514`
- the command line omits:
  - `--recompile-run-name`
  - `--run-name`
  - `--promote-channel`

That means the trainer is configured as a queue drainer + evaluator, not as an automatic
bundle-publisher.

## Secret And State Evidence

Trainer secret:

- `kubectl get secret -n repo-rag repo-rag-trainer-secrets -o jsonpath='{.data}'`

Decoded salient values:

- `AZURE_STORAGE_ACCOUNT = realagistorage`
- `DATASET_REPO_RAG_TRACE_QUEUE_NAME = repo-rag-training`
- `AZURE_OPENAI_API_VERSION = 2024-12-01-preview`

Missing values:

- `AZURE_STORAGE_KEY`
- `AZURE_STORAGE_CONNECTION_STRING`

Trainer config:

- `kubectl get configmap -n repo-rag repo-rag-trainer-config -o yaml`

Important settings:

- `TRAINER_RECOMPILE_RUN_NAME = ""`
- `TRAINER_PROMOTE_CHANNEL = ""`
- `TRAINER_MIN_BUNDLE_PASS_RATE = ""`

Trainer-local persisted state:

- latest service history file under `/workspace/repo-rag/artifacts/trainer/history/`
  reports:
  - `command_status = "success"`
  - `queue_backend = "filesystem"`
  - `queue_found = false`
  - `drained_count = 0`
  - `publish_requested = false`
  - `promotion_status = "not-requested"`

Trainer-local artifact counts:

- `/workspace/repo-rag/artifacts/traces/imported` -> `0` files
- `/workspace/repo-rag/artifacts/dspy/published` -> `0` files
- `/workspace/repo-rag/artifacts/dspy/channels` -> `0` files

## Interpretation

The current end-to-end status is:

- worker-side `codex + repo-rag` mediation: live and successful
- worker-side secure trace handoff: live and successful
- trainer-side global queue consumption: **not live yet**
- trainer-side bundle publication: **not configured yet in the deployed trainer**

This explains why `repo-rag-bundles` remains empty even after the latest worker run:

1. the live trainer cannot see Azure queue/blob items because its secret lacks storage
   credentials, so it falls back to the empty filesystem queue
2. even if it could drain traces, the deployed trainer config still has no
   `TRAINER_RECOMPILE_RUN_NAME` or `TRAINER_PROMOTE_CHANNEL`, so bundle publication is not
   requested automatically

## Verification Commands

Repository-local checks re-run in this turn:

- `uv run python -m compileall src tests` — `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — `37 passed`
- `uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`

Operational evidence collected in this turn:

- `az account show -o json`
- `az aks list -o table`
- `kubectl get ns -o name | rg 'repo-rag|prompt-exec'`
- `kubectl get deploy,cronjob,pods -A | rg 'repo-rag-trainer|trainer'`
- `kubectl get deploy -n repo-rag repo-rag-trainer-service -o yaml`
- `kubectl get cronjob -n repo-rag repo-rag-trainer-cycle -o yaml`
- `kubectl get configmap -n repo-rag repo-rag-trainer-config -o yaml`
- `kubectl get secret -n repo-rag repo-rag-trainer-secrets -o jsonpath='{.data}'`
- `kubectl exec -n repo-rag deploy/repo-rag-trainer-service -- sh -lc 'ls -lt /workspace/repo-rag/artifacts/trainer/history | head -n 10'`
- inspection of fresh `../dataset/artifacts/redis_results.json` and `all_artifacts.tar.gz`

Limitations:

- direct Azure Blob/Queue readback through `az storage ... --auth-mode login` was blocked by
  storage data-plane RBAC on the current Azure login, so blob/queue existence claims are anchored
  to pipeline-produced enqueue artifacts plus trainer-side cluster state instead of direct storage
  listing.

## Next Corrective Action

The next deployment fix should target the trainer, not the worker:

1. redeploy `repo-rag-trainer-service` / `repo-rag-trainer-cycle` with Azure storage credentials
   so `trace-drain` uses `azure-blob-queue` instead of filesystem fallback
2. update trainer Azure/OpenAI settings, including `AZURE_OPENAI_API_VERSION`, away from the stale
   `2024-12-01-preview`
3. decide whether automatic publish should stay off or whether
   `TRAINER_RECOMPILE_RUN_NAME` and `TRAINER_PROMOTE_CHANNEL` should be enabled intentionally
