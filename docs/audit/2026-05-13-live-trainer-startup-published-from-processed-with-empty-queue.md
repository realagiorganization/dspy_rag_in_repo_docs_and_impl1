# 2026-05-13 Live Trainer Startup Published From Processed With Empty Queue

## Scope

Check whether the freshly redeployed live trainer had re-entered the prior endless training loop
immediately after startup.

## Live Status

At inspection time:

- `repo-rag-trainer-service` was `1/1`
- `repo-rag-trainer-cycle` remained `suspend=true`
- `queued/...` was empty from the live service point of view
- `service-state.json` reported:
  - `cycles_executed = 0`
  - `successful_cycle_count = 0`
  - `total_publish_count = 0`
  - `pending_input_inspection.current_cycle_input_detected = false`
  - `pending_input_inspection.queue_visible_count = 0`

So the service was **not** currently spinning in a repeated publish loop.

## Confirmed Bug

Even with an empty queue, the redeployed service still performed one expensive startup
materialization/recompile sequence:

- pod creation timestamp: `2026-05-13T19:03:18Z`
- `family-state.json` rewritten at `2026-05-13 19:06:32Z`
- `training-candidates-summary.json` rewritten at `2026-05-13 19:07:31Z`
- `generated-training.yaml` rewritten at `2026-05-13 19:08:27Z`
- service logs at `2026-05-13T19:09:21Z` show live `BootstrapFewShot` progress

The remote `repo-rag-training-families` container also showed a newly published:

- `current_version = 20260513T190632Z`

with no second or third follow-up version after that startup publish.

## Interpretation

This means the current live bug is **not** "infinite cycle while idle". The current live bug is:

- **one unintended startup publish from `processed` when no remote family version exists and
  `queued/` is empty**

That violates the intended contract:

1. trainer should start a training cycle only when new blobs are visible under `queued/...`
2. `from scratch from processed` is allowed only inside such an explicitly queue-triggered cycle
3. an idle service should not synthesize a new remote family-state version on startup by itself

## Supporting Live Evidence

Commands used:

- `kubectl -n repo-rag get deploy repo-rag-trainer-service -o yaml`
- `kubectl -n repo-rag get cronjob repo-rag-trainer-cycle -o yaml`
- `kubectl -n repo-rag logs deploy/repo-rag-trainer-service --timestamps --tail=300`
- `kubectl -n repo-rag exec <pod> -- sh -lc '...service-state.json...'`
- `uv run python - <<'PY' ... BlobServiceClient ... repo-rag-training-families ... PY`

Relevant live values:

- trainer image: `llmpromptsacr.azurecr.io/repo-rag-runtime:20260513-184943`
- optimizer still configured as `bootstrapfewshot`
- live trainer env now correctly resolves to:
  - `AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o`
  - `AZURE_OPENAI_MODEL_NAME=gpt-4o`
  - `DSPY_TRAINER_API_BASE=https://gpt45standard.openai.azure.com/`

So the model-alignment fix is present, but the startup cache lifecycle is still wrong.

## Local Fix

The repository now hard-gates `run_trainer_cycle()` on **actual queued trace input** before any
cache preparation or processed-ledger replay runs:

- queue drain/import is computed first
- if `drained_count == 0` and no imported trace paths were produced, the cycle returns an
  explicit no-op payload
- `_prepare_local_trainer_family_cache(...)`, trainer materialization, recompile, and publish
  are all skipped in that branch

This preserves the intended contract:

1. `queued/...` visibility is the only trigger for an active trainer cycle
2. `from scratch from processed` is allowed only inside a queue-triggered cycle
3. a startup redeploy with an empty queue does not publish a remote family-state version

## Verification

After the code fix, the repository verified successfully with:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py -q`
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`

The targeted utility suite now passes with the new strict queue-only semantics, including the
regression that asserts the trainer does nothing when `queued/...` is empty.
