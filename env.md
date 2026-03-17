# Environment Variables

This repository is mostly build, test, notebook, and deployment-manifest scaffolding today. It
does not automatically load `.env` inside the Python package, so the file is for local shell use,
not a hidden runtime dependency. Source it before running notebooks, ad hoc scripts, or downstream
deployment steps that need Azure OpenAI or GitHub CLI credentials.

## Tracked Files And Secret Handling

- `.env.sample`: tracked, safe template with placeholders only.
- `.env`: local only, gitignored, may contain real secrets.
- `env.md`: tracked documentation for the variables the repo already references or expects around
  usage, deployment, and CI operations.

## Azure OpenAI And Deployment Variables

These are the variables most relevant to real usage and downstream deployment.

| Variable | Required for | Current repo surface | Notes |
| --- | --- | --- | --- |
| `AZURE_OPENAI_CHAT_COMPLETIONS_URI` | Direct Azure OpenAI chat completions calls | Local notebooks, ad hoc scripts, future DSPy/Azure integrations | Full REST target URI including deployment path and `api-version`. |
| `AZURE_OPENAI_ENDPOINT` | SDK-style Azure OpenAI clients | Local notebooks, ad hoc scripts, future code | Base endpoint only, without the `/openai/deployments/...` suffix. |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI authentication | Local notebooks, ad hoc scripts, future DSPy/Azure integrations | Secret. Do not commit. |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Selecting the Azure deployment | Local notebooks, ad hoc scripts, future DSPy/Azure integrations | In this repo's current local setup, this is `gpt-4o`. |
| `AZURE_OPENAI_MODEL_NAME` | Human-readable model label | Local docs and downstream tooling | Optional but useful when deployment name and model name differ. |
| `AZURE_OPENAI_API_VERSION` | Azure OpenAI request compatibility | Deployment docs and downstream tooling | The current local value is `2025-01-01-preview`. |
| `AZURE_INFERENCE_ENDPOINT` | Deployment/runtime environment contract | `src/repo_rag_lab/azure.py`, `documentation/azure-deployment.md` | This repo stores it in generated deployment manifests. |
| `AZURE_INFERENCE_CREDENTIAL` | Deployment/runtime environment contract | `src/repo_rag_lab/azure.py`, `documentation/azure-deployment.md` | Usually the same secret as `AZURE_OPENAI_API_KEY` when key auth is used. |

## GitHub And CI Operator Variables

The checked-in GitHub Actions workflows do not reference any custom repository secrets today for
the normal CI path. They only run build and test commands. These variables still matter for local
CI inspection and operator workflows.

| Variable | Required for | Current repo surface | Notes |
| --- | --- | --- | --- |
| `GH_TOKEN` | Non-interactive `gh` CLI usage | `make gh-runs`, `make gh-watch`, `make gh-failed-logs`, post-push log capture | Optional if `gh auth login` is already configured locally. |

## Make And Shell Override Variables

These are not secret env vars, but they are part of the operator-facing environment surface because
they can be exported in the shell or passed inline to `make`.

| Variable | Purpose | Current repo surface |
| --- | --- | --- |
| `QUESTION` | Override the repository question for `make ask` or `make rust-cli-run` | `Makefile` |
| `MODEL_ID` | Override the model id written into the Azure manifest | `make azure-manifest` |
| `DEPLOYMENT_NAME` | Override the deployment name written into the Azure manifest | `make azure-manifest` |
| `AZURE_ENDPOINT` | Override the endpoint written into the Azure manifest | `make azure-manifest` |
| `GH_RUN_LIMIT` | Control how many runs `make gh-runs` lists | `make gh-runs` |
| `RUN_ID` | Select a specific run for `make gh-watch` or `make gh-failed-logs` | `make gh-watch`, `make gh-failed-logs` |

## What The Repo Actually Uses Today

Current checked-in code and docs explicitly reference these runtime env vars:

- `AZURE_INFERENCE_ENDPOINT`
- `AZURE_INFERENCE_CREDENTIAL`
- `AZURE_OPENAI_API_VERSION`

Current checked-in operational tooling explicitly relies on:

- `GH_TOKEN` or an existing authenticated `gh` session for GitHub Actions inspection commands

Current local Azure OpenAI usage guidance in this repo should also carry:

- `AZURE_OPENAI_CHAT_COMPLETIONS_URI`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_DEPLOYMENT_NAME`
- `AZURE_OPENAI_MODEL_NAME`

## Recommended Local Workflow

The repo does not auto-load `.env`, so source it in your shell before running any Azure-dependent
work:

```bash
set -a
source .env
set +a
```

Example Azure manifest generation using the same values:

```bash
make azure-manifest \
  MODEL_ID="${AZURE_OPENAI_MODEL_NAME}" \
  DEPLOYMENT_NAME="${AZURE_OPENAI_DEPLOYMENT_NAME}" \
  AZURE_ENDPOINT="${AZURE_INFERENCE_ENDPOINT}"
```

Example GitHub Actions inspection:

```bash
make gh-runs GH_RUN_LIMIT=5
make gh-watch
```

## Cross-References

- `src/repo_rag_lab/azure.py`
- `documentation/azure-deployment.md`
- `Makefile`
- `.github/workflows/ci.yml`
- `.github/workflows/publish.yml`
