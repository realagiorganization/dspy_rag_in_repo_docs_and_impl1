# MCP Discovery Notes

The repository treats MCP discovery as a reusable research surface rather than notebook-only glue.

## Current Heuristics

`src/repo_rag_lab/mcp.py` scans the repository for:

- `mcp.json`
- `.mcp.json`
- `pyproject.toml`
- `Cargo.toml`
- `package.json`

It emits a candidate only when the file shape or contents suggest MCP-related behavior.

## Notebook Usage

The notebooks use MCP discovery in two ways:

- to record repo-local MCP candidates alongside retrieval experiments
- to keep corpus-population follow-up work grounded in real MCP-related files

## Why This Doc Exists

Population scaffolding now extends the starter corpus candidates with MCP-specific documentation so follow-up work can cite a stable explanation of the current discovery behavior.
