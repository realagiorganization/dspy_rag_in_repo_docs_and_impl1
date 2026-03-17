"""Baseline repository question-answering workflow built on file retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .corpus import load_documents
from .mcp import discover_mcp_servers
from .retrieval import Chunk, chunk_documents, retrieve


@dataclass(frozen=True)
class RAGAnswer:
    """Answer payload returned by the baseline repository RAG workflow."""

    question: str
    answer: str
    context: list[Chunk]
    mcp_servers: list[dict[str, str]]


def ask_repository(question: str, root: Path) -> RAGAnswer:
    """Answer a repository-grounded question using the baseline retrieval pipeline."""

    documents = load_documents(root)
    chunks = chunk_documents(documents)
    context = retrieve(question, chunks)
    mcp_servers = [candidate.__dict__ for candidate in discover_mcp_servers(root)]
    answer = synthesize_answer(question=question, context=context, mcp_servers=mcp_servers)
    return RAGAnswer(question=question, answer=answer, context=context, mcp_servers=mcp_servers)


def synthesize_answer(
    question: str, context: list[Chunk], mcp_servers: list[dict[str, str]]
) -> str:
    """Render a readable answer from retrieved context and MCP discovery hints."""

    if not context:
        return (
            f"No repository evidence matched the question: {question!r}. "
            "Add more documentation, code, or examples before evaluating RAG quality."
        )

    lines = [f"Question: {question}", "", "Evidence:"]
    for chunk in context:
        preview = " ".join(chunk.text.split())[:240]
        lines.append(f"- {chunk.source}: {preview}")
    if mcp_servers:
        lines.append("")
        lines.append("Discovered MCP candidates:")
        for server in mcp_servers:
            lines.append(f"- {server['path']}: {server['hint']}")
    return "\n".join(lines)
