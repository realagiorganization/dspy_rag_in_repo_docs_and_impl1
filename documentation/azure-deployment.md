# Azure Deployment Notes

This repository does not fine-tune or deploy a model on its own. Its Azure support is limited to
writing a small deployment manifest, validating runtime configuration, and reusing those settings
for an optional live repository-answer path once a tuned artifact already exists.

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

## Reference Docs

- Azure AI Foundry inference endpoints: https://learn.microsoft.com/azure/ai-foundry/foundry-models/how-to/inference
- Fine-tuning in Azure OpenAI and Foundry: https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/fine-tuning
- Fine-tuned deployment flow: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/fine-tuning-deploy
