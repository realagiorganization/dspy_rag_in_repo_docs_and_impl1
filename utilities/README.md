# Repository Utilities

These utilities give agents and contributors stable entrypoints for common repository tasks.

## Available Utilities

- `make ask QUESTION="..."`: ask a repository RAG question.
- `make discover-mcp`: list MCP server candidates discovered in the repository.
- `make utility-summary`: print a compact summary of the utility surfaces.
- `make smoke-test`: run smoke coverage for utility behavior.
- `make verify-surfaces`: validate notebook and Makefile contract surfaces.
- `make azure-manifest MODEL_ID=... DEPLOYMENT_NAME=...`: generate Azure deployment metadata.
- `uv run repo-rag ...`: invoke the packaged CLI directly through Astral's locked environment.
- `make build`: build publishable Python artifacts through `uv build`.

## Why These Utilities Exist

- Keep notebook, CLI, and test workflows aligned.
- Give agents a narrow set of preferred interfaces.
- Make regression testing focus on behavior users actually invoke.
- Keep local execution, CI, and publishing on the same Astral-managed toolchain.
