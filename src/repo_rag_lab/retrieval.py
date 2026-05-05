"""Baseline chunking and lexical retrieval utilities for repository text."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import cache
from itertools import pairwise
from pathlib import Path
from typing import Literal, cast

from .corpus import RepoDocument
from .retrieval_profile import (
    DEFAULT_RETRIEVAL_PROFILE,
    SUPPORTED_RETRIEVAL_MODES,
    RetrievalProfile,
)
from .semantic_retrieval import rank_semantic_chunks

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
QUESTION_TEST_SEEKING_TERMS = {
    "bdd",
    "coverage",
    "integration",
    "pytest",
    "test",
    "tests",
    "unit",
}
QUESTION_TRAINING_SEEKING_TERMS = {
    "dataset",
    "datasets",
    "example",
    "examples",
    "fewshot",
    "sample",
    "samples",
    "train",
    "training",
}
QUESTION_AUDIT_SEEKING_TERMS = {
    "audit",
    "audits",
    "ci",
    "evidence",
    "health",
    "log",
    "logs",
    "probe",
    "probes",
    "status",
    "verification",
    "verify",
}
RetrievalMode = Literal["lexical", "idf-rerank", "vector", "hybrid-vector"]
_HYBRID_RRF_K = 40.0
_HYBRID_LEXICAL_WEIGHT = 0.45
_HYBRID_SEMANTIC_WEIGHT = 0.75
_SEMANTIC_CANDIDATE_MULTIPLIER = 2


@dataclass(frozen=True)
class Chunk:
    """A retrievable slice of repository text tied to its source path."""

    source: Path
    text: str


@dataclass(frozen=True)
class RetrievalExecution:
    """Describe one retrieval pass including the effective mode and warnings."""

    chunks: tuple[Chunk, ...]
    retrieval_mode: RetrievalMode
    warnings: tuple[str, ...] = ()


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


def retrieve(
    question: str,
    chunks: list[Chunk],
    top_k: int = 4,
    *,
    profile: RetrievalProfile = DEFAULT_RETRIEVAL_PROFILE,
    retrieval_mode: RetrievalMode | None = None,
    root: Path | None = None,
) -> list[Chunk]:
    """Return the highest-scoring chunks for ``question``."""

    return list(
        retrieve_with_metadata(
            question,
            chunks,
            top_k=top_k,
            profile=profile,
            retrieval_mode=retrieval_mode,
            root=root,
        ).chunks
    )


def retrieve_with_metadata(
    question: str,
    chunks: list[Chunk],
    top_k: int = 4,
    *,
    profile: RetrievalProfile = DEFAULT_RETRIEVAL_PROFILE,
    retrieval_mode: RetrievalMode | None = None,
    root: Path | None = None,
) -> RetrievalExecution:
    """Return retrieved chunks plus the effective retrieval mode and fallback warnings."""

    resolved_mode = resolve_retrieval_mode(profile, retrieval_mode)
    eligible_chunks = [chunk for chunk in chunks if not profile.excludes(chunk.source)]
    lexical_scored = _score_chunks(question, eligible_chunks, profile=profile)

    if resolved_mode == "lexical":
        ranked = [chunk for value, chunk in lexical_scored if value > 0]
        return RetrievalExecution(
            chunks=tuple(_select_diverse_chunks(ranked, top_k=top_k)),
            retrieval_mode="lexical",
        )

    lexical_ranked = _rerank_chunks(
        question,
        lexical_scored,
        top_k=top_k,
        candidate_pool_size=profile.rerank_candidate_pool_size,
        profile=profile,
    )
    if resolved_mode == "idf-rerank":
        return RetrievalExecution(
            chunks=tuple(_select_diverse_chunks(lexical_ranked, top_k=top_k)),
            retrieval_mode="idf-rerank",
        )

    semantic_rankings, semantic_warnings = rank_semantic_chunks(
        question,
        root=root.resolve() if root is not None else Path.cwd(),
        chunk_records=[
            (_semantic_source_key(chunk.source, root=root), chunk.text) for chunk in eligible_chunks
        ],
        max_candidates=max(
            top_k, profile.rerank_candidate_pool_size * _SEMANTIC_CANDIDATE_MULTIPLIER
        ),
    )
    if not semantic_rankings:
        fallback_ranked = lexical_ranked
        warnings = tuple(
            [
                *semantic_warnings,
                "Semantic retrieval fell back to idf-rerank.",
            ]
        )
        return RetrievalExecution(
            chunks=tuple(_select_diverse_chunks(fallback_ranked, top_k=top_k)),
            retrieval_mode="idf-rerank",
            warnings=warnings,
        )

    semantic_ranked_chunks = [eligible_chunks[index] for index, _ in semantic_rankings]
    if resolved_mode == "vector":
        return RetrievalExecution(
            chunks=tuple(_select_diverse_chunks(semantic_ranked_chunks, top_k=top_k)),
            retrieval_mode="vector",
            warnings=tuple(semantic_warnings),
        )

    hybrid_ranked = _hybrid_ranked_chunks(
        lexical_ranked=lexical_ranked,
        semantic_rankings=semantic_rankings,
        semantic_chunks=eligible_chunks,
        top_k=top_k,
        candidate_pool_size=profile.rerank_candidate_pool_size,
    )
    return RetrievalExecution(
        chunks=tuple(_select_diverse_chunks(hybrid_ranked, top_k=top_k)),
        retrieval_mode="hybrid-vector",
        warnings=tuple(semantic_warnings),
    )


def resolve_retrieval_mode(
    profile: RetrievalProfile,
    retrieval_mode: RetrievalMode | None = None,
) -> RetrievalMode:
    """Return the active retrieval mode, preferring explicit overrides over profile defaults."""

    selected_mode = retrieval_mode if retrieval_mode is not None else profile.retrieval_mode
    if selected_mode not in SUPPORTED_RETRIEVAL_MODES:
        supported = ", ".join(sorted(SUPPORTED_RETRIEVAL_MODES))
        raise ValueError(
            f"Unsupported retrieval mode `{selected_mode}`. Expected one of: {supported}"
        )
    return cast(RetrievalMode, selected_mode)


def _score_chunks(
    question: str,
    chunks: list[Chunk],
    *,
    profile: RetrievalProfile,
) -> list[tuple[float, Chunk]]:
    return sorted(
        [
            (score(question, chunk.text, source=chunk.source, profile=profile), chunk)
            for chunk in chunks
        ],
        key=lambda item: item[0],
        reverse=True,
    )


def _select_diverse_chunks(ranked: list[Chunk], *, top_k: int) -> list[Chunk]:
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


def _semantic_source_key(source: Path, *, root: Path | None) -> str:
    if root is None:
        return source.as_posix()
    try:
        return source.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return source.as_posix()


def _hybrid_ranked_chunks(
    *,
    lexical_ranked: list[Chunk],
    semantic_rankings: list[tuple[int, float]],
    semantic_chunks: list[Chunk],
    top_k: int,
    candidate_pool_size: int,
) -> list[Chunk]:
    lexical_pool = lexical_ranked[: max(top_k, candidate_pool_size)]
    semantic_pool = [
        semantic_chunks[index] for index, _ in semantic_rankings[: max(top_k, candidate_pool_size)]
    ]
    lexical_positions = {chunk: position for position, chunk in enumerate(lexical_pool, start=1)}
    semantic_positions = {chunk: position for position, chunk in enumerate(semantic_pool, start=1)}
    semantic_scores = {
        semantic_chunks[index]: value
        for index, value in semantic_rankings[: max(top_k, candidate_pool_size)]
    }
    candidates = {
        *lexical_pool,
        *semantic_pool,
    }
    if not candidates:
        return []

    def _rrf(position: int, *, weight: float) -> float:
        return weight / (_HYBRID_RRF_K + position)

    return sorted(
        candidates,
        key=lambda chunk: (
            (
                _rrf(lexical_positions[chunk], weight=_HYBRID_LEXICAL_WEIGHT)
                if chunk in lexical_positions
                else 0.0
            )
            + (
                _rrf(semantic_positions[chunk], weight=_HYBRID_SEMANTIC_WEIGHT)
                if chunk in semantic_positions
                else 0.0
            )
            + (semantic_scores.get(chunk, 0.0) * 0.05)
        ),
        reverse=True,
    )


def _rerank_chunks(
    question: str,
    scored_chunks: list[tuple[float, Chunk]],
    *,
    top_k: int,
    candidate_pool_size: int,
    profile: RetrievalProfile = DEFAULT_RETRIEVAL_PROFILE,
) -> list[Chunk]:
    """Return an IDF-aware reranking across the strongest lexical candidates."""

    positive_candidates = [(value, chunk) for value, chunk in scored_chunks if value > 0]
    if not positive_candidates:
        return []

    question_terms = _query_content_terms(_normalized_terms(question))
    if not question_terms:
        return [chunk for _, chunk in positive_candidates]

    pool_size = min(len(positive_candidates), max(top_k, candidate_pool_size))
    candidate_pool = positive_candidates[:pool_size]
    idf_by_term = _candidate_idf(candidate_pool)
    reranked_pool = sorted(
        candidate_pool,
        key=lambda item: _rerank_score(question_terms, item, idf_by_term, profile=profile),
        reverse=True,
    )
    return [
        *[chunk for _, chunk in reranked_pool],
        *[chunk for _, chunk in positive_candidates[pool_size:]],
    ]


def _candidate_idf(candidate_pool: list[tuple[float, Chunk]]) -> dict[str, float]:
    """Return lightweight IDF weights over the current rerank candidate pool."""

    candidate_count = len(candidate_pool)
    document_frequencies: Counter[str] = Counter()
    for _, chunk in candidate_pool:
        document_terms = set(_normalized_terms(chunk.text))
        document_terms.update(_normalized_terms(_scoring_source_path(chunk.source).as_posix()))
        for term in document_terms:
            document_frequencies[term] += 1
    return {
        term: math.log(1.0 + ((candidate_count + 1.0) / (frequency + 1.0))) + 1.0
        for term, frequency in document_frequencies.items()
    }


def _rerank_score(
    question_terms: list[str],
    candidate: tuple[float, Chunk],
    idf_by_term: dict[str, float],
    *,
    profile: RetrievalProfile,
) -> float:
    """Return a second-stage reranking score on top of the lexical baseline."""

    base_score, chunk = candidate
    text_terms = _normalized_terms(chunk.text)
    if not text_terms:
        return 0.0
    scoring_source = _scoring_source_path(chunk.source)
    path_terms = _normalized_terms(scoring_source.as_posix())
    unique_question_terms = list(dict.fromkeys(question_terms))
    if not unique_question_terms:
        return 0.0

    matched_terms = set(unique_question_terms).intersection(text_terms)
    path_matches = set(unique_question_terms).intersection(path_terms)
    mean_idf_overlap = (
        sum(idf_by_term.get(term, 1.0) for term in matched_terms) / len(matched_terms)
        if matched_terms
        else 0.0
    )
    mean_path_idf_overlap = (
        sum(idf_by_term.get(term, 1.0) for term in path_matches) / len(path_matches)
        if path_matches
        else 0.0
    )
    coverage = len(matched_terms) / len(set(unique_question_terms))
    question_bigrams = _ordered_bigrams(unique_question_terms)
    text_bigram_matches = len(question_bigrams.intersection(_ordered_bigrams(text_terms)))
    path_bigram_matches = len(question_bigrams.intersection(_ordered_bigrams(path_terms)))
    phrase_bonus = 0.8 if _contains_term_sequence(text_terms, unique_question_terms) else 0.0
    path_phrase_bonus = 0.25 if _contains_term_sequence(path_terms, unique_question_terms) else 0.0
    leading_term_bonus = 0.15 if unique_question_terms[0] in text_terms[:24] else 0.0
    return (
        base_score
        + (mean_idf_overlap * 0.35)
        + (mean_path_idf_overlap * 0.1)
        + (coverage * 0.9)
        + (text_bigram_matches * 0.8)
        + (path_bigram_matches * 0.2)
        + phrase_bonus
        + path_phrase_bonus
        + leading_term_bonus
    )


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


def _query_content_terms(question_terms: list[str]) -> list[str]:
    """Return content-bearing question terms, falling back to all terms when needed."""

    content_terms = [term for term in question_terms if term not in QUESTION_FILLER_TERMS]
    return content_terms if content_terms else question_terms


def _ordered_bigrams(terms: list[str]) -> set[tuple[str, str]]:
    """Return unique adjacent bigrams from ``terms``."""

    return set(pairwise(terms))


def _contains_term_sequence(haystack: list[str], needle: list[str]) -> bool:
    """Return ``True`` when ``needle`` appears contiguously inside ``haystack``."""

    if not needle or len(needle) > len(haystack):
        return False
    needle_length = len(needle)
    for index in range(len(haystack) - needle_length + 1):
        if haystack[index : index + needle_length] == needle:
            return True
    return False


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


@cache
def _scoring_source_path(source: Path) -> Path:
    """Return a repository-relative path for scoring heuristics when possible."""

    if not source.is_absolute():
        return source
    for candidate in (source.parent, *source.parents):
        if _looks_like_scoring_repository_root(candidate):
            try:
                return source.relative_to(candidate)
            except ValueError:
                continue
    return source


@cache
def _looks_like_scoring_repository_root(path: Path) -> bool:
    """Return ``True`` when ``path`` looks like the selected repository root for scoring."""

    if _looks_like_repository_root(path):
        return True
    return (
        path.joinpath("README.md").is_file()
        and path.joinpath("src").is_dir()
        and (path.joinpath("docs").is_dir() or path.joinpath("include").is_dir())
    )


def _question_is_document_seeking(question_terms: list[str]) -> bool:
    """Return ``True`` when question terms imply "where/how do I read this?" intent."""

    return bool(set(question_terms).intersection(QUESTION_DOCUMENT_SEEKING_TERMS))


def _question_is_code_seeking(question_terms: list[str]) -> bool:
    """Return ``True`` when question terms imply implementation or API lookup intent."""

    return bool(set(question_terms).intersection(QUESTION_CODE_SEEKING_TERMS))


def _question_is_audit_seeking(question_terms: list[str]) -> bool:
    """Return ``True`` when question terms explicitly seek audit or verification evidence."""

    return bool(set(question_terms).intersection(QUESTION_AUDIT_SEEKING_TERMS))


def _question_is_test_seeking(question_terms: list[str]) -> bool:
    """Return ``True`` when question terms explicitly seek tests or pytest surfaces."""

    return bool(set(question_terms).intersection(QUESTION_TEST_SEEKING_TERMS))


def _question_is_training_seeking(question_terms: list[str]) -> bool:
    """Return ``True`` when question terms explicitly seek training examples or sample data."""

    return bool(set(question_terms).intersection(QUESTION_TRAINING_SEEKING_TERMS))


def _definition_bonus(question: str, text: str, *, profile: RetrievalProfile) -> float:
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
    return profile.definition_pattern_bonus if f"{phrase} is" in normalized_text else 0.0


def _question_echo_penalty(question: str, text: str, *, profile: RetrievalProfile) -> float:
    """Return a penalty when a chunk mostly repeats the question instead of answering it."""

    normalized_question = _normalized_token_string(question)
    if not normalized_question:
        return 0.0
    normalized_text = _normalized_token_string(text)
    return profile.question_echo_penalty if normalized_question in normalized_text else 0.0


def source_score_adjustment(
    source: Path,
    question_terms: list[str],
    *,
    profile: RetrievalProfile = DEFAULT_RETRIEVAL_PROFILE,
) -> float:
    """Return a path-aware score adjustment for ``source`` and ``question_terms``."""

    scoring_source = _scoring_source_path(source)
    adjustment = profile.source_adjustments_by_name.get(scoring_source.name, 0.0)
    for part in scoring_source.parts:
        adjustment += profile.source_adjustments_by_part.get(part, 0.0)

    for subpath_rule in profile.subpath_adjustments:
        if _contains_path_parts(scoring_source, subpath_rule.path):
            adjustment += subpath_rule.value

    path_terms = {
        _normalize_term(term) for term in TOKEN_RE.findall(scoring_source.as_posix().lower())
    }
    adjustment += profile.path_term_overlap_bonus * len(
        set(question_terms).intersection(path_terms)
    )

    if {"repository", "research"}.issubset(question_terms):
        if _is_root_readme(scoring_source):
            adjustment += 2.5
        elif _contains_path_parts(scoring_source, ("src", "repo_rag_lab")):
            if scoring_source.name == "utilities.py":
                adjustment += 0.8
        elif _contains_path_parts(scoring_source, ("docs", "operations")) or _contains_path_parts(
            scoring_source,
            ("docs", "architecture", "inspired"),
        ):
            adjustment -= 1.5
        elif scoring_source.suffix.lower() in {".py", ".rs"} and not _question_is_code_seeking(
            question_terms
        ):
            adjustment -= 1.0
    if scoring_source.name == "AGENTS.md":
        if _has_term_prefix(question_terms, "agent"):
            adjustment += 0.6
        else:
            adjustment -= 1.4
    if _contains_path_parts(scoring_source, ("docs", "audit")) and not _question_is_audit_seeking(
        question_terms
    ):
        adjustment -= 3.0
    if "tests" in scoring_source.parts and not _question_is_test_seeking(question_terms):
        adjustment -= 5.0
    if _contains_path_parts(
        scoring_source,
        ("samples", "training"),
    ) and not _question_is_training_seeking(question_terms):
        adjustment -= 3.0

    for rule in profile.contextual_rules:
        if rule.path_name is not None and scoring_source.name != rule.path_name:
            continue
        if rule.subpath is not None and not _contains_path_parts(scoring_source, rule.subpath):
            continue
        if rule.required_terms and not rule.required_terms.issubset(question_terms):
            continue
        if rule.required_term_prefix is not None and not _has_term_prefix(
            question_terms, rule.required_term_prefix
        ):
            continue
        adjustment += rule.value

    if _question_is_document_seeking(question_terms):
        if _is_markdown_source(scoring_source):
            adjustment += profile.document_seeking_markdown_bonus
        if "docs" in scoring_source.parts:
            adjustment += profile.document_seeking_documentation_bonus
        if scoring_source.name == "README.md":
            adjustment += profile.document_seeking_readme_bonus
    if _question_is_code_seeking(question_terms) and scoring_source.suffix.lower() in {
        ".c",
        ".h",
        ".py",
        ".rs",
    }:
        adjustment += profile.code_seeking_source_bonus

    return adjustment


def score(
    question: str,
    text: str,
    *,
    source: Path | None = None,
    profile: RetrievalProfile = DEFAULT_RETRIEVAL_PROFILE,
) -> float:
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
    path_adjustment = (
        source_score_adjustment(source, q_terms, profile=profile) if source is not None else 0.0
    )
    definition_bonus = _definition_bonus(question, text, profile=profile)
    question_echo_penalty = _question_echo_penalty(question, text, profile=profile)
    return (
        overlap
        + (unique_overlap * 0.4)
        + density
        + path_adjustment
        + definition_bonus
        - question_echo_penalty
    )
