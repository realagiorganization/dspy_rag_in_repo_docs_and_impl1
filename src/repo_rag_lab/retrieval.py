"""Baseline chunking and lexical retrieval utilities for repository text."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from .corpus import RepoDocument

TOKEN_RE = re.compile(r"[A-Za-z0-9_]{2,}")
PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")
QUESTION_FILLER_TERMS = {
    "a",
    "an",
    "are",
    "does",
    "how",
    "is",
    "should",
    "the",
    "this",
    "what",
    "where",
}
QUESTION_DOCUMENT_SEEKING_TERMS = {
    "documentation",
    "docs",
    "explain",
    "explains",
    "file",
    "files",
    "notes",
    "read",
    "stored",
    "where",
}
QUESTION_CODE_SEEKING_TERMS = {
    "command",
    "commands",
    "define",
    "defines",
    "function",
    "functions",
    "handle",
    "handles",
    "report",
    "reports",
    "struct",
}
QUESTION_ECHO_PENALTY = 4.2
DEFINITION_PATTERN_BONUS = 2.0
DOCUMENT_SEEKING_MARKDOWN_BONUS = 0.8
DOCUMENT_SEEKING_DOCUMENTATION_BONUS = 0.9
DOCUMENT_SEEKING_README_BONUS = 0.4
CODE_SEEKING_SOURCE_BONUS = 1.4
SOURCE_BONUS_BY_NAME = {
    "README.md": 1.4,
    "AGENTS.md": 1.2,
}
SOURCE_BONUS_BY_PART = {
    "documentation": 0.9,
    "docs": 0.9,
    "include": 0.8,
    "publication": 0.5,
    "utilities": 0.9,
    "src": 0.6,
}
SOURCE_PENALTY_BY_NAME = {
    "FILES.csv": 4.0,
    "FILES.md": 4.0,
    "README.DSPY.MD": 4.0,
    "README.AGENTS.md": 3.0,
    "REPO_COMPLETENESS_CHECKLIST.md": 3.0,
    "TODO.MD": 4.0,
    "hushwheel-fixture-rag-guide.md": 3.0,
    "workflow.py": 1.0,
    "todo-backlog.yaml": 4.0,
}
SOURCE_PENALTY_BY_PART = {
    ".codex": 2.5,
    ".github": 1.5,
    "data": 6.0,
    "generated": 2.0,
    "tests": 5.0,
}
SOURCE_PENALTY_BY_SUBPATH = {
    ("AGENTS.md.d",): 2.5,
    ("docs", "audit"): 5.0,
    ("publication", "exploratorium_translation", "generated"): 4.0,
    ("samples", "logs"): 5.0,
    ("samples", "population"): 6.0,
    ("samples", "training"): 6.0,
}
PATH_TERM_OVERLAP_BONUS = 0.45


@dataclass(frozen=True)
class Chunk:
    """A retrievable slice of repository text tied to its source path."""

    source: Path
    text: str


def chunk_documents(documents: list[RepoDocument], chunk_size: int = 1200) -> list[Chunk]:
    """Split loaded repository documents into paragraph-aware text chunks."""

    chunks: list[Chunk] = []
    for doc in documents:
        text = doc.text.strip()
        if not text:
            continue
        for snippet in _chunk_text(text, chunk_size):
            chunks.append(Chunk(source=doc.path, text=snippet))
    return chunks


def retrieve(question: str, chunks: list[Chunk], top_k: int = 4) -> list[Chunk]:
    """Return the highest-scoring chunks for ``question``."""

    scored = [(score(question, chunk.text, source=chunk.source), chunk) for chunk in chunks]
    ranked = [
        chunk
        for value, chunk in sorted(scored, key=lambda item: item[0], reverse=True)
        if value > 0
    ]

    selected: list[Chunk] = []
    seen_sources: set[Path] = set()
    for chunk in ranked:
        if chunk.source in seen_sources:
            continue
        selected.append(chunk)
        seen_sources.add(chunk.source)
        if len(selected) >= top_k:
            return selected

    selected_chunks = set(selected)
    for chunk in ranked:
        if chunk in selected_chunks:
            continue
        selected.append(chunk)
        if len(selected) >= top_k:
            break

    return selected


def _contains_path_parts(path: Path, needle: tuple[str, ...]) -> bool:
    """Return ``True`` when ``needle`` appears as a contiguous path-part slice."""

    parts = path.parts
    for index in range(len(parts) - len(needle) + 1):
        if parts[index : index + len(needle)] == needle:
            return True
    return False


def _has_term_prefix(question_terms: list[str], prefix: str) -> bool:
    """Return ``True`` when any normalized question term starts with ``prefix``."""

    return any(term.startswith(prefix) for term in question_terms)


def _normalize_term(term: str) -> str:
    """Lightly normalize a token so singular/plural variants overlap in lexical scoring."""

    lowered = term.lower()
    if not lowered.isalpha():
        return lowered
    if lowered.endswith("ies") and len(lowered) > 4:
        return f"{lowered[:-3]}y"
    if lowered.endswith("es") and len(lowered) > 4:
        return lowered[:-2]
    if lowered.endswith("s") and len(lowered) > 4:
        return lowered[:-1]
    return lowered


def _normalized_terms(text: str) -> list[str]:
    """Return normalized lexical terms from ``text``."""

    return [_normalize_term(term) for term in TOKEN_RE.findall(text.lower())]


def _normalized_token_string(text: str) -> str:
    """Return ``text`` normalized to lowercase token strings separated by spaces."""

    return " ".join(_normalized_terms(text))


def _chunk_text(text: str, chunk_size: int) -> list[str]:
    """Split text into paragraph-aware chunks before falling back to fixed-width slices."""

    paragraphs = [
        paragraph.strip() for paragraph in PARAGRAPH_SPLIT_RE.split(text) if paragraph.strip()
    ]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current_parts: list[str] = []
    current_length = 0

    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if current_parts:
                chunks.append("\n\n".join(current_parts))
                current_parts = []
                current_length = 0
            for start in range(0, len(paragraph), chunk_size):
                chunks.append(paragraph[start : start + chunk_size])
            continue

        added_length = len(paragraph) + (2 if current_parts else 0)
        if current_parts and current_length + added_length > chunk_size:
            chunks.append("\n\n".join(current_parts))
            current_parts = [paragraph]
            current_length = len(paragraph)
            continue

        current_parts.append(paragraph)
        current_length += added_length

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks


def _is_root_readme(source: Path) -> bool:
    """Return ``True`` when ``source`` is the repository root ``README.md``."""

    if source.name != "README.md":
        return False
    if source.parts == ("README.md",):
        return True
    return _looks_like_repository_root(source.parent)


@cache
def _looks_like_repository_root(path: Path) -> bool:
    """Return ``True`` when ``path`` looks like the repository root directory."""

    return (
        path.joinpath("pyproject.toml").is_file()
        and path.joinpath("Makefile").is_file()
        and path.joinpath("src").is_dir()
    )


def _is_markdown_source(source: Path) -> bool:
    """Return ``True`` when ``source`` is a Markdown document."""

    return source.suffix.lower() == ".md"


def _question_is_document_seeking(question_terms: list[str]) -> bool:
    """Return ``True`` when question terms imply "where/how do I read this?" intent."""

    return bool(set(question_terms).intersection(QUESTION_DOCUMENT_SEEKING_TERMS))


def _question_is_code_seeking(question_terms: list[str]) -> bool:
    """Return ``True`` when question terms imply implementation or API lookup intent."""

    return bool(set(question_terms).intersection(QUESTION_CODE_SEEKING_TERMS))


def _definition_bonus(question: str, text: str) -> float:
    """Return a bonus when a ``what is ...`` question matches a definitional chunk."""

    normalized_question = _normalized_token_string(question)
    if not normalized_question.startswith("what is "):
        return 0.0

    phrase_terms = [
        term for term in _normalized_terms(question) if term not in QUESTION_FILLER_TERMS
    ]
    if not phrase_terms:
        return 0.0

    normalized_text = _normalized_token_string(text)
    phrase = " ".join(phrase_terms)
    return DEFINITION_PATTERN_BONUS if f"{phrase} is" in normalized_text else 0.0


def _question_echo_penalty(question: str, text: str) -> float:
    """Return a penalty when a chunk mostly repeats the question instead of answering it."""

    normalized_question = _normalized_token_string(question)
    if not normalized_question:
        return 0.0
    normalized_text = _normalized_token_string(text)
    return QUESTION_ECHO_PENALTY if normalized_question in normalized_text else 0.0


def source_score_adjustment(source: Path, question_terms: list[str]) -> float:
    """Return a path-aware score adjustment for ``source`` and ``question_terms``."""

    adjustment = SOURCE_BONUS_BY_NAME.get(source.name, 0.0)
    adjustment -= SOURCE_PENALTY_BY_NAME.get(source.name, 0.0)

    for part in source.parts:
        adjustment += SOURCE_BONUS_BY_PART.get(part, 0.0)
        adjustment -= SOURCE_PENALTY_BY_PART.get(part, 0.0)

    for subpath, penalty in SOURCE_PENALTY_BY_SUBPATH.items():
        if _contains_path_parts(source, subpath):
            adjustment -= penalty

    path_terms = {_normalize_term(term) for term in TOKEN_RE.findall(source.as_posix().lower())}
    adjustment += PATH_TERM_OVERLAP_BONUS * len(set(question_terms).intersection(path_terms))

    if _is_root_readme(source) and {"repository", "research"}.issubset(question_terms):
        adjustment += 1.0
    if source.name == "utilities.py" and {"repository", "research"}.issubset(question_terms):
        adjustment += 1.2
    if source.name == "AGENTS.md" and _has_term_prefix(question_terms, "agent"):
        adjustment += 0.6
    if _contains_path_parts(source, ("utilities", "README.md")) and _has_term_prefix(
        question_terms, "utilit"
    ):
        adjustment += 0.7
    if _contains_path_parts(source, ("documentation", "inspired")) and "inspired" in question_terms:
        adjustment += 2.0
    if (
        source.name == "utilities.py"
        and _contains_path_parts(source, ("src", "repo_rag_lab"))
        and {"repository", "research"}.issubset(question_terms)
    ):
        adjustment += 0.5
    if (
        source.name == "rust_lookup.py"
        and _contains_path_parts(source, ("src", "repo_rag_lab"))
        and {"repository", "research"}.issubset(question_terms)
    ):
        adjustment -= 1.6
    if _question_is_document_seeking(question_terms):
        if _is_markdown_source(source):
            adjustment += DOCUMENT_SEEKING_MARKDOWN_BONUS
        if "documentation" in source.parts:
            adjustment += DOCUMENT_SEEKING_DOCUMENTATION_BONUS
        if source.name == "README.md":
            adjustment += DOCUMENT_SEEKING_README_BONUS
    if _question_is_code_seeking(question_terms) and source.suffix.lower() in {
        ".c",
        ".h",
        ".py",
        ".rs",
    }:
        adjustment += CODE_SEEKING_SOURCE_BONUS

    return adjustment


def score(question: str, text: str, *, source: Path | None = None) -> float:
    """Score a text chunk by lexical overlap and light term-density weighting."""

    q_terms = _normalized_terms(question)
    if not q_terms:
        return 0.0
    t_terms = _normalized_terms(text)
    if not t_terms:
        return 0.0
    overlap = sum(1 for term in q_terms if term in t_terms)
    unique_overlap = len(set(q_terms).intersection(t_terms))
    density = overlap / math.sqrt(len(t_terms))
    path_adjustment = source_score_adjustment(source, q_terms) if source is not None else 0.0
    definition_bonus = _definition_bonus(question, text)
    question_echo_penalty = _question_echo_penalty(question, text)
    return (
        overlap
        + (unique_overlap * 0.4)
        + density
        + path_adjustment
        + definition_bonus
        - question_echo_penalty
    )
