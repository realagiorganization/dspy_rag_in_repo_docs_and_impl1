# Package API Notes

This repository keeps notebook logic in small Python modules under `src/repo_rag_lab/` so
notebooks stay readable, testable, and aligned with CLI and automation entrypoints.

## Core Workflow Modules

- `workflow.py`: baseline repository-grounded retrieval and answer synthesis.
- `dspy_workflow.py`: DSPy-shaped retriever and response flow when DSPy is installed.
- `corpus.py`: repository text discovery and document loading.
- `retrieval.py`: chunking and lexical retrieval helpers.
- `mcp.py`: repo-local MCP server candidate discovery.

## Notebook-Facing Modules

- `notebook_support.py`: repository-root resolution, notebook assertions, and notebook run logging.
- `notebook_scaffolding.py`: high-level training, workflow, and population scaffolds used directly by notebooks.
- `training_samples.py`: training sample loading, summarization, and validation.
- `population_samples.py`: population candidate loading, extension, validation, and empirical re-ranking.
- `benchmarks.py`: retrieval benchmark assertions derived from training samples.

## Utility Surfaces

- `repo-rag ask --question "..."`: run the baseline or DSPy-shaped RAG workflow.
- `repo-rag discover-mcp`: inspect MCP discovery candidates.
- `repo-rag smoke-test`: run a compact workflow smoke test.
- `repo-rag verify-surfaces`: validate the repository utility and notebook contract surfaces.
- `repo-rag azure-manifest`: write Azure deployment metadata for downstream deployment workflows.
