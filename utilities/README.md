# Repository Utilities

These utilities are the stable entrypoints for contributors, agents, notebooks, and CI. Prefer
them over ad hoc shell commands so every workflow hits the same package code.

## Core Commands

- `make utility-summary`: list the supported user-facing utility surfaces.
- `make ask QUESTION="..."`: answer a repository-grounded question with the baseline RAG flow.
- `make discover-mcp`: inspect repository-local MCP candidates.
- `make smoke-test`: exercise answer generation, MCP discovery, and Azure manifest output together.
- `make verify-surfaces`: validate the Makefile and notebook contract.
- `make azure-manifest MODEL_ID=... DEPLOYMENT_NAME=...`: write Azure deployment metadata.
- `uv run repo-rag ...`: call the packaged CLI directly inside the locked `uv` environment.
- `make build`: build the wheel and source distribution through `uv build`.

## Why The Repository Uses These Surfaces

- Keep notebooks, tests, automation, and manual runs aligned.
- Give agents one preferred command vocabulary.
- Focus verification on behavior users actually invoke.
- Keep local execution, CI, and publishing on the same `uv`-managed toolchain.
