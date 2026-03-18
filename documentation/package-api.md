# Package API Notes

This repository keeps notebook logic in small Python modules under `src/repo_rag_lab/` so
notebooks stay readable, testable, and aligned with CLI and automation entrypoints.

## Core Workflow Modules

- `workflow.py`: baseline repository-grounded retrieval and answer synthesis.
- `dspy_workflow.py`: DSPy-shaped retriever and response flow when DSPy is installed.
- `dspy_training.py`: DSPy compile, artifact persistence, latest-run inspection, and LM resolution.
- `corpus.py`: repository text discovery and document loading.
- `retrieval.py`: chunking and lexical retrieval helpers.
- `mcp.py`: repo-local MCP server candidate discovery.

## Notebook-Facing Modules

- `notebook_support.py`: repository-root resolution, notebook assertions, and notebook run logging.
- `notebook_runner.py`: monitored batch execution, `.env` loading, and report generation for all tracked notebooks.
- `notebook_scaffolding.py`: high-level training, workflow, population, and fixture-specific scaffolds used directly by notebooks.
- `training_samples.py`: training sample loading, summarization, and validation.
- `population_samples.py`: population candidate loading, extension, validation, and empirical re-ranking.
- `benchmarks.py`: retrieval benchmark assertions derived from training samples.

## Utility Surfaces

- `repo-rag ask --question "..."`: run the baseline or DSPy-shaped RAG workflow.
- `repo-rag dspy-train --run-name ...`: compile and persist a repository-grounded DSPy program.
- `repo-rag dspy-artifacts`: inspect saved DSPy runs and the latest compiled program path.
- `repo-rag ask-live --question "..."`: run baseline retrieval locally, then synthesize a live
  answer through Azure OpenAI or Azure AI Inference.
- `repo-rag discover-mcp`: inspect MCP discovery candidates.
- `repo-rag smoke-test`: run a compact workflow smoke test.
- `repo-rag verify-surfaces`: validate the repository utility and notebook contract surfaces.
- `repo-rag run-notebooks`: execute all tracked notebooks with monitored progress and report artifacts.
- `repo-rag azure-manifest`: write Azure deployment metadata for downstream deployment workflows.
- `repo-rag azure-openai-probe`: normalize and validate the Azure OpenAI runtime contract.
- `repo-rag azure-inference-probe`: normalize and validate the Azure AI Inference runtime contract.
