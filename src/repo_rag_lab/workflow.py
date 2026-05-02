"""Baseline repository question-answering workflow built on file retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .azure_runtime import call_azure_inference_chat, call_azure_openai_chat
from .corpus import RepoDocument, load_documents, load_documents_for_paths
from .mcp import discover_mcp_servers
from .retrieval import (
    TOKEN_RE,
    Chunk,
    RetrievalExecution,
    RetrievalMode,
    chunk_documents,
    resolve_retrieval_mode,
    retrieve_with_metadata,
)
from .retrieval_profile import RetrievalProfile, load_retrieval_profile
from .rust_lookup import lookup_candidate_paths

LiveProvider = Literal["azure-openai", "azure-inference"]
QUESTION_FILLER_TERMS = {
    "a",
    "an",
    "are",
    "does",
    "how",
    "is",
    "the",
    "this",
    "what",
    "where",
}
QUESTION_LIST_PENALTY_MARKERS = (
    "suggested retrieval questions",
    "sample retrieval questions",
)


@dataclass(frozen=True)
class RAGAnswer:
    """Answer payload returned by the baseline repository RAG workflow."""

    question: str
    answer: str
    context: list[Chunk]
    mcp_servers: list[dict[str, str]]
    summary: str
    retrieval_mode: RetrievalMode
    retrieval_warnings: tuple[str, ...] = ()

    def to_payload(self, *, root: Path) -> dict[str, object]:
        """Return a machine-readable payload for CLI and worker integrations."""

        machine_answer = self.summary
        response_text = self.answer
        for chunk in self.context:
            relative_source = _relative_source_path(chunk.source, root=root)
            machine_answer = machine_answer.replace(chunk.source.as_posix(), relative_source)
            response_text = response_text.replace(chunk.source.as_posix(), relative_source)
        return {
            "question": self.question,
            "answer": machine_answer,
            "response_text": response_text,
            "sources": list(
                dict.fromkeys(
                    _relative_source_path(chunk.source, root=root) for chunk in self.context
                )
            ),
            "context": [serialize_chunk(chunk, root=root) for chunk in self.context],
            "mcp_candidates": list(self.mcp_servers),
            "retrieval_mode": self.retrieval_mode,
            "retrieval_warnings": list(self.retrieval_warnings),
        }


def collect_repository_evidence(
    question: str,
    root: Path,
    *,
    retrieval_mode: RetrievalMode | None = None,
) -> tuple[list[Chunk], list[dict[str, str]], RetrievalMode]:
    """Collect retrieved context chunks and MCP hints for ``question``."""

    profile, resolved_mode = _resolve_retrieval_profile(root, retrieval_mode=retrieval_mode)
    execution = _collect_repository_context_execution(
        question,
        root,
        retrieval_mode=resolved_mode,
        profile=profile,
    )
    mcp_servers = [candidate.__dict__ for candidate in discover_mcp_servers(root)]
    return list(execution.chunks), mcp_servers, execution.retrieval_mode


def collect_repository_context(
    question: str,
    root: Path,
    *,
    top_k: int = 4,
    retrieval_mode: RetrievalMode | None = None,
    profile: RetrievalProfile | None = None,
) -> list[Chunk]:
    """Collect lookup-first repository context for ``question``."""

    return list(
        _collect_repository_context_execution(
            question,
            root,
            top_k=top_k,
            retrieval_mode=retrieval_mode,
            profile=profile,
        ).chunks
    )


def _collect_repository_context_execution(
    question: str,
    root: Path,
    *,
    top_k: int = 4,
    retrieval_mode: RetrievalMode | None = None,
    profile: RetrievalProfile | None = None,
) -> RetrievalExecution:
    """Collect lookup-first repository context plus retrieval diagnostics."""

    resolved_profile, resolved_mode = _resolve_retrieval_profile(
        root,
        retrieval_mode=retrieval_mode,
        profile=profile,
    )
    lookup_paths = lookup_candidate_paths(question, root)
    if lookup_paths:
        narrowed_documents = load_documents_for_paths(root, lookup_paths)
        narrowed_context = _retrieve_from_documents(
            question,
            narrowed_documents,
            root=root,
            top_k=top_k,
            profile=resolved_profile,
            retrieval_mode=resolved_mode,
        )
        if narrowed_context.chunks:
            return narrowed_context

    return _retrieve_from_documents(
        question,
        load_documents(root),
        root=root,
        top_k=top_k,
        profile=resolved_profile,
        retrieval_mode=resolved_mode,
    )


def ask_repository(
    question: str,
    root: Path,
    *,
    retrieval_mode: RetrievalMode | None = None,
) -> RAGAnswer:
    """Answer a repository-grounded question using the baseline retrieval pipeline."""

    execution = _collect_repository_context_execution(
        question,
        root,
        retrieval_mode=retrieval_mode,
    )
    context = list(execution.chunks)
    mcp_servers = [candidate.__dict__ for candidate in discover_mcp_servers(root)]
    resolved_mode = execution.retrieval_mode
    summary = (
        _compose_answer_summary(question, context) if context else _no_evidence_message(question)
    )
    answer = synthesize_answer(question=question, context=context, mcp_servers=mcp_servers)
    return RAGAnswer(
        question=question,
        answer=answer,
        context=context,
        mcp_servers=mcp_servers,
        summary=summary,
        retrieval_mode=resolved_mode,
        retrieval_warnings=execution.warnings,
    )


def ask_repository_live(
    question: str,
    root: Path,
    *,
    provider: LiveProvider,
    load_env_file: bool = False,
    retrieval_mode: RetrievalMode | None = None,
) -> RAGAnswer:
    """Answer a repository-grounded question with retrieved evidence plus a live Azure model."""

    execution = _collect_repository_context_execution(
        question,
        root,
        retrieval_mode=retrieval_mode,
    )
    context = list(execution.chunks)
    mcp_servers = [candidate.__dict__ for candidate in discover_mcp_servers(root)]
    resolved_mode = execution.retrieval_mode
    if not context:
        summary = _no_evidence_message(question)
        answer = synthesize_answer(question=question, context=context, mcp_servers=mcp_servers)
        return RAGAnswer(
            question=question,
            answer=answer,
            context=context,
            mcp_servers=mcp_servers,
            summary=summary,
            retrieval_mode=resolved_mode,
            retrieval_warnings=execution.warnings,
        )

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
        summary=completion.answer.strip(),
        retrieval_mode=resolved_mode,
        retrieval_warnings=execution.warnings,
    )


def synthesize_answer(
    question: str, context: list[Chunk], mcp_servers: list[dict[str, str]]
) -> str:
    """Render a readable answer from retrieved context and MCP discovery hints."""

    if not context:
        return _no_evidence_message(question)

    lines = [
        f"Question: {question}",
        "",
        "Answer:",
        _compose_answer_summary(question, context),
        "",
        "Evidence:",
    ]
    for chunk in context:
        lines.append(f"- {chunk.source}: {_chunk_preview(chunk)}")
    if mcp_servers:
        lines.append("")
        lines.append("Discovered MCP candidates:")
        for server in mcp_servers:
            lines.append(f"- {server['path']}: {server['hint']}")
    return "\n".join(lines)


def _no_evidence_message(question: str) -> str:
    """Return the user-facing no-evidence response used by baseline and live paths."""

    return (
        f"No repository evidence matched the question: {question!r}. "
        "Add more documentation, code, or examples before evaluating RAG quality."
    )


def _relative_source_path(path: Path, *, root: Path) -> str:
    """Return ``path`` relative to ``root`` when possible."""

    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def serialize_chunk(chunk: Chunk, *, root: Path) -> dict[str, str]:
    """Serialize a retrieved chunk for machine-readable CLI and worker output."""

    return {
        "source": _relative_source_path(chunk.source, root=root),
        "preview": _chunk_preview(chunk),
        "text": chunk.text,
    }


def _chunk_preview(chunk: Chunk) -> str:
    """Return the short preview used in baseline and live-answer prompts."""

    return _truncate_text(" ".join(chunk.text.split()), max_chars=240)


def _answer_preview(chunk: Chunk) -> str:
    """Return a shorter chunk preview used by the baseline answer summary."""

    return _truncate_text(_clean_preview_text(chunk.text), max_chars=160)


def _clean_preview_text(text: str) -> str:
    """Normalize chunk text into a compact, citation-friendly preview string."""

    cleaned = " ".join(text.split())
    return cleaned.lstrip("#*-|> ").strip()


def _truncate_text(text: str, *, max_chars: int) -> str:
    """Return ``text`` clipped to ``max_chars`` without splitting the trailing word."""

    if len(text) <= max_chars:
        return text
    clipped = text[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{clipped}..."


def _normalize_text_tokens(text: str) -> str:
    """Return ``text`` normalized to lowercase repository-token words."""

    return " ".join(TOKEN_RE.findall(text.lower()))


def _question_focus_terms(question: str) -> list[str]:
    """Return the content-bearing terms that should guide answer synthesis."""

    terms = list(TOKEN_RE.findall(question.lower()))
    focus_terms = [term for term in terms if term not in QUESTION_FILLER_TERMS]
    return focus_terms if focus_terms else terms


def _question_focus_phrases(focus_terms: list[str]) -> tuple[str, ...]:
    """Return short multi-term phrases derived from the question focus terms."""

    phrases = [
        " ".join(focus_terms[index : index + 2])
        for index in range(len(focus_terms) - 1)
        if len(focus_terms[index : index + 2]) == 2
    ]
    return tuple(dict.fromkeys(phrases))


def _answer_focus_score(question: str, chunk: Chunk) -> float:
    """Score how directly a retrieved chunk answers ``question``."""

    focus_terms = _question_focus_terms(question)
    focus_term_set = set(focus_terms)
    normalized_text = _normalize_text_tokens(chunk.text)
    text_terms = set(normalized_text.split())
    score = float(len(text_terms.intersection(focus_terms)))

    for phrase in _question_focus_phrases(focus_terms):
        if phrase in normalized_text:
            score += 1.0

    lower_text = chunk.text.lower()
    if question.lower().startswith("what is "):
        phrase = " ".join(focus_terms)
        if phrase and (f"{phrase} is" in normalized_text or f"{phrase}:" in normalized_text):
            score += 2.0

    raw_terms = TOKEN_RE.findall(question)
    score += 1.5 * sum(
        1 for term in raw_terms if ("_" in term or "-" in term) and term.lower() in normalized_text
    )
    if chunk.source.suffix == ".md":
        score += 0.5
    if "documentation" in chunk.source.parts or "docs" in chunk.source.parts:
        score += 0.5
    if chunk.source.parts == ("README.md",) and {"repository", "research"}.issubset(focus_term_set):
        score += 2.0
    if "tools" in chunk.source.parts:
        score -= 0.75
    if chunk.text.count('",') >= 3:
        score -= 2.0
    score -= lower_text.count("?") * 1.25
    if any(marker in lower_text for marker in QUESTION_LIST_PENALTY_MARKERS):
        score -= 3.0

    return score


def _select_answer_highlights(
    question: str, context: list[Chunk], *, limit: int = 2
) -> list[Chunk]:
    """Choose the retrieved chunks that should anchor the readable answer summary."""

    ranked = sorted(
        enumerate(context),
        key=lambda item: (-_answer_focus_score(question, item[1]), item[0]),
    )
    return [chunk for _, chunk in ranked[:limit]]


def _compose_answer_summary(question: str, context: list[Chunk]) -> str:
    """Compose the explicit ``Answer:`` paragraph for the baseline workflow."""

    highlights = _select_answer_highlights(question, context)
    primary = highlights[0]
    summary_parts = [f"`{primary.source.as_posix()}` says {_answer_preview(primary)!r}."]

    if len(highlights) > 1:
        support = highlights[1]
        summary_parts.append(
            f"Supporting evidence from `{support.source.as_posix()}` adds"
            f" {_answer_preview(support)!r}."
        )

    remaining_sources = list(
        dict.fromkeys(
            f"`{chunk.source.as_posix()}`" for chunk in context if chunk not in set(highlights)
        )
    )
    if remaining_sources:
        summary_parts.append(
            f"Additional retrieved context appears in {', '.join(remaining_sources)}."
        )

    return " ".join(summary_parts)


def _retrieve_from_documents(
    question: str,
    documents: list[RepoDocument],
    *,
    root: Path,
    top_k: int,
    profile: RetrievalProfile,
    retrieval_mode: RetrievalMode,
) -> RetrievalExecution:
    """Chunk ``documents`` and retrieve the most relevant context."""

    chunks = chunk_documents(documents)
    return retrieve_with_metadata(
        question,
        chunks,
        top_k=top_k,
        profile=profile,
        retrieval_mode=retrieval_mode,
        root=root,
    )


def _resolve_retrieval_profile(
    root: Path,
    *,
    retrieval_mode: RetrievalMode | None = None,
    profile: RetrievalProfile | None = None,
) -> tuple[RetrievalProfile, RetrievalMode]:
    resolved_profile = profile if profile is not None else load_retrieval_profile(root)
    return resolved_profile, resolve_retrieval_mode(resolved_profile, retrieval_mode)


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
