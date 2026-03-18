# Repository Utilities

These utilities are the stable entrypoints for contributors, agents, notebooks, and CI. Prefer
them over ad hoc shell commands so every workflow hits the same package code.

## Core Commands

- `make utility-summary`: list the supported user-facing utility surfaces.
- `make ask QUESTION="..."`: answer a repository-grounded question with the baseline RAG flow.
- `make discover-mcp`: inspect repository-local MCP candidates.
- `make smoke-test`: exercise answer generation, MCP discovery, and Azure manifest output together.
- `make verify-surfaces`: validate the Makefile and notebook contract.
- `make notebook-report`: execute all tracked notebooks with monitored progress and report artifacts.
- `make gh-runs`: list the latest GitHub Actions runs with `gh`.
- `make gh-watch`: watch the latest or selected GitHub Actions run and exit with its status.
- `make gh-failed-logs`: show failed job logs for the latest or selected run.
- `make azure-manifest MODEL_ID=... DEPLOYMENT_NAME=...`: write Azure deployment metadata.
- `uv run repo-rag ...`: call the packaged CLI directly inside the locked `uv` environment.
- `make build`: build the wheel and source distribution through `uv build`.
- Notebooks reuse `src/repo_rag_lab/notebook_scaffolding.py` and `src/repo_rag_lab/notebook_support.py`
  for sample validation, benchmark assertions, tuning metadata, and notebook-run logging.
- Batch notebook runs also use `src/repo_rag_lab/notebook_runner.py` to stream progress, capture
  raw logs, and write JSON plus Markdown reports under `artifacts/notebook_runs/`.

## Why The Repository Uses These Surfaces

- Keep notebooks, tests, automation, and manual runs aligned.
- Give agents one preferred command vocabulary.
- Focus verification on behavior users actually invoke.
- Keep local execution, CI, and publishing on the same `uv`-managed toolchain.
