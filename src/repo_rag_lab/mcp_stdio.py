"""Lightweight stdio entrypoint for the bounded repo-RAG MCP server."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .mcp_server import serve_repo_rag_mcp


def build_parser() -> argparse.ArgumentParser:
    """Return the dedicated MCP stdio argument parser."""

    parser = argparse.ArgumentParser(
        prog="python -m repo_rag_lab.mcp_stdio",
        description="Serve the bounded repo-RAG MCP surface over stdio.",
    )
    parser.add_argument("--root", default=".")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the minimal stdio MCP server entrypoint."""

    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    return serve_repo_rag_mcp(
        root,
        input_stream=sys.stdin.buffer,
        output_stream=sys.stdout.buffer,
    )


if __name__ == "__main__":
    raise SystemExit(main())
