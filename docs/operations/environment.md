# Environment Variables

This repository is mostly build, test, notebook, and deployment-manifest scaffolding today. It
does not automatically load `.env` inside the Python package, so the file is for local shell use,
not a hidden runtime dependency. Source it before running notebooks, ad hoc scripts, or downstream
deployment steps that need Azure OpenAI or GitHub CLI credentials.

## Tracked Files And Secret Handling

- `.env.sample`: tracked, safe template with placeholders only.
- `.env`: local only, gitignored, may contain real secrets.
- `environment.md`: tracked documentation for the variables the repo already references or expects around
  usage, deployment, and CI operations.

## Azure OpenAI And Deployment Variables

These are the variables most relevant to real usage and downstream deployment.

| Variable | Required for | Current repo surface | Notes |
| --- | --- | --- | --- |
| `AZURE_OPENAI_CHAT_COMPLETIONS_URI` | Direct Azure OpenAI chat completions calls | Local notebooks, ad hoc scripts, future DSPy/Azure integrations | Full REST target URI including deployment path and `api-version`. |
| `AZURE_OPENAI_ENDPOINT` | SDK-style Azure OpenAI clients | Local notebooks, ad hoc scripts, future code | Base endpoint only, without the `/openai/deployments/...` suffix. |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI authentication | Local notebooks, ad hoc scripts, future DSPy/Azure integrations | Secret. Do not commit. |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Selecting the Azure deployment | Local notebooks, ad hoc scripts, future DSPy/Azure integrations | Validated locally on `2026-04-29` with `gpt-5.4`. |
| `AZURE_OPENAI_MODEL_NAME` | Human-readable model label | Local docs and downstream tooling | Optional but useful when deployment name and model name differ. |
| `AZURE_OPENAI_API_VERSION` | Azure OpenAI request compatibility | Deployment docs and downstream tooling | Validated locally on `2026-05-01` with `2025-03-01-preview`. |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME` | Azure OpenAI semantic retrieval | `src/repo_rag_lab/semantic_retrieval.py`, `src/repo_rag_lab/retrieval.py` | Non-secret. Required for `vector` / `hybrid-vector` retrieval to build the local semantic index. |
| `AZURE_OPENAI_EMBEDDING_MODEL_NAME` | Optional embedding deployment alias/label | `src/repo_rag_lab/azure_runtime.py` | Optional fallback label when deployment name and model name are the same. |
| `AZURE_OPENAI_EMBEDDING_API_VERSION` | Optional embedding-specific API-version override | `src/repo_rag_lab/azure_runtime.py` | Falls back to `AZURE_OPENAI_API_VERSION` when unset. |
| `AZURE_INFERENCE_ENDPOINT` | Deployment/runtime environment contract | `src/repo_rag_lab/azure.py`, `azure-deployment.md` | This repo stores it in generated deployment manifests. |
| `AZURE_INFERENCE_CREDENTIAL` | Deployment/runtime environment contract | `src/repo_rag_lab/azure.py`, `azure-deployment.md` | Usually the same secret as `AZURE_OPENAI_API_KEY` when key auth is used. |

## GitHub And CI Operator Variables

The normal CI path still stays mostly build-and-test oriented, but it now also includes an
optional live Azure integration slice. That slice only becomes active when the repository or
organization provides the Azure runtime configuration through GitHub secrets and variables.

| Variable | Required for | Current repo surface | Notes |
| --- | --- | --- | --- |
| `GH_TOKEN` | Non-interactive `gh` CLI usage | `make gh-runs`, `make gh-watch`, `make gh-failed-logs`, post-push log capture | Optional if `gh auth login` is already configured locally. |
| `AZURE_OPENAI_API_KEY` | Optional live Azure OpenAI CI integration | `.github/workflows/ci.yml`, `tests/test_live_azure_integration.py` | Store as a GitHub secret. |
| `AZURE_OPENAI_ENDPOINT` | Optional live Azure OpenAI CI integration | `.github/workflows/ci.yml`, `tests/test_live_azure_integration.py` | Prefer a GitHub Actions variable because it is not itself secret. |
| `AZURE_OPENAI_CHAT_COMPLETIONS_URI` | Optional live Azure OpenAI CI integration fallback | `.github/workflows/ci.yml`, `tests/test_live_azure_integration.py` | Optional alternative to `AZURE_OPENAI_ENDPOINT`. |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Optional live Azure OpenAI CI integration | `.github/workflows/ci.yml`, `tests/test_live_azure_integration.py` | Prefer a GitHub Actions variable. |
| `AZURE_OPENAI_API_VERSION` | Optional live Azure OpenAI CI integration | `.github/workflows/ci.yml`, `tests/test_live_azure_integration.py` | Prefer a GitHub Actions variable. |
| `AZURE_OPENAI_MODEL_NAME` | Optional live Azure OpenAI CI labeling | `.github/workflows/ci.yml` | Optional, non-secret. |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME` | Optional live semantic retrieval | Retrieval-heavy local/CI runs, worker-side Codex mediation | Prefer a GitHub Actions variable because it is not itself secret. |
| `AZURE_OPENAI_EMBEDDING_API_VERSION` | Optional live semantic retrieval override | Retrieval-heavy local/CI runs | Optional; defaults to `AZURE_OPENAI_API_VERSION`. |

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
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME`

Current checked-in operational tooling explicitly relies on:

- `GH_TOKEN` or an existing authenticated `gh` session for GitHub Actions inspection commands

Current checked-in optional live CI integration additionally reads:

- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT` or `AZURE_OPENAI_CHAT_COMPLETIONS_URI`
- `AZURE_OPENAI_DEPLOYMENT_NAME`
- `AZURE_OPENAI_API_VERSION`

Current local Azure OpenAI usage guidance in this repo should also carry:

- `AZURE_OPENAI_CHAT_COMPLETIONS_URI`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_DEPLOYMENT_NAME`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_MODEL_NAME`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME`
- `AZURE_OPENAI_EMBEDDING_API_VERSION` when the embedding deployment needs a different API-version

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
- `azure-deployment.md`
- `Makefile`
- `.github/workflows/ci.yml`
- `.github/workflows/publish.yml`
