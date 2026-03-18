# Repository Utilities

These utilities are the stable entrypoints for contributors, agents, notebooks, and CI. Prefer
them over ad hoc shell commands so every workflow hits the same package code.

## Core Commands

- `make utility-summary`: list the supported user-facing utility surfaces.
- `make files-sync`: regenerate the tracked-file inventory surfaces `FILES.md` and `FILES.csv`.
- `make ask QUESTION="..."`: answer a repository-grounded question with the baseline RAG flow.
- `make ask-dspy QUESTION="..."`: answer through the DSPy runtime path, optionally loading a saved
  compiled program, and automatically reusing the latest saved one when no explicit program path is
  provided.
- `make ask-live QUESTION="..."`: retrieve repository evidence locally, then synthesize the answer
  through Azure OpenAI or Azure AI Inference.
- `make dspy-train DSPY_RUN_NAME=...`: compile and persist a repository-grounded DSPy program under
  `artifacts/dspy/`.
- `make dspy-artifacts`: inspect the saved DSPy runs, latest program path, and recorded benchmark
  summaries.
- `make exploratorium-sync`: regenerate the bilingual publication inventory of files, links, and
  fetch state.
- `make retrieval-eval`: evaluate retrieval quality across a top-k sweep with source recall,
  precision, reciprocal-rank metrics, and per-tag benchmark summaries.
- `make discover-mcp`: inspect repository-local MCP candidates.
- `make smoke-test`: exercise answer generation, MCP discovery, and Azure manifest output together.
- `make azure-openai-probe`: validate the Azure OpenAI runtime contract and run a minimal live
  round trip.
- `make azure-inference-probe`: validate and normalize the Azure AI Inference runtime contract and
  run a minimal live round trip.
- `make todo-sync`: regenerate the shared TODO backlog table for both `TODO.MD` and the publication PDF source.
- `make exploratorium-build`: build the committed bilingual exploratorium translation PDF.
- `make verify-surfaces`: validate the Makefile and notebook contract.
- `make notebook-report`: execute all tracked notebooks with monitored progress and report artifacts.
- `make gh-runs`: list the latest GitHub Actions runs with `gh`.
- `make gh-watch`: watch the latest or selected GitHub Actions run and exit with its status.
- `make gh-failed-logs`: show failed job logs for the latest or selected run.
- `make azure-manifest MODEL_ID=... DEPLOYMENT_NAME=...`: write Azure deployment metadata.
- `uv run repo-rag ...`: call the packaged CLI directly inside the locked `uv` environment.
- `make build`: build the wheel and source distribution through `uv build`.
- Notebooks reuse `src/repo_rag_lab/notebook_scaffolding.py` and `src/repo_rag_lab/notebook_support.py`
  for sample validation, benchmark assertions, tuning metadata, latest compiled-program inspection,
  and notebook-run logging.
- Batch notebook runs also use `src/repo_rag_lab/notebook_runner.py` to stream progress, capture
  raw logs, and write JSON plus Markdown reports under `artifacts/notebook_runs/`.

## Why The Repository Uses These Surfaces

- Keep notebooks, tests, automation, and manual runs aligned.
- Give agents one preferred command vocabulary.
- Focus verification on behavior users actually invoke.
- Keep local Azure runtime validation on the same package entrypoints as the docs and notebooks.
- Keep local execution, CI, and publishing on the same `uv`-managed toolchain.
