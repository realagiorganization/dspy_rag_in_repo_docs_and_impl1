# Azure Deployment Notes

This repository prepares for Azure deployment after a DSPy-backed model or prompt program has been tuned.

## Assumed Deployment Shape

- Fine-tune or otherwise prepare the model outside this scaffold.
- Deploy the resulting model in Azure AI Foundry or Azure OpenAI.
- Invoke it through an Azure inference endpoint using a deployment name.

## Why The Repository Generates A Manifest

The scaffold writes a small JSON manifest into `artifacts/azure/` so notebook experiments, `uv run repo-rag ...` calls, and CI jobs can point at the same deployment metadata without hardcoding credentials.

## Local Workflow

Use the Astral-managed environment before generating deployment metadata:

```bash
uv sync --extra azure
uv run repo-rag azure-manifest \
  --model-id my-ft-model \
  --deployment-name repo-rag-ft \
  --endpoint https://example.services.ai.azure.com/models
```

## Required Runtime Secrets

- `AZURE_INFERENCE_ENDPOINT`
- `AZURE_INFERENCE_CREDENTIAL`
- `AZURE_OPENAI_API_VERSION`

## Official Documentation Used

- Azure AI Foundry inference endpoints: https://learn.microsoft.com/azure/ai-foundry/foundry-models/how-to/inference
- Fine-tuning in Azure OpenAI / Foundry: https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/fine-tuning
- Fine-tuned deployment flow: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/fine-tuning-deploy
