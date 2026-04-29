# Azure Deployment Notes

This repository does not fine-tune or deploy a model on its own. Its Azure support is limited to
writing a small deployment manifest, validating runtime configuration, and reusing those settings
for an optional live repository-answer path once a tuned artifact already exists.

Current central inference decision:

- use Azure OpenAI or Azure AI Inference as the shared inference layer for worker-side answering
  and trainer-side live recompilation
- keep that inference layer external to this repository and external to the `dataset` worker image
- defer any shared internal model-serving layer until cost, latency, or compliance requirements
  justify replacing the current Azure/OpenAI contract

## Deployment Contract

- Produce or tune the model outside this repository.
- Deploy the resulting model in Azure AI Foundry or Azure OpenAI.
- Use this repository to write consistent deployment metadata into `artifacts/azure/`.

## Why The Manifest Exists

The manifest keeps notebooks, CLI runs, CI jobs, and downstream deployment automation pointed at
the same deployment name and endpoint shape without hardcoding credentials into source control.

## Preferred Local Workflow

```bash
uv sync --extra azure
make azure-manifest MODEL_ID=my-ft-model DEPLOYMENT_NAME=repo-rag-ft
make azure-openai-probe
make azure-inference-probe
make ask-live QUESTION="What does this repository research?"
```

The equivalent direct CLI command is:

```bash
uv run repo-rag azure-manifest \
  --model-id my-ft-model \
  --deployment-name repo-rag-ft \
  --endpoint https://example.services.ai.azure.com/models
```

## Optional CI Integration

The repository CI now includes an env-gated live Azure integration slice. It remains safe for
forks and partially configured repositories because the test file skips itself unless the full
Azure OpenAI runtime contract is present in the workflow environment.

Recommended GitHub configuration:

- repository or organization secret: `AZURE_OPENAI_API_KEY`
- repository or organization variables:
  - `AZURE_OPENAI_ENDPOINT` or `AZURE_OPENAI_CHAT_COMPLETIONS_URI`
  - `AZURE_OPENAI_DEPLOYMENT_NAME`
  - `AZURE_OPENAI_API_VERSION`
  - optional `AZURE_OPENAI_MODEL_NAME`

Validated bounded local Azure OpenAI example on `2026-04-29`:

- `AZURE_OPENAI_ENDPOINT=https://gpt45standard.openai.azure.com/`
- `AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5.4`
- `AZURE_OPENAI_API_VERSION=2024-12-01-preview`
- optional `AZURE_OPENAI_MODEL_NAME=gpt-5.4`

That configuration now passes all of:

- `uv run repo-rag azure-openai-probe`
- `uv run repo-rag ask-live --question "What does this repository research?" --provider azure-openai --output json`
- `uv run repo-rag trainer-recompile --run-name trainer-live-check --output json`

`repo-rag trainer-cycle --recompile-run-name ... --output json` also now executes a real live
recompile against the same deployment and then correctly blocks publish when the trainer-side DSPy
benchmark gate is not met.

## Required Runtime Secrets

- `AZURE_INFERENCE_ENDPOINT`
- `AZURE_INFERENCE_CREDENTIAL`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_DEPLOYMENT_NAME`
- `AZURE_OPENAI_API_VERSION`

For the Azure AI Inference SDK, `AZURE_INFERENCE_ENDPOINT` should be the deployment base endpoint,
for example `https://<host>/openai/deployments/<deployment>`, not the full
`.../chat/completions?...` request URI. The SDK appends `/chat/completions` itself.

The repository CLI now normalizes either form automatically for `repo-rag azure-inference-probe`
and `repo-rag ask-live --provider azure-inference`. When `AZURE_INFERENCE_ENDPOINT` is absent,
those commands can also derive the deployment-base endpoint from `AZURE_OPENAI_ENDPOINT` plus
`AZURE_OPENAI_DEPLOYMENT_NAME`.

For Azure OpenAI callers, `AZURE_OPENAI_ENDPOINT` can be the host origin or can be derived from
`AZURE_OPENAI_CHAT_COMPLETIONS_URI`. The CLI also derives `AZURE_OPENAI_DEPLOYMENT_NAME` from the
chat-completions URI when that is the only deployment-shaped value present.

For newer GPT-5-class Azure OpenAI chat-completions deployments, the probe and live-answer path
now prefer `max_completion_tokens` and only fall back to `max_tokens` when the model explicitly
rejects the newer parameter. This keeps the runtime compatible across both newer and older Azure
OpenAI chat-completions surfaces without forcing separate code paths in operators or CI.

For the trainer-side Kubernetes packaging that consumes those same runtime variables, see
[trainer-deployment.md](trainer-deployment.md).

## Reference Docs

- Azure AI Foundry inference endpoints: https://learn.microsoft.com/azure/ai-foundry/foundry-models/how-to/inference
- Fine-tuning in Azure OpenAI and Foundry: https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/fine-tuning
- Fine-tuned deployment flow: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/fine-tuning-deploy
