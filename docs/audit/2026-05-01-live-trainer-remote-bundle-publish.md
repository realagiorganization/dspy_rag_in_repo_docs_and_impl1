# Live Trainer Remote Bundle Publish

- Date: `2026-05-01`
- Scope: live AKS trainer-side Azure queue drain plus remote bundle publication after the trusted downstream worker handoff redesign
- Preceding note: `2026-05-01-live-trainer-service-azure-fallback.md`

## Summary

The live AKS path has now moved past the earlier filesystem-fallback state:

- worker-side `codex_cli_repo_rag_proxy` mediation and trusted downstream trace enqueue remain live
- the live trainer service now runs image `llmpromptsacr.azurecr.io/repo-rag-runtime:20260501-154923`
- the trainer secret now includes Azure storage credentials, so trainer-side queue drain uses
  `azure-blob-queue` instead of the empty filesystem fallback
- the global bundle container `repo-rag-bundles` is no longer empty

The remaining live nuance is no longer “can the trainer see Azure?” but “did this specific imported
trace create new DSPy training candidates?” The latest service-cycle history shows:

- `queue_backend = "azure-blob-queue"`
- the service is inspecting the global `repo-rag-training` queue
- the latest cycle still reports `new_candidate_count = 0`, so trainer-side recompilation is
  skipped for that cycle
- the current Deployment still has no promotion channel configured, so automatic channel promotion
  remains intentionally disabled

So the live system now drains the global queue and can publish remote bundles, but the newest
imported trace did not create a fresh candidate set large enough to force an automatic recompile.

## Root Cause And Fix

The trainer-side gap turned out not to be queue visibility anymore. After the queue/secret fix, the
next live blocker was inside `repo-rag trainer-cycle` itself:

- `publish_bundle(...)` and `promote_bundle(...)` updated local trainer state
- but `trainer-cycle` did not mirror those published artifacts back into the Azure
  `repo-rag-bundles` container
- manual `repo-rag bundle-publish` already uploaded remote bundle blobs, which proved the storage
  credentials and upload helper path were fine
- the missing behavior was specific to the trainer-cycle wrapper

The current code now uploads the remote bundle directly from `run_trainer_cycle(...)` after
successful local publish, and uploads both bundle/version artifacts and channel state after
successful promotion.

## Live Evidence

Azure bundle container readback:

- `az storage blob list --account-name realagistorage --account-key "$AZURE_STORAGE_KEY" --container-name repo-rag-bundles -o table`
- observed remote bundle blobs:
  - `versions/trainer-auto/bundle.json`
  - `versions/trainer-auto/metadata.json`
  - `versions/trainer-auto/program.json`
  - `versions/trainer-auto/published.json`
  - `versions/trainer-auto-remoteupload/bundle.json`
  - `versions/trainer-auto-remoteupload/metadata.json`
  - `versions/trainer-auto-remoteupload/program.json`
  - `versions/trainer-auto-remoteupload/published.json`

Live trainer Deployment:

- `kubectl get deploy -n repo-rag repo-rag-trainer-service -o jsonpath='{.spec.template.spec.containers[0].image}'`
- returned `llmpromptsacr.azurecr.io/repo-rag-runtime:20260501-154923`

Live trainer publish-only proof:

- `kubectl exec -n repo-rag deploy/repo-rag-trainer-service -- sh -lc 'repo-rag trainer-cycle --root /workspace/repo-rag --queue-name manual-publish-check --run-name trainer-auto --minimum-bundle-pass-rate 1.0 --output json'`
- returned `command_status = "success"`
- returned `publish_requested = true`
- returned `publish.remote_publish.storage_backend = "azure-blob"`

Latest trainer-service history:

- latest file: `artifacts/trainer/history/20260501T161447Z-cycle-0017.json`
- salient values:
  - `queue_backend = "azure-blob-queue"`
  - `queue_found = true`
  - `failed_count = 1`
  - `new_candidate_count = 0`
  - `recompile_status = "skipped-no-new-candidates"`
  - `publish_requested = false`
  - `promotion_status = "not-requested"`

The single failure in that history record is not a new worker-side regression. It is stale
operator-side noise from an earlier manual long-name queue item that had already been deleted from
the queue path, which now surfaces as `BlobNotFound` during cleanup.

## Interpretation

Current live status:

- worker-side secure handoff: `live`
- trainer-side Azure queue drain: `live`
- trainer-side remote bundle upload from `trainer-cycle`: `live`
- trainer-side automatic promotion channel publishing: `not enabled`
- trainer-side automatic recompilation on truly new candidate data: `not disproven, but not
  observed in this latest cycle because imported traces deduped to zero new candidates`

This means `repo-rag-bundles` being non-empty is now the correct live signal that the global
trainer publication path exists. The next remaining validation target is narrower:

1. enqueue a genuinely new accepted/candidate trace that survives dedupe
2. observe `new_candidate_count > 0`
3. confirm the live service performs recompile plus remote publish without manual intervention

## Verification Commands

Repository-local checks re-run in this turn:

- `uv run python -m compileall src tests` — `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — `39 passed`
- `uv run pytest tests/test_dspy_training.py tests/test_training_samples.py tests/test_project_surfaces.py -q` — `51 passed`
- `uv run pytest tests/test_utilities.py -k 'uploads_remote_bundle_when_publish_succeeds or skips_recompile_and_publish_without_new_candidates or blocks_publish_when_bundle_benchmark_gate_fails' -q` — `3 passed`
- `uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`
- `make files-sync` — `pass`
- `make exploratorium-sync` — `pass`
- `make verify-surfaces` — `pass`
- `make exploratorium-build` — `pass`
- `make paper-build` — `pass` with LaTeX overfull/underfull box warnings, but no build failure

Operational evidence re-collected in this turn:

- `az storage blob list --account-name realagistorage --account-key "$AZURE_STORAGE_KEY" --container-name repo-rag-bundles -o table`
- `kubectl get deploy -n repo-rag repo-rag-trainer-service -o jsonpath='{.spec.template.spec.containers[0].image}'`
- `kubectl exec -n repo-rag deploy/repo-rag-trainer-service -- sh -lc 'ls -1t /workspace/repo-rag/artifacts/trainer/history | head -n 1'`
- `kubectl exec -n repo-rag deploy/repo-rag-trainer-service -- sh -lc 'cat /workspace/repo-rag/artifacts/trainer/history/20260501T161447Z-cycle-0017.json'`

Verification categories not exercised in this turn:

- linting: no dedicated lint command was run
- type checking: no dedicated type-check command was run
- coverage: no coverage command was run
- notebook execution: notebook surfaces were validated structurally through `make verify-surfaces`,
  but no notebook execution suite was run
- UI/browser validation: no UI surface exists for this change set
- end-to-end live worker consumption of a trainer-published stable bundle: not yet revalidated

## Remaining Gaps

- The live service still has `TRAINER_PROMOTE_CHANNEL = ""`, so stable/canary channel promotion is
  intentionally off.
- The latest cycle did not prove auto-recompile against a genuinely new candidate because the
  imported traces deduped to already-known examples.
- The worker-side live path still has not been revalidated against global bundle fetch/pull for a
  subsequent AKS run that consumes a trainer-published stable channel.
