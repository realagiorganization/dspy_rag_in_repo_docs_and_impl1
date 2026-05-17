# Trainer Deployment Notes

This repository now exposes a concrete Kubernetes packaging surface for the trainer-side runtime.
It does not build or push images itself, but it can materialize the manifests needed to run the
background trainer roles on AKS or another Kubernetes cluster. The runtime image definition lives
in the repository-root [Dockerfile](../../Dockerfile); `../dataset` is expected to build and push
that image as `repo-rag-runtime`.

## Deployment Model

- Use one shared image family for repo-RAG runtime roles.
- Keep worker runtime and trainer runtime as separate Kubernetes roles.
- Treat Azure Blob + Queue as the primary cross-namespace transport for worker traces and promoted
  DSPy bundles.
- Treat the immutable bundle version directory under `versions/<timestamp>/` as the primary
  runtime artifact, with deployment-time `DSPY_BUNDLE_VERSION` pinning selecting which published
  version workers should consume.
- Mount one shared artifacts PVC for temporary queue-cycle artifacts, imported traces, remote
  family-state mirrors, and current-cycle generated trainer files.
- Do not treat the PVC as the durable trainer baseline; the baseline must always come from the
  latest remote `repo-rag-training-families` version.
- Keep the older file-backed queue path as compatibility-only; it is no longer the primary worker
  to trainer contract.
- Keep Azure/OpenAI or `DSPY_*` credentials outside source control in a Kubernetes Secret.

## Generated Surfaces

```bash
make trainer-k8s-manifests \
  TRAINER_K8S_IMAGE=ghcr.io/realagiorganization/repo-rag-lab:latest \
  TRACE_QUEUE_NAME=dataset
```

The equivalent direct CLI command is:

```bash
uv run repo-rag trainer-k8s-manifests \
  --image ghcr.io/realagiorganization/repo-rag-lab:latest \
  --namespace repo-rag \
  --queue-name dataset
```

That command writes manifests under `artifacts/kubernetes/`:

- `trainer-serviceaccount.yaml`
- `trainer-configmap.yaml`
- `trainer-secret.example.yaml`
- `repo-rag-artifacts.pvc.yaml`
- `trainer-cycle.cronjob.yaml`

## Runtime Contract

The generated CronJob runs:

```bash
repo-rag trainer-cycle --root /workspace/repo-rag ...
```

Both surfaces still reuse the same repo-native runtime contract as the local Makefile:

- `TRACE_QUEUE_NAME`
- `RETRIEVAL_TRAINING_PATH`
- `RETRIEVAL_TOP_K`
- `RETRIEVAL_TOP_K_SWEEP`
- `RETRIEVAL_MODE`
- `RETRIEVAL_MIN_PASS_RATE`
- `RETRIEVAL_MIN_SOURCE_RECALL`
- `TRAINER_MIN_BUNDLE_PASS_RATE`
- `TRAINER_RECOMPILE_RUN_NAME`
- `TRAINER_RECOMPILE_BASE_TRAINING_PATH`
- `TRAINER_PROMOTE_CHANNEL`

For the downstream `dataset` deployment contract, workers do not need channel promotion in order
to use a global bundle. The primary runtime selector is one explicit immutable bundle version
distributed through `DSPY_BUNDLE_VERSION`; `stable` / `canary` remain optional alias or rollback
surfaces when a deployment wants indirection instead of direct version pinning.

The generated AKS surface now defaults to a cron-only posture:

- a single `trainer-cycle` CronJob scheduled every five minutes
- no long-lived `trainer-service` Deployment in cluster manifests
- no duplicate publish loop competing with the CronJob for the same queue
- the existing `trainer-service` CLI remains available only for local debugging

## Required Storage And Secrets

The generated manifests assume:

- a PVC named `repo-rag-artifacts` by default
- mounted at `/workspace/repo-rag/artifacts`
- an image pull secret named `acr-secret` by default
- a ConfigMap for non-secret runtime knobs
- a Secret for LM credentials
- Azure Storage credentials for the global trace/bundle store, typically:
  - `AZURE_STORAGE_ACCOUNT`
  - `AZURE_STORAGE_KEY` or `AZURE_STORAGE_CONNECTION_STRING`
  - `DATASET_REPO_RAG_TRACE_CONTAINER`
  - `DATASET_REPO_RAG_BUNDLE_CONTAINER`
  - `DATASET_REPO_RAG_TRACE_QUEUE_NAME`

The generated secret example is Azure-oriented and expects:

- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT_NAME`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_MODEL_NAME` optionally, when the deployment metadata should remain explicit
- `AZURE_STORAGE_ACCOUNT`
- `AZURE_STORAGE_KEY`
- `DATASET_REPO_RAG_TRACE_CONTAINER`
- `DATASET_REPO_RAG_BUNDLE_CONTAINER`
- `DATASET_REPO_RAG_TRACE_QUEUE_NAME`

Without those values the trainer can still drain queues and materialize candidates, but
trainer-side recompilation will skip because the DSPy LM contract is incomplete. Without Azure
Storage credentials the trainer falls back to the local filesystem queue and local bundle registry,
which is suitable for single-repo development but not for the intended global multi-namespace
deployment.

## Apply Workflow

Recommended sequence:

1. Build and publish the shared repo-RAG runtime image outside this repository.
2. Run `make trainer-k8s-manifests ...` with the final image reference.
3. Create the Azure Blob containers and Azure Queue used for global trainer transport.
4. Apply `repo-rag-artifacts.pvc.yaml` and wait for the claim to reach `Bound`.
5. Create or patch the real secret from `trainer-secret.example.yaml`.
6. Copy or create `acr-secret` in the target namespace when the cluster does not already have ACR pull rights.
7. Apply the service account, config map, deployment, and cronjob.
8. Confirm that `artifacts/traces/queued/`, `artifacts/traces/imported/`, and
   `artifacts/trainer/remote-family-state/` begin to populate on the mounted PVC during active
   cycles.

If `../dataset/deploy_repo_rag_trainer.sh` is used, that script now automates the PVC apply,
ACR pull-secret creation, Azure/OpenAI secret creation from `AZURE_OPENAI_*`, Azure Blob/Queue
bootstrap from `AZURE_STORAGE_*`, and rollout wait with diagnostics.

## Current Boundary

This repository now packages the trainer-side runtime for Kubernetes, but it still does not:

- build/push the container image itself
- provision the live namespace or cluster access itself
- validate a live AKS deployment in local tests
