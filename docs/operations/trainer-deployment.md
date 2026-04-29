# Trainer Deployment Notes

This repository now exposes a concrete Kubernetes packaging surface for the trainer-side runtime.
It does not build or push images itself, but it can materialize the manifests needed to run the
background trainer roles on AKS or another Kubernetes cluster. The runtime image definition lives
in the repository-root [Dockerfile](../../Dockerfile); `../dataset` is expected to build and push
that image as `repo-rag-runtime`.

## Deployment Model

- Use one shared image family for repo-RAG runtime roles.
- Keep worker runtime and trainer runtime as separate Kubernetes roles.
- Persist `artifacts/` on shared storage so queued traces, imported traces, bundles, overlays, and
  trainer history survive pod restarts.
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
  --queue-name dataset \
  --promote-channel canary \
  --minimum-bundle-pass-rate 1.0
```

That command writes manifests under `artifacts/kubernetes/`:

- `trainer-serviceaccount.yaml`
- `trainer-configmap.yaml`
- `trainer-secret.example.yaml`
- `trainer-service.deployment.yaml`
- `trainer-cycle.cronjob.yaml`

## Runtime Contract

The generated trainer service runs:

```bash
repo-rag trainer-service --root /workspace/repo-rag ...
```

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

## Required Storage And Secrets

The generated manifests assume:

- a PVC named `repo-rag-trainer-artifacts` by default
- mounted at `/workspace/repo-rag/artifacts`
- an image pull secret named `acr-secret` by default
- a ConfigMap for non-secret runtime knobs
- a Secret for LM credentials

The generated secret example is Azure-oriented and expects:

- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT_NAME`
- `AZURE_OPENAI_API_VERSION`

Without those values the trainer can still drain queues and materialize candidates, but
trainer-side recompilation will skip because the DSPy LM contract is incomplete.

## Apply Workflow

Recommended sequence:

1. Build and publish the shared repo-RAG runtime image outside this repository.
2. Run `make trainer-k8s-manifests ...` with the final image reference.
3. Create or patch the real secret from `trainer-secret.example.yaml`.
4. Copy or create `acr-secret` in the target namespace when the cluster does not already have ACR pull rights.
5. Apply the service account, config map, secret, deployment, and cronjob.
6. Confirm that `artifacts/trainer/service-state.json` and `artifacts/trainer/history/` begin to
   populate on the mounted PVC.

## Current Boundary

This repository now packages the trainer-side runtime for Kubernetes, but it still does not:

- build/push the container image itself
- provision the PVC, namespace, or secret values
- validate a live AKS deployment in local tests
