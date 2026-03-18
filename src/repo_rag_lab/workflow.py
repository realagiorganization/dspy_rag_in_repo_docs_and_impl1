"""Baseline repository question-answering workflow built on file retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .azure_runtime import call_azure_inference_chat, call_azure_openai_chat
from .corpus import load_documents
from .mcp import discover_mcp_servers
from .retrieval import Chunk, chunk_documents, retrieve

LiveProvider = Literal["azure-openai", "azure-inference"]


@dataclass(frozen=True)
class RAGAnswer:
    """Answer payload returned by the baseline repository RAG workflow."""

    question: str
    answer: str
    context: list[Chunk]
    mcp_servers: list[dict[str, str]]


def collect_repository_evidence(
    question: str, root: Path
) -> tuple[list[Chunk], list[dict[str, str]]]:
    """Collect retrieved context chunks and MCP hints for ``question``."""

    documents = load_documents(root)
    chunks = chunk_documents(documents)
    context = retrieve(question, chunks)
    mcp_servers = [candidate.__dict__ for candidate in discover_mcp_servers(root)]
    return context, mcp_servers


def ask_repository(question: str, root: Path) -> RAGAnswer:
    """Answer a repository-grounded question using the baseline retrieval pipeline."""

    context, mcp_servers = collect_repository_evidence(question, root)
    answer = synthesize_answer(question=question, context=context, mcp_servers=mcp_servers)
    return RAGAnswer(question=question, answer=answer, context=context, mcp_servers=mcp_servers)


def ask_repository_live(
    question: str,
    root: Path,
    *,
    provider: LiveProvider,
    load_env_file: bool = False,
) -> RAGAnswer:
    """Answer a repository-grounded question with retrieved evidence plus a live Azure model."""

    context, mcp_servers = collect_repository_evidence(question, root)
    if not context:
        answer = synthesize_answer(question=question, context=context, mcp_servers=mcp_servers)
        return RAGAnswer(question=question, answer=answer, context=context, mcp_servers=mcp_servers)

    system_prompt, user_prompt = build_live_answer_messages(
        question=question,
        context=context,
        mcp_servers=mcp_servers,
    )
    if provider == "azure-openai":
        completion = call_azure_openai_chat(
            system_prompt,
            user_prompt,
            root=root,
            load_env_file=load_env_file,
        )
    elif provider == "azure-inference":
        completion = call_azure_inference_chat(
            system_prompt,
            user_prompt,
            root=root,
            load_env_file=load_env_file,
        )
    else:  # pragma: no cover - parser-level validation handles this branch
        raise ValueError(f"Unsupported live provider: {provider}")

    return RAGAnswer(
        question=question,
        answer=completion.answer.strip(),
        context=context,
        mcp_servers=mcp_servers,
    )


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
        lines.append(f"- {chunk.source}: {_chunk_preview(chunk)}")
    if mcp_servers:
        lines.append("")
        lines.append("Discovered MCP candidates:")
        for server in mcp_servers:
            lines.append(f"- {server['path']}: {server['hint']}")
    return "\n".join(lines)


def _chunk_preview(chunk: Chunk) -> str:
    """Return the short preview used in baseline and live-answer prompts."""

    return " ".join(chunk.text.split())[:240]


def build_live_answer_messages(
    *,
    question: str,
    context: list[Chunk],
    mcp_servers: list[dict[str, str]],
) -> tuple[str, str]:
    """Build the system and user prompts for a cloud-backed repository answer."""

    evidence_lines = [f"- {chunk.source}: {_chunk_preview(chunk)}" for chunk in context]
    mcp_lines = [f"- {server['path']}: {server['hint']}" for server in mcp_servers]
    user_lines = [
        f"Question: {question}",
        "",
        "Repository evidence:",
        *evidence_lines,
    ]
    if mcp_lines:
        user_lines.extend(["", "MCP candidates:", *mcp_lines])
    user_lines.extend(
        [
            "",
            "Answer the question using only the repository evidence above.",
            "If the evidence is incomplete, say so directly.",
            "Mention concrete file paths when they support the answer.",
        ]
    )
    system_prompt = (
        "You answer questions about the current repository using only the supplied evidence. "
        "Do not invent files, behavior, or configuration that are not present in the evidence."
    )
    return system_prompt, "\n".join(user_lines)
