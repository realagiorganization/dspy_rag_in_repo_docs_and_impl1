# Azure Inference Endpoint Probe Audit

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Repository root: `/home/standard/dspy_rag_in_repo_docs_and_impl1`
- Git HEAD during verification: `9654adc879abd34218e7135dccbc9382f4b5623a`

## Scope

This audit covers the follow-up live validation of the Azure AI Inference endpoint after the
earlier env-refresh retest had already confirmed repository checks, notebook execution, and a live
Azure OpenAI chat-completions probe.

## Executed Commands

Executed successfully in this turn:

- `set -a; source .env; set +a; uv run python - <<'PY' ... ChatCompletionsClient(...).complete(...) ... PY`

Probe sequence:

1. Read `AZURE_INFERENCE_ENDPOINT`, `AZURE_INFERENCE_CREDENTIAL`, `AZURE_OPENAI_API_VERSION`,
   `AZURE_OPENAI_ENDPOINT`, and `AZURE_OPENAI_DEPLOYMENT_NAME` from `.env`.
2. Try the Azure AI Inference SDK against the current `AZURE_INFERENCE_ENDPOINT` value.
3. Observe that the current env value is a full Azure OpenAI chat-completions URI and returns
   `404 Resource not found` when passed directly to `ChatCompletionsClient`, because the SDK
   appends `/chat/completions` itself.
4. Derive the SDK-ready base endpoint by stripping `/chat/completions` and the query string from
   the env value, then rerun the probe.

## Notable Results

- Direct SDK use against the current `AZURE_INFERENCE_ENDPOINT` env value failed with
  `404 Resource not found`.
- The derived base endpoint path `/openai/deployments/gpt-4o` succeeded with the same credential.
- The live Azure AI Inference round trip returned:
  - reply: `INFERENCE_OK`
  - resolved model: `gpt-4o-2024-11-20`
  - finish reason: `stop`
- No `model` argument was required once the deployment was encoded in the endpoint path.

## Current Verification Status

Configured and verified in this turn:

- Live Azure AI Inference endpoint validation: present and passed through the minimal
  `ChatCompletionsClient.complete(...)` probe, using a deployment-base endpoint derived from the
  current env value

Still absent or not exercised in this turn:

- UI or browser tests: none found in the repository configuration
- Automated DSPy training compile path: not implemented in the repository today

## Notes

- The current `.env` stores `AZURE_INFERENCE_ENDPOINT` as a full request URI ending in
  `/chat/completions?...`. That shape works for direct REST calls but not for the Azure AI
  Inference SDK constructor.
- The repository documentation now clarifies that SDK callers should use the deployment base
  endpoint form instead.
- The broader repository retest evidence remains in
  `docs/audit/2026-03-18-retest-with-env-refresh.md`.
