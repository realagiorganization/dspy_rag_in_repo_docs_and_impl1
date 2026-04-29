# MCP Discovery Notes

The repository treats MCP discovery as a reusable package surface rather than notebook-only glue.

This note is about discovery, not about the live MCP transport. The repository now also exposes a
bounded stdio MCP server through `repo-rag serve-mcp`, but that server intentionally wraps only
short-running repo-RAG tools and leaves heavy DSPy training or retrieval evaluation on the direct
CLI path.

## Current Heuristics

`src/repo_rag_lab/mcp.py` scans the repository for:

- `mcp.json`
- `.mcp.json`
- `pyproject.toml`
- `Cargo.toml`
- `package.json`

It emits a candidate only when the file path or file contents suggest MCP-related behavior.

## Notebook Usage

The notebooks use MCP discovery in two ways:

- to record repo-local MCP candidates alongside retrieval experiments
- to keep corpus-population follow-up work grounded in real MCP-related files

## Why This Doc Exists

Population scaffolding extends the starter corpus candidates with MCP-specific documentation so
follow-up work can cite a stable explanation of the current discovery behavior.

## Bounded MCP Runtime Surface

The current MCP transport is intentionally narrow:

- `ask_repo`: baseline repo-grounded ask with local retrieval only
- `bundle_status`: inspect stable/canary bundle state
- `dspy_artifacts`: list saved DSPy artifacts
- `publish_trace`: enqueue one normalized worker trace for later asynchronous drain

The following intentionally do **not** go through MCP in this repository:

- `dspy-train`
- `trainer-recompile`
- `trainer-cycle`
- `trainer-service`
- `retrieval-eval`
- notebook execution

That boundary keeps MCP calls short and predictable while the main runtime continues to use the
machine-readable CLI family for heavier work.
