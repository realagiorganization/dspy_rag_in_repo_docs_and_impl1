"""Helpers for loading and summarizing starter DSPy training examples."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml

from .runtime_artifacts import (
    DEFAULT_TRAINER_FAMILY_CACHE_DIR,
    DEFAULT_TRAINER_FAMILY_STATE_PATH,
    load_family_index_payload,
    load_json_object,
    resolve_family_index_path,
    upload_remote_family_state,
    write_family_index_payload,
)
from .term_extraction import extract_profile_terms, extract_tokens, select_profile_summary_terms


@dataclass(frozen=True)
class TrainingExample:
    """A normalized repository question-answer example."""

    question: str
    expected_answer: str
    tags: tuple[str, ...]
    expected_sources: tuple[str, ...] = ()
    benchmark_context: tuple[str, ...] = ()
    benchmark_context_sources: tuple[str, ...] = ()
    original_prompt: str = ""
    reformulated_prompt: str = ""
    command_trace: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class PromptFamilySupport:
    """Describe the best current prompt-family support for one prompt."""

    question: str
    prompt_family_id: str | None
    similarity: float
    band: str
    supported: bool
    family_father_question: str | None = None
    family_father_record: dict[str, Any] | None = None
    family_runtime_record: dict[str, Any] | None = None


TRAINER_CHAMPION_INDEX_SCHEMA_VERSION = 1
TRAINER_FAMILY_INDEX_KIND = "repo-rag-trainer-family-index"
TRAINER_CHAMPION_INDEX_KIND = TRAINER_FAMILY_INDEX_KIND
TRAINER_FAMILY_STATE_SCHEMA_VERSION = TRAINER_CHAMPION_INDEX_SCHEMA_VERSION
TRAINER_FAMILY_STATE_KIND = TRAINER_FAMILY_INDEX_KIND
PROMPT_FAMILY_MATCH_THRESHOLD = 0.8
TRAINER_IMPORTED_ANSWER_CHAR_BUDGET = 4000

_CODEX_TRANSCRIPT_BLOCK_PATTERN = re.compile(
    r"(?ms)^codex\n(.*?)(?=^(?:user|exec|apply patch|diff --git|web search|mcp)\b|"
    r"^tokens used\b|\Z)"
)
_CODEX_STDOUT_SECTION_PATTERN = re.compile(r"(?ms)\nSTDOUT:\n(.*?)(?:\nSTDERR:\n|\Z)")
_FORWARDED_DISCORD_TAIL_PATTERN = re.compile(r"(?is)\s*\[forwarded\]\s*@.*$")
_FAMILY_CACHE_TOKEN_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_TRAINER_SIGNAL_KINDS = {"full_trace", "feedback_trace"}
_SUCCESS_POSTERIOR_ALPHA_PRIOR = 1.0
_SUCCESS_POSTERIOR_BETA_PRIOR = 1.0
_SUCCESS_LOWER_BOUND_Z = 1.281552
_PATHLIKE_TOKEN_PATTERN = re.compile(
    r"(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+|[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+)"
)
_FAMILY_ROUTING_PROFILE_PRIMARY_WEIGHT = 1.45
_FAMILY_ROUTING_PROMPT_SUPPORT_WEIGHT = 0.15
_FAMILY_ROUTING_SUCCESS_BOOST = 0.2
_FAMILY_ROUTING_UNCERTAINTY_PENALTY = 0.05
_FAMILY_PROMPT_PROFILE_LIMIT = 12
_FAMILY_COMMAND_PROFILE_LIMIT = 16
_FAMILY_CONSTRAINT_PROFILE_LIMIT = 12
_FAMILY_PROFILE_MIN_COUNT = 2
_FAMILY_ROUTING_SHORTLIST_TOP_K = 20


def _coerce_int(value: object) -> int | None:
    """Return one best-effort integer conversion for optional scalar values."""

    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def _string_list(value: object) -> list[str]:
    """Return one list of normalized strings for sequence-like values."""

    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _normalize_trainer_signal_kind(value: object) -> str:
    """Return one normalized trainer-signal kind, defaulting to replay traces."""

    cleaned = str(value or "").strip()
    if cleaned in _TRAINER_SIGNAL_KINDS:
        return cleaned
    return "full_trace"


def _strip_forwarded_discord_tail(text: str) -> str:
    """Remove one Discord forwarding tail from a prompt-like string."""

    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    stripped = _FORWARDED_DISCORD_TAIL_PATTERN.sub("", cleaned).strip()
    return stripped or cleaned


def _strip_dataset_execution_envelope(text: object) -> str:
    """Remove worker-side execution scaffolding from one prompt-like string."""

    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    if "\nEXECUTION CONTEXT:" in cleaned:
        cleaned = cleaned.split("\nEXECUTION CONTEXT:", 1)[0].rstrip()
    elif "\nAUTONOMOUS EXECUTION CONTRACT:" in cleaned:
        cleaned = cleaned.split("\nAUTONOMOUS EXECUTION CONTRACT:", 1)[0].rstrip()
    if "Messages with required reaction:" in cleaned:
        cleaned = cleaned.split("Messages with required reaction:", 1)[1].strip()
    elif "Messages aggregated:" in cleaned and "\n\n" in cleaned:
        cleaned = cleaned.split("\n\n", 1)[1].strip()
    normalized_lines: list[str] = []
    skip_attachment_lines = False
    for raw_line in cleaned.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            skip_attachment_lines = False
            if normalized_lines and normalized_lines[-1] != "":
                normalized_lines.append("")
            continue
        if stripped == "Attachment locations:":
            skip_attachment_lines = True
            continue
        if skip_attachment_lines and stripped.startswith("- "):
            continue
        if stripped.startswith("Discord channel:"):
            continue
        if stripped.startswith("Channel ID:"):
            continue
        if stripped.startswith("Queue label:"):
            continue
        if stripped.startswith("Messages aggregated:"):
            continue
        if stripped.startswith("Available repository:"):
            continue
        if stripped.startswith("Repository checkout:"):
            continue
        if stripped.startswith("Attachment mount:"):
            continue
        if stripped.startswith("Attachments saved for execution"):
            continue
        if stripped.startswith("Attachments:"):
            continue
        if stripped.startswith("[") and ") " in stripped:
            prefix, separator, remainder = stripped.partition(") ")
            if separator and prefix.startswith("["):
                stripped = remainder.strip()
        normalized_lines.append(stripped)
    while normalized_lines and normalized_lines[-1] == "":
        normalized_lines.pop()
    result = _strip_forwarded_discord_tail("\n".join(normalized_lines).strip())
    fallback = _strip_forwarded_discord_tail(str(text or "").strip())
    return result or fallback


def _sanitize_family_cache_token(value: object, *, default: str) -> str:
    """Return a filesystem-safe cache token for one family-scoped path."""

    cleaned = "-".join(
        part for part in _FAMILY_CACHE_TOKEN_PATTERN.split(str(value or "").strip()) if part
    )
    return cleaned or default


def _family_state_dir(path: Path) -> Path:
    """Return the directory that owns one persisted family-state file."""

    return path.resolve().parent


def _family_cache_relative_dir(prompt_family_id: str) -> Path:
    """Return the relative local cache directory for one prompt family."""

    return Path("families") / _sanitize_family_cache_token(prompt_family_id, default="family")


def _resolve_family_state_member_path(
    family_state_path: Path,
    path_text: object,
) -> Path | None:
    """Resolve one thin-index member path relative to its owning family-state file."""

    cleaned = str(path_text or "").strip()
    if not cleaned:
        return None
    candidate = Path(cleaned)
    if candidate.is_absolute():
        return candidate
    return _family_state_dir(family_state_path) / candidate


def normalize_training_examples(records: list[dict[str, Any]]) -> list[TrainingExample]:
    """
    Normalize raw YAML records into immutable training examples.

    >>> examples = normalize_training_examples([
    ...     {
    ...         "question": " What is RAG? ",
    ...         "expected_answer": "Retrieval-Augmented Generation",
    ...         "tags": ["rag", "intro"],
    ...         "expected_sources": ["README.md"],
    ...     },
    ...     {"question": "Where are logs stored?", "expected_answer": "samples/logs"}
    ... ])
    >>> examples[0].question
    'What is RAG?'
    >>> examples[0].tags
    ('rag', 'intro')
    >>> examples[0].expected_sources
    ('README.md',)
    >>> examples[1].tags
    ()
    """

    normalized: list[TrainingExample] = []
    for record in records:
        tags = tuple(str(tag).strip() for tag in record.get("tags", []) if str(tag).strip())
        expected_sources = tuple(
            str(source).strip()
            for source in record.get("expected_sources", [])
            if str(source).strip()
        )
        benchmark_context = tuple(
            str(text).strip() for text in record.get("benchmark_context", []) if str(text).strip()
        )
        benchmark_context_sources = tuple(
            str(source).strip()
            for source in record.get("benchmark_context_sources", [])
            if str(source).strip()
        )
        original_prompt = _normalize_question_text(record.get("original_prompt"))
        reformulated_prompt = _normalize_question_text(record.get("reformulated_prompt"))
        command_trace = tuple(_ordered_unique_command_trace(record.get("command_trace", [])))
        normalized.append(
            TrainingExample(
                question=_normalize_question_text(record["question"]),
                expected_answer=str(record["expected_answer"]).strip(),
                tags=tags,
                expected_sources=expected_sources,
                benchmark_context=benchmark_context,
                benchmark_context_sources=benchmark_context_sources,
                original_prompt=original_prompt,
                reformulated_prompt=reformulated_prompt,
                command_trace=command_trace,
            )
        )
    return normalized


def batch_training_examples(
    examples: list[TrainingExample], batch_size: int = 2
) -> list[list[TrainingExample]]:
    """
    Group examples into notebook-friendly review batches.

    >>> items = normalize_training_examples([
    ...     {"question": "Q1", "expected_answer": "A1"},
    ...     {"question": "Q2", "expected_answer": "A2"},
    ...     {"question": "Q3", "expected_answer": "A3"},
    ... ])
    >>> [len(batch) for batch in batch_training_examples(items, batch_size=2)]
    [2, 1]
    """

    return [examples[index : index + batch_size] for index in range(0, len(examples), batch_size)]


def summarize_training_examples(examples: list[TrainingExample]) -> dict[str, Any]:
    """
    Produce a compact summary of the training set for notebook display.

    >>> summary = summarize_training_examples(normalize_training_examples([
    ...     {"question": "Q1", "expected_answer": "A1", "tags": ["repo"]},
    ...     {"question": "Q2", "expected_answer": "A2", "tags": ["repo", "mcp"]},
    ... ]))
    >>> summary["example_count"]
    2
    >>> summary["unique_tags"]
    ['mcp', 'repo']
    >>> summary["benchmark_count"]
    0
    """

    unique_tags = sorted({tag for example in examples for tag in example.tags})
    return {
        "example_count": len(examples),
        "benchmark_count": sum(
            1 for example in examples if example.expected_sources or example.benchmark_context
        ),
        "questions": [example.question for example in examples],
        "unique_tags": unique_tags,
    }


def validate_training_examples(
    examples: list[TrainingExample], root: Path | None = None
) -> list[str]:
    """
    Validate notebook training examples before using them for assertions.

    >>> issues = validate_training_examples([
    ...     TrainingExample(
    ...         question="Q",
    ...         expected_answer="A",
    ...         tags=("repo",),
    ...         expected_sources=("README.md",),
    ...     )
    ... ])
    >>> issues
    []
    """

    issues: list[str] = []
    seen_questions: set[str] = set()
    for index, example in enumerate(examples, start=1):
        if not example.question:
            issues.append(f"Example {index} is missing a question.")
        if not example.expected_answer:
            issues.append(f"Example {index} is missing an expected answer.")
        if len(set(example.tags)) != len(example.tags):
            issues.append(f"Example {index} has duplicate tags.")
        normalized_question = example.question.casefold()
        if normalized_question in seen_questions:
            issues.append(f"Example {index} duplicates an earlier question.")
        seen_questions.add(normalized_question)
        if root is None:
            continue
        for source in example.expected_sources:
            if Path(source).is_absolute():
                issues.append(f"Example {index} expected source must be relative: {source}")
                continue
            if not (root / source).exists():
                issues.append(f"Example {index} expected source does not exist: {source}")
        for source in example.benchmark_context_sources:
            if Path(source).is_absolute():
                issues.append(
                    f"Example {index} benchmark context source must be relative: {source}"
                )
    return issues


def load_training_examples(path: Path) -> list[TrainingExample]:
    """Load a YAML training set and normalize its records."""

    records = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return normalize_training_examples(records)


def _candidate_record_key(record: Mapping[str, Any]) -> tuple[str, str, tuple[str, ...], str]:
    """Return a stable deduplication key for one training-candidate record."""

    sources = tuple(
        sorted(
            str(source).strip()
            for source in record.get("expected_sources", [])
            if str(source).strip()
        )
    )
    return (
        _normalize_question_text(record.get("question")).casefold(),
        str(record.get("expected_answer") or "").strip().casefold(),
        sources,
        str(record.get("candidate_status") or "").strip().casefold(),
    )


def _candidate_question_key(record: Mapping[str, Any]) -> str:
    """Return the stable question-level identity for one training-candidate record."""

    return _normalize_question_text(record.get("question")).casefold()


def _candidate_record_hash(record: Mapping[str, Any]) -> str:
    """Return a compact stable identifier for one candidate-answer variant."""

    return f"cr-{_stable_hash(_candidate_record_key(record))}"


def _dedupe_tags(tags: Sequence[str]) -> list[str]:
    """Return tags in input order without duplicates or blanks."""

    seen: set[str] = set()
    deduped: list[str] = []
    for tag in tags:
        cleaned = str(tag).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def _looks_like_codex_cli_transcript(text: str) -> bool:
    """Return whether one imported answer looks like a raw Codex CLI transcript."""

    if not text:
        return False
    return (
        text.startswith("COMMAND: ")
        and "WORKING DIRECTORY:" in text
        and "STDOUT:" in text
        and "STDERR:" in text
    ) or (
        "OpenAI Codex v" in text
        and "\nuser\n" in text
        and ("\nexec\n" in text or "\napply patch\n" in text)
    )


def _normalize_training_answer_whitespace(text: str) -> str:
    """Collapse one answer into stable readable paragraph spacing."""

    normalized_lines = [line.rstrip() for line in text.replace("\r\n", "\n").splitlines()]
    collapsed: list[str] = []
    blank_pending = False
    for line in normalized_lines:
        stripped = line.strip()
        if not stripped:
            blank_pending = bool(collapsed)
            continue
        if blank_pending:
            collapsed.append("")
            blank_pending = False
        collapsed.append(stripped)
    return "\n".join(collapsed).strip()


def _clip_training_answer(text: str, budget: int = TRAINER_IMPORTED_ANSWER_CHAR_BUDGET) -> str:
    """Clamp one trainer answer to a bounded compile-friendly size."""

    if len(text) <= budget:
        return text
    clipped = text[:budget].rstrip()
    return f"{clipped}\n...[truncated for trainer budget]"


def _extract_codex_cli_transcript_answer(text: str) -> tuple[str, str]:
    """Extract the most training-useful assistant answer from one raw Codex transcript."""

    matches = [
        _normalize_training_answer_whitespace(match)
        for match in _CODEX_TRANSCRIPT_BLOCK_PATTERN.findall(text)
        if _normalize_training_answer_whitespace(match)
    ]
    if matches:
        return matches[-1], "codex-final-block"
    stdout_match = _CODEX_STDOUT_SECTION_PATTERN.search(text)
    if stdout_match is not None:
        stdout_text = _normalize_training_answer_whitespace(stdout_match.group(1))
        if stdout_text:
            return stdout_text, "stdout-section"
    return _normalize_training_answer_whitespace(text), "raw-fallback"


def _normalize_imported_training_answer(
    answer: object,
    response_text: object | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return one bounded trainer answer plus normalization metadata."""

    raw_answer = str(answer or "").strip()
    fallback_response = str(response_text or "").strip()
    source = "answer" if raw_answer else "response_text"
    candidate = raw_answer or fallback_response
    method = "raw"
    if _looks_like_codex_cli_transcript(candidate):
        candidate, method = _extract_codex_cli_transcript_answer(candidate)
    normalized = _clip_training_answer(_normalize_training_answer_whitespace(candidate))
    metadata: dict[str, Any] = {
        "source": source,
        "normalization_method": method,
        "raw_answer_length": len(raw_answer),
        "raw_response_text_length": len(fallback_response),
        "normalized_answer_length": len(normalized),
        "was_transcript": _looks_like_codex_cli_transcript(raw_answer or fallback_response),
        "was_truncated": len(normalized) < len(_normalize_training_answer_whitespace(candidate)),
    }
    return normalized, metadata


def _normalize_question_text(value: object) -> str:
    """Return a whitespace-normalized question string suitable for family grouping."""

    return " ".join(_strip_dataset_execution_envelope(value).split())


def _routing_question(
    *,
    question: object = "",
    original_prompt: object = "",
    reformulated_prompt: object = "",
) -> str:
    """Return the family-routing prompt surface, preferring the original prompt contract."""

    normalized_original = _normalize_question_text(original_prompt)
    if normalized_original:
        return normalized_original
    normalized_question = _normalize_question_text(question)
    if normalized_question:
        return normalized_question
    return _normalize_question_text(reformulated_prompt)


def _record_routing_question(record: Mapping[str, Any]) -> str:
    """Return the persisted routing prompt for one trainer-family record."""

    return _routing_question(
        question=record.get("question"),
        original_prompt=record.get("original_prompt"),
        reformulated_prompt=record.get("reformulated_prompt"),
    )


def _stable_hash(*parts: object) -> str:
    """Return a short stable hash for trainer-side lineage identifiers."""

    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _normalized_source_tokens(values: Sequence[str]) -> list[str]:
    """Return ordered, deduplicated source tokens for overlap checks."""

    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(str(value or "").strip().split())
        if not cleaned:
            continue
        token = cleaned.casefold()
        if token in seen:
            continue
        seen.add(token)
        ordered.append(cleaned)
    return ordered


def _evidence_preview_text(value: object) -> str:
    """Return a compact normalized preview string for evidence fingerprinting."""

    normalized = " ".join(str(value or "").strip().split())
    return normalized[:240]


def _evidence_fingerprint_tokens_from_rows(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return stable evidence-fingerprint tokens for serialized retrieved-context rows."""

    fingerprints: list[str] = []
    seen: set[str] = set()
    for row in rows:
        source = " ".join(str(row.get("source") or "").strip().split())
        preview = _evidence_preview_text(row.get("preview") or row.get("text"))
        if not source and not preview:
            continue
        token = f"ev-{_stable_hash(source.casefold(), preview.casefold())}"
        if token in seen:
            continue
        seen.add(token)
        fingerprints.append(token)
    return fingerprints


def _jaccard_similarity(left: Sequence[str], right: Sequence[str]) -> float:
    """Return a simple Jaccard overlap score between two ordered token collections."""

    left_set = {item.casefold() for item in left if str(item).strip()}
    right_set = {item.casefold() for item in right if str(item).strip()}
    if not left_set and not right_set:
        return 1.0
    if not left_set or not right_set:
        return 0.0
    intersection = left_set.intersection(right_set)
    union = left_set.union(right_set)
    if not union:
        return 0.0
    return len(intersection) / len(union)


def _profile_overlap_similarity(left: Sequence[str], right: Sequence[str]) -> float:
    """Return one profile overlap score that favors shared anchor terms."""

    left_set = {item.casefold() for item in left if str(item).strip()}
    right_set = {item.casefold() for item in right if str(item).strip()}
    if not left_set or not right_set:
        return 0.0
    intersection_size = len(left_set.intersection(right_set))
    if intersection_size <= 0:
        return 0.0
    coverage = intersection_size / min(len(left_set), len(right_set))
    return round(max(_jaccard_similarity(left, right), coverage), 6)


def _string_match_similarity(left: object, right: object) -> float:
    """Return ``1.0`` when normalized strings match, otherwise ``0.0``."""

    normalized_left = str(left or "").strip().casefold()
    normalized_right = str(right or "").strip().casefold()
    if not normalized_left and not normalized_right:
        return 1.0
    return 1.0 if normalized_left == normalized_right else 0.0


def _trace_context_snapshot(
    payload: Mapping[str, Any],
    trace_mapping: Mapping[str, Any],
    outcome_mapping: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the stable trainer-side context snapshot for one imported trace."""

    observed_sources = _normalized_source_tokens(
        [
            *(str(source).strip() for source in payload.get("sources", []) if str(source).strip()),
            *(
                str(source).strip()
                for source in trace_mapping.get("sources", [])
                if str(source).strip()
            ),
        ]
    )
    retrieval_mode = str(trace_mapping.get("retrieval_mode") or "").strip()
    mode = str(trace_mapping.get("mode") or "").strip()
    context_field = str(trace_mapping.get("context_field") or "").strip()
    evidence_rows = [
        row for row in payload.get("retrieved_context", []) if isinstance(row, Mapping)
    ]
    evidence_rows.extend(row for row in payload.get("context", []) if isinstance(row, Mapping))
    evidence_fingerprints = _normalized_source_tokens(
        [
            *_evidence_fingerprint_tokens_from_rows(evidence_rows),
            *(
                str(token).strip()
                for token in trace_mapping.get("evidence_fingerprints", [])
                if str(token).strip()
            ),
        ]
    )
    source_count = int(trace_mapping.get("source_count") or len(observed_sources) or 0)
    context_count = int(trace_mapping.get("context_count") or 0)
    top_k_raw = trace_mapping.get("top_k")
    top_k = int(top_k_raw) if isinstance(top_k_raw, int) else None
    command_trace = _ordered_unique_command_trace(
        [
            *_ordered_unique_command_trace(payload.get("command_trace")),
            *_ordered_unique_command_trace(trace_mapping.get("command_trace")),
        ]
    )
    original_prompt = _normalize_question_text(
        payload.get("original_prompt")
        or trace_mapping.get("original_prompt")
        or payload.get("question")
        or trace_mapping.get("question")
    )
    reformulated_prompt = _normalize_question_text(
        payload.get("reformulated_prompt")
        or trace_mapping.get("reformulated_prompt")
        or trace_mapping.get("question")
        or payload.get("question")
        or original_prompt
    )
    routing_question = _routing_question(
        question=payload.get("question") or trace_mapping.get("question"),
        original_prompt=original_prompt,
        reformulated_prompt=reformulated_prompt,
    )
    return {
        "question": routing_question or reformulated_prompt or original_prompt,
        "original_prompt": original_prompt,
        "reformulated_prompt": reformulated_prompt or original_prompt,
        "retrieval_mode": retrieval_mode,
        "mode": mode,
        "context_field": context_field,
        "sources": observed_sources,
        "evidence_fingerprints": evidence_fingerprints,
        "evidence_count": len(evidence_fingerprints),
        "source_count": source_count,
        "context_count": context_count,
        "top_k": top_k,
        "command_trace": command_trace,
        "bundle_version": str(trace_mapping.get("bundle_version") or "").strip(),
        "overlay_path": str(trace_mapping.get("overlay_path") or "").strip(),
        "program_loaded": bool(trace_mapping.get("program_loaded")),
        "execution_status": str(outcome_mapping.get("execution_status") or "").strip(),
        "acceptance_status": str(outcome_mapping.get("acceptance_status") or "").strip().lower(),
        "used_baseline_fallback": bool(outcome_mapping.get("used_baseline_fallback")),
    }


def _prompt_family_id(question: str) -> str:
    """Return the stable prompt-family identifier for one normalized question."""

    normalized_question = _normalize_question_text(question).casefold()
    return f"pf-{_stable_hash(normalized_question)}"


def _question_tokens(question: object) -> list[str]:
    """Return stable normalized lexical tokens for one prompt string."""

    return extract_tokens(_normalize_question_text(question))


def _profile_terms(values: Sequence[object], *, limit: int = 24) -> list[str]:
    """Return stable family-profile lexical terms from prompt-like values."""

    normalized_values = [_normalize_question_text(value) for value in values]
    return extract_profile_terms(normalized_values, limit=limit)


def _increment_term_counts(
    counts: dict[str, int],
    terms: Sequence[str],
) -> None:
    """Update one term-frequency mapping from one ordered term sequence."""

    for term in terms:
        cleaned = str(term or "").strip().casefold()
        if not cleaned:
            continue
        counts[cleaned] = counts.get(cleaned, 0) + 1


def _sorted_term_count_items(counts: Mapping[str, object]) -> list[tuple[str, int]]:
    """Return one deterministic descending list of normalized term counts."""

    normalized: list[tuple[str, int]] = []
    for key, value in counts.items():
        term = str(key or "").strip().casefold()
        if not term:
            continue
        count = _coerce_int(value)
        if count is None or count <= 0:
            continue
        normalized.append((term, count))
    normalized.sort(key=lambda item: (-item[1], item[0]))
    return normalized


def _term_count_mapping(
    counts: Mapping[str, object],
) -> dict[str, int]:
    """Return one deterministic normalized term-frequency dictionary."""

    return dict(_sorted_term_count_items(counts))


def _term_counts_from_stats(
    stats: Mapping[str, object],
) -> dict[str, int]:
    """Return one normalized count mapping from one term-stats payload."""

    counts: dict[str, int] = {}
    for key, value in stats.items():
        term = str(key or "").strip().casefold()
        if not term or not isinstance(value, Mapping):
            continue
        count = _coerce_int(value.get("count"))
        if count is None or count <= 0:
            continue
        counts[term] = count
    return _term_count_mapping(counts)


def _term_stats_mapping(value: object) -> Mapping[str, object]:
    """Return one mapping view for term-stats payloads."""

    if isinstance(value, Mapping):
        return value
    return {}


def _term_stats_from_counts(
    counts: Mapping[str, object],
) -> dict[str, dict[str, float | int]]:
    """Return one normalized term-stats payload with count and weight fields."""

    normalized_counts = _term_count_mapping(counts)
    total = sum(normalized_counts.values())
    if total <= 0:
        return {}
    return {
        term: {
            "count": count,
            "weight": round(count / total, 6),
        }
        for term, count in normalized_counts.items()
    }


def _stable_profile_terms_from_counts(
    counts: Mapping[str, object],
    *,
    limit: int,
    min_count: int = _FAMILY_PROFILE_MIN_COUNT,
) -> list[str]:
    """Return one top-k stable routing profile from one term-frequency mapping."""

    return select_profile_summary_terms(counts, limit=limit, min_count=min_count)


def _stable_profile_min_count(record_count: int) -> int:
    """Return one family-size-aware stability threshold for routing-profile terms."""

    bounded_count = max(0, int(record_count))
    if bounded_count <= 1:
        return 1
    return max(2, math.ceil(bounded_count * 0.75))


def _constraint_terms(values: Sequence[object], *, limit: int = 16) -> list[str]:
    """Return stable file/path/constraint-like tokens from prompt or trace text."""

    constraints: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        for match in _PATHLIKE_TOKEN_PATTERN.findall(text):
            token = match.strip().casefold()
            if not token or token in seen:
                continue
            seen.add(token)
            constraints.append(token)
            if len(constraints) >= limit:
                return constraints
    return constraints


def _command_trace_profile_terms(command_trace: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return stable lexical terms extracted from one command trace summary."""

    values: list[object] = []
    for entry in command_trace:
        for key in ("text", "command", "path", "source", "tool", "type", "role"):
            value = entry.get(key)
            if value not in (None, ""):
                values.append(value)
    return _profile_terms(values, limit=24)


def _command_trace_constraint_terms(command_trace: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return stable constraint/path tokens extracted from one command trace summary."""

    values: list[object] = []
    for entry in command_trace:
        for key in ("text", "command", "path", "source"):
            value = entry.get(key)
            if value not in (None, ""):
                values.append(value)
    return _constraint_terms(values, limit=16)


def _question_similarity(left: object, right: object) -> float:
    """Return a bounded similarity score between two prompt strings."""

    normalized_left = _normalize_question_text(left).casefold()
    normalized_right = _normalize_question_text(right).casefold()
    if not normalized_left and not normalized_right:
        return 1.0
    if not normalized_left or not normalized_right:
        return 0.0
    exact_score = _string_match_similarity(normalized_left, normalized_right)
    token_score = _jaccard_similarity(
        _question_tokens(normalized_left),
        _question_tokens(normalized_right),
    )
    char_score = SequenceMatcher(a=normalized_left, b=normalized_right).ratio()
    return round(max(exact_score, token_score, char_score), 6)


def _family_question_variants(family_payload: Mapping[str, Any]) -> list[str]:
    """Return the stored normalized question variants for one prompt family."""

    variants: list[str] = []
    seen: set[str] = set()

    def _append_variant(value: object) -> None:
        normalized = _normalize_question_text(value).strip()
        if not normalized:
            return
        folded = normalized.casefold()
        if folded in seen:
            return
        seen.add(folded)
        variants.append(normalized)

    _append_variant(family_payload.get("question"))
    _append_variant(family_payload.get("normalized_question"))
    _append_variant(family_payload.get("family_father_question"))
    stored_variants = family_payload.get("question_variants")
    if isinstance(stored_variants, list):
        for variant in stored_variants:
            _append_variant(variant)
    for record in _family_candidate_records(family_payload):
        _append_variant(_record_routing_question(record))
        _append_variant(record.get("question"))
        _append_variant(record.get("original_prompt"))
        _append_variant(record.get("reformulated_prompt"))
    return variants


def _coarse_prompt_family_similarity(
    question: str,
    family_payload: Mapping[str, Any],
) -> float:
    """Return one cheap shortlist score before rich family routing."""

    question_profile_terms = _profile_terms([question])
    question_constraint_terms = _constraint_terms([question])
    family_prompt_terms = _profile_terms(
        [
            family_payload.get("question"),
            family_payload.get("normalized_question"),
            family_payload.get("family_father_question"),
            *_string_list(family_payload.get("family_prompt_profile_terms")),
        ],
        limit=_FAMILY_PROMPT_PROFILE_LIMIT,
    )
    family_command_terms = _profile_terms(
        _string_list(family_payload.get("family_command_pattern_summary")),
        limit=_FAMILY_COMMAND_PROFILE_LIMIT,
    )
    family_constraint_terms = _constraint_terms(
        [
            *_string_list(family_payload.get("family_constraint_summary")),
            *family_command_terms,
        ],
        limit=_FAMILY_CONSTRAINT_PROFILE_LIMIT,
    )
    family_question_support = max(
        _question_similarity(question, str(family_payload.get("family_father_question") or "")),
        _question_similarity(question, str(family_payload.get("question") or "")),
        _question_similarity(question, str(family_payload.get("normalized_question") or "")),
    )
    prompt_overlap = _profile_overlap_similarity(question_profile_terms, family_prompt_terms)
    constraint_overlap = _profile_overlap_similarity(
        question_constraint_terms,
        [*family_constraint_terms, *family_command_terms],
    )
    command_overlap = _profile_overlap_similarity(question_profile_terms, family_command_terms)
    routing_score = max(
        prompt_overlap,
        (
            (0.55 * prompt_overlap)
            + (0.25 * constraint_overlap)
            + (0.10 * command_overlap)
            + (0.10 * family_question_support)
        ),
    )
    return round(min(1.0, max(0.0, routing_score)), 6)


def _prompt_family_similarity(question: str, family_payload: Mapping[str, Any]) -> float:
    """Return one profile-first routing score for a prompt against one family."""

    candidate_questions = _family_question_variants(family_payload)
    family_father_question = _routing_question(
        question=family_payload.get("family_father_question")
        or family_payload.get("question")
        or family_payload.get("normalized_question"),
        original_prompt=(_family_father_record(family_payload) or {}).get("original_prompt"),
        reformulated_prompt=(_family_father_record(family_payload) or {}).get(
            "reformulated_prompt"
        ),
    )
    if family_father_question:
        candidate_questions = [family_father_question, *candidate_questions]
    best_similarity = 0.0
    for candidate_question in candidate_questions:
        best_similarity = max(best_similarity, _question_similarity(question, candidate_question))
    family_record_count = max(1, len(_family_candidate_records(family_payload)))
    profile_min_count = _stable_profile_min_count(family_record_count)
    family_prompt_term_counts = _term_counts_from_stats(
        _term_stats_mapping(family_payload.get("family_prompt_profile_term_stats"))
    ) or _term_count_mapping(
        _term_stats_mapping(family_payload.get("family_prompt_profile_term_counts"))
    )
    if family_prompt_term_counts:
        family_prompt_profile_terms = _stable_profile_terms_from_counts(
            family_prompt_term_counts,
            limit=_FAMILY_PROMPT_PROFILE_LIMIT,
            min_count=profile_min_count,
        )
    else:
        family_prompt_profile_terms = _profile_terms(
            [
                *candidate_questions,
                *_string_list(family_payload.get("family_prompt_profile_terms")),
            ],
            limit=_FAMILY_PROMPT_PROFILE_LIMIT,
        )
    family_command_term_counts = _term_counts_from_stats(
        _term_stats_mapping(family_payload.get("family_command_pattern_term_stats"))
    ) or _term_count_mapping(
        _term_stats_mapping(family_payload.get("family_command_pattern_counts"))
    )
    if family_command_term_counts:
        family_command_pattern_summary = _stable_profile_terms_from_counts(
            family_command_term_counts,
            limit=_FAMILY_COMMAND_PROFILE_LIMIT,
            min_count=profile_min_count,
        )
    else:
        family_command_pattern_summary = _profile_terms(
            _string_list(family_payload.get("family_command_pattern_summary")),
            limit=_FAMILY_COMMAND_PROFILE_LIMIT,
        )
    family_constraint_term_counts = _term_counts_from_stats(
        _term_stats_mapping(family_payload.get("family_constraint_term_stats"))
    ) or _term_count_mapping(_term_stats_mapping(family_payload.get("family_constraint_counts")))
    if family_constraint_term_counts:
        family_constraint_summary = _stable_profile_terms_from_counts(
            family_constraint_term_counts,
            limit=_FAMILY_CONSTRAINT_PROFILE_LIMIT,
            min_count=profile_min_count,
        )
    else:
        family_constraint_summary = _constraint_terms(
            [
                *_string_list(family_payload.get("family_constraint_summary")),
                *family_command_pattern_summary,
            ],
            limit=_FAMILY_CONSTRAINT_PROFILE_LIMIT,
        )
    question_profile_terms = _profile_terms([question])
    question_constraint_terms = _constraint_terms([question])
    profile_overlap = max(
        _profile_overlap_similarity(question_profile_terms, family_prompt_profile_terms),
        _profile_overlap_similarity(
            question_constraint_terms,
            [*family_constraint_summary, *family_command_pattern_summary],
        ),
    )
    family_success_metric = family_payload.get("family_success_metric")
    family_feedback_metric = family_payload.get("family_feedback_metric")
    predicted_success = 0.0
    uncertainty = 0.0
    if isinstance(family_success_metric, Mapping):
        posterior_mean = family_success_metric.get("posterior_mean")
        if isinstance(posterior_mean, (int, float)) and not isinstance(posterior_mean, bool):
            predicted_success = float(posterior_mean)
        uncertainty_value = family_success_metric.get("uncertainty")
        if isinstance(uncertainty_value, (int, float)) and not isinstance(uncertainty_value, bool):
            uncertainty = float(uncertainty_value)
    if predicted_success == 0.0 and isinstance(family_feedback_metric, Mapping):
        feedback_hit_rate = family_feedback_metric.get("hit_rate")
        if isinstance(feedback_hit_rate, (int, float)) and not isinstance(feedback_hit_rate, bool):
            predicted_success = float(feedback_hit_rate)
    if predicted_success == 0.0:
        family_metric_1_mean = family_payload.get("family_metric_1_mean")
        if isinstance(family_metric_1_mean, (int, float)) and not isinstance(
            family_metric_1_mean, bool
        ):
            predicted_success = float(family_metric_1_mean)
    routing_score = max(
        profile_overlap,
        (
            (_FAMILY_ROUTING_PROFILE_PRIMARY_WEIGHT * profile_overlap)
            + (_FAMILY_ROUTING_PROMPT_SUPPORT_WEIGHT * best_similarity)
            + (_FAMILY_ROUTING_SUCCESS_BOOST * predicted_success)
            - (_FAMILY_ROUTING_UNCERTAINTY_PENALTY * uncertainty)
        ),
    )
    routing_score = min(1.0, max(0.0, routing_score))
    return round(max(0.0, routing_score), 6)


def _family_routing_question(family_payload: Mapping[str, Any]) -> str:
    """Return the current routing question for one prompt family payload."""

    father_record = _family_father_record(family_payload) or {}
    return _routing_question(
        question=family_payload.get("family_father_question")
        or family_payload.get("question")
        or family_payload.get("normalized_question"),
        original_prompt=father_record.get("original_prompt"),
        reformulated_prompt=father_record.get("reformulated_prompt"),
    )


def _family_profile_summary(
    family_payload: Mapping[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    """Return stable prompt, command, and constraint summaries for one family payload."""

    family_record_count = max(1, len(_family_candidate_records(family_payload)))
    profile_min_count = _stable_profile_min_count(family_record_count)
    candidate_questions = _family_question_variants(family_payload)
    family_routing_question = _family_routing_question(family_payload)
    if family_routing_question:
        candidate_questions = [family_routing_question, *candidate_questions]

    family_prompt_term_counts = _term_counts_from_stats(
        _term_stats_mapping(family_payload.get("family_prompt_profile_term_stats"))
    ) or _term_count_mapping(
        _term_stats_mapping(family_payload.get("family_prompt_profile_term_counts"))
    )
    if family_prompt_term_counts:
        family_prompt_profile_terms = _stable_profile_terms_from_counts(
            family_prompt_term_counts,
            limit=_FAMILY_PROMPT_PROFILE_LIMIT,
            min_count=profile_min_count,
        )
    else:
        family_prompt_profile_terms = _profile_terms(
            [
                *candidate_questions,
                *_string_list(family_payload.get("family_prompt_profile_terms")),
            ],
            limit=_FAMILY_PROMPT_PROFILE_LIMIT,
        )

    family_command_term_counts = _term_counts_from_stats(
        _term_stats_mapping(family_payload.get("family_command_pattern_term_stats"))
    ) or _term_count_mapping(
        _term_stats_mapping(family_payload.get("family_command_pattern_counts"))
    )
    if family_command_term_counts:
        family_command_pattern_summary = _stable_profile_terms_from_counts(
            family_command_term_counts,
            limit=_FAMILY_COMMAND_PROFILE_LIMIT,
            min_count=profile_min_count,
        )
    else:
        family_command_pattern_summary = _profile_terms(
            _string_list(family_payload.get("family_command_pattern_summary")),
            limit=_FAMILY_COMMAND_PROFILE_LIMIT,
        )

    family_constraint_term_counts = _term_counts_from_stats(
        _term_stats_mapping(family_payload.get("family_constraint_term_stats"))
    ) or _term_count_mapping(_term_stats_mapping(family_payload.get("family_constraint_counts")))
    if family_constraint_term_counts:
        family_constraint_summary = _stable_profile_terms_from_counts(
            family_constraint_term_counts,
            limit=_FAMILY_CONSTRAINT_PROFILE_LIMIT,
            min_count=profile_min_count,
        )
    else:
        family_constraint_summary = _constraint_terms(
            [
                *_string_list(family_payload.get("family_constraint_summary")),
                *family_command_pattern_summary,
            ],
            limit=_FAMILY_CONSTRAINT_PROFILE_LIMIT,
        )

    return (
        family_prompt_profile_terms,
        family_command_pattern_summary,
        family_constraint_summary,
    )


def _family_to_family_similarity(
    left_family: Mapping[str, Any],
    right_family: Mapping[str, Any],
) -> float:
    """Return a symmetric routing score between two family-like payloads."""

    left_question_variants = _family_question_variants(left_family)
    right_question_variants = _family_question_variants(right_family)
    left_question = _family_routing_question(left_family)
    right_question = _family_routing_question(right_family)
    if left_question:
        left_question_variants = [left_question, *left_question_variants]
    if right_question:
        right_question_variants = [right_question, *right_question_variants]
    left_prompt_terms, left_command_terms, left_constraint_terms = _family_profile_summary(
        left_family
    )
    right_prompt_terms, right_command_terms, right_constraint_terms = _family_profile_summary(
        right_family
    )
    question_similarity = 0.0
    for left_variant in left_question_variants:
        for right_variant in right_question_variants:
            question_similarity = max(
                question_similarity,
                _question_similarity(left_variant, right_variant),
            )
    prompt_overlap = _profile_overlap_similarity(left_prompt_terms, right_prompt_terms)
    command_overlap = _profile_overlap_similarity(left_command_terms, right_command_terms)
    constraint_overlap = _profile_overlap_similarity(
        [*left_constraint_terms, *left_command_terms],
        [*right_constraint_terms, *right_command_terms],
    )
    shared_prompt_anchor_count = len(
        {term.casefold() for term in left_prompt_terms if term.strip()}.intersection(
            {term.casefold() for term in right_prompt_terms if term.strip()}
        )
    )
    shared_constraint_anchor_count = len(
        {
            term.casefold()
            for term in [*left_constraint_terms, *left_command_terms]
            if term.strip()
        }.intersection(
            {
                term.casefold()
                for term in [*right_constraint_terms, *right_command_terms]
                if term.strip()
            }
        )
    )
    anchor_support = min(1.0, shared_prompt_anchor_count / 6.0)
    constraint_support = min(1.0, shared_constraint_anchor_count / 4.0)
    routing_score = max(
        prompt_overlap,
        constraint_overlap,
        (
            prompt_overlap
            + (0.2 * anchor_support)
            + (0.05 * constraint_support)
            + (0.05 * command_overlap)
            + (0.05 * question_similarity)
        ),
    )
    return round(min(1.0, max(0.0, routing_score)), 6)


def _shortlist_prompt_families(
    question: str,
    families: Sequence[Mapping[str, Any]],
    *,
    top_k: int = _FAMILY_ROUTING_SHORTLIST_TOP_K,
) -> list[Mapping[str, Any]]:
    """Return one coarse top-k shortlist of prompt-family payloads."""

    shortlist_limit = max(1, int(top_k))
    ranked: list[tuple[float, Mapping[str, Any]]] = []
    for family in families:
        score = _coarse_prompt_family_similarity(question, family)
        ranked.append((score, family))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [family for _, family in ranked[:shortlist_limit]]


def _sqlite_family_index_shortlist(
    question: str,
    family_state_path: Path,
    *,
    top_k: int = _FAMILY_ROUTING_SHORTLIST_TOP_K,
) -> list[dict[str, Any]]:
    """Return one coarse top-k shortlist from the SQLite family index."""

    resolved_family_state_path = resolve_family_index_path(family_state_path)
    if not resolved_family_state_path.is_file():
        return []
    ranked: list[tuple[float, dict[str, Any]]] = []
    connection = sqlite3.connect(resolved_family_state_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT prompt_family_id, question, normalized_question, family_father_question,
                   question_variant_count, family_record_count, prompt_terms_json,
                   command_terms_json, constraint_terms_json, family_path, father_path
            FROM family_index_entries
            ORDER BY prompt_family_id
            """
        )
        for row in rows:
            try:
                prompt_terms = json.loads(str(row["prompt_terms_json"] or "[]"))
            except json.JSONDecodeError:
                prompt_terms = []
            try:
                command_terms = json.loads(str(row["command_terms_json"] or "[]"))
            except json.JSONDecodeError:
                command_terms = []
            try:
                constraint_terms = json.loads(str(row["constraint_terms_json"] or "[]"))
            except json.JSONDecodeError:
                constraint_terms = []
            family_entry = {
                "prompt_family_id": str(row["prompt_family_id"] or "").strip(),
                "question": str(row["question"] or "").strip(),
                "normalized_question": str(row["normalized_question"] or "").strip(),
                "family_father_question": str(row["family_father_question"] or "").strip(),
                "question_variant_count": int(row["question_variant_count"] or 0),
                "family_record_count": int(row["family_record_count"] or 0),
                "family_prompt_profile_terms": prompt_terms
                if isinstance(prompt_terms, list)
                else [],
                "family_command_pattern_summary": command_terms
                if isinstance(command_terms, list)
                else [],
                "family_constraint_summary": constraint_terms
                if isinstance(constraint_terms, list)
                else [],
                "family_path": str(row["family_path"] or "").strip(),
                "father_path": str(row["father_path"] or "").strip(),
            }
            ranked.append((_coarse_prompt_family_similarity(question, family_entry), family_entry))
    except sqlite3.DatabaseError:
        return []
    finally:
        connection.close()
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [family for _, family in ranked[: max(1, int(top_k))]]


def _resolve_prompt_family_support_from_families(
    question: str,
    families: Sequence[Mapping[str, Any]],
) -> PromptFamilySupport:
    """Resolve prompt-family support from one family sequence with shortlist routing."""

    normalized_question = _normalize_question_text(question)
    if not normalized_question:
        return PromptFamilySupport(
            question="",
            prompt_family_id=None,
            similarity=0.0,
            band="new",
            supported=False,
            family_father_question=None,
            family_father_record=None,
            family_runtime_record=None,
        )
    best_family: Mapping[str, Any] | None = None
    best_similarity = 0.0
    shortlisted_families = _shortlist_prompt_families(normalized_question, families)
    for family in shortlisted_families:
        similarity = _prompt_family_similarity(normalized_question, family)
        if similarity > best_similarity:
            best_family = family
            best_similarity = similarity
    band = "match" if best_similarity >= PROMPT_FAMILY_MATCH_THRESHOLD else "new"
    supported = bool(best_family is not None and best_similarity >= PROMPT_FAMILY_MATCH_THRESHOLD)
    prompt_family_id = (
        str(best_family.get("prompt_family_id") or "").strip()
        if isinstance(best_family, Mapping)
        else ""
    )
    family_father_question = (
        _normalize_question_text(best_family.get("family_father_question"))
        if isinstance(best_family, Mapping)
        else ""
    )
    family_father_record = _family_father_record(best_family) if best_family is not None else None
    family_runtime_record = _family_runtime_record(best_family) if best_family is not None else None
    return PromptFamilySupport(
        question=normalized_question,
        prompt_family_id=prompt_family_id or None,
        similarity=best_similarity,
        band=band,
        supported=supported,
        family_father_question=family_father_question or None,
        family_father_record=family_father_record,
        family_runtime_record=family_runtime_record,
    )


def _singleton_prompt_family_payload(
    *,
    question: str,
    candidate_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one temporary family-like payload built from a single trace record."""

    family_payload: dict[str, Any] = {
        "prompt_family_id": _prompt_family_id(question),
        "family_needs_recompile": True,
        "question": "",
        "normalized_question": "",
        "question_variants": [],
        "question_variant_count": 0,
        "family_prompt_profile_term_stats": {},
        "family_command_pattern_term_stats": {},
        "family_constraint_term_stats": {},
        "family_prompt_profile_terms": [],
        "family_command_pattern_summary": [],
        "family_constraint_summary": [],
        "family_father_question": None,
        "family_father_similarity_mean": None,
        "family_father_record": None,
        "family_runtime_artifact": None,
        "family_runtime_context_group_id": None,
        "family_runtime_score": None,
        "family_runtime_record": None,
        "family_feedback_metric": None,
        "family_feedback_count": 0,
        "family_success_metric": None,
        "family_champion_context_group_id": None,
        "family_champion_score": None,
        "family_champion_record": None,
        "family_records": [],
        "context_groups": [],
    }
    if isinstance(candidate_record, Mapping):
        normalized_record = _serialize_candidate_record(candidate_record)
        if _trainer_candidate_record_is_supported(normalized_record):
            family_payload["family_records"] = [normalized_record]
    _refresh_prompt_family_summary(family_payload, question)
    return family_payload


def _refresh_family_profile_summary(family_payload: dict[str, Any]) -> None:
    """Persist one lightweight routing profile derived from stored family traces."""

    family_record_count = len(_family_candidate_records(family_payload))
    profile_min_count = _stable_profile_min_count(family_record_count)
    prompt_term_counts: dict[str, int] = {}
    command_term_counts: dict[str, int] = {}
    constraint_term_counts: dict[str, int] = {}

    seed_prompt_terms = _profile_terms(
        [
            family_payload.get("question"),
            family_payload.get("normalized_question"),
            family_payload.get("family_father_question"),
            *(family_payload.get("question_variants", []) or []),
        ],
        limit=_FAMILY_PROMPT_PROFILE_LIMIT * 4,
    )
    _increment_term_counts(prompt_term_counts, seed_prompt_terms)

    for record in _family_candidate_records(family_payload):
        record_prompt_terms = _profile_terms(
            [
                record.get("question"),
                record.get("original_prompt"),
                record.get("reformulated_prompt"),
            ],
            limit=_FAMILY_PROMPT_PROFILE_LIMIT * 4,
        )
        _increment_term_counts(prompt_term_counts, record_prompt_terms)

        command_trace = _ordered_unique_command_trace(record.get("command_trace"))
        record_command_terms = _command_trace_profile_terms(command_trace)
        _increment_term_counts(command_term_counts, record_command_terms)

        record_constraint_terms = _constraint_terms(
            [
                record.get("question"),
                record.get("original_prompt"),
                record.get("reformulated_prompt"),
                *_command_trace_constraint_terms(command_trace),
            ],
            limit=_FAMILY_CONSTRAINT_PROFILE_LIMIT * 4,
        )
        _increment_term_counts(constraint_term_counts, record_constraint_terms)

    prompt_term_counts = _term_count_mapping(prompt_term_counts)
    command_term_counts = _term_count_mapping(command_term_counts)
    constraint_term_counts = _term_count_mapping(constraint_term_counts)
    family_payload["family_prompt_profile_term_stats"] = _term_stats_from_counts(prompt_term_counts)
    family_payload["family_command_pattern_term_stats"] = _term_stats_from_counts(
        command_term_counts
    )
    family_payload["family_constraint_term_stats"] = _term_stats_from_counts(constraint_term_counts)
    family_payload["family_prompt_profile_terms"] = _stable_profile_terms_from_counts(
        prompt_term_counts,
        limit=_FAMILY_PROMPT_PROFILE_LIMIT,
        min_count=profile_min_count,
    )
    family_payload["family_command_pattern_summary"] = _stable_profile_terms_from_counts(
        command_term_counts,
        limit=_FAMILY_COMMAND_PROFILE_LIMIT,
        min_count=profile_min_count,
    )
    family_payload["family_constraint_summary"] = _stable_profile_terms_from_counts(
        constraint_term_counts,
        limit=_FAMILY_CONSTRAINT_PROFILE_LIMIT,
        min_count=profile_min_count,
    )


def resolve_prompt_family_support_from_payload(
    question: str,
    payload: Mapping[str, Any],
) -> PromptFamilySupport:
    """Resolve the best stored prompt-family support from one in-memory family payload."""

    families = payload.get("prompt_families")
    if not isinstance(families, list):
        families = []
    mapped_families = [family for family in families if isinstance(family, Mapping)]
    return _resolve_prompt_family_support_from_families(question, mapped_families)


def resolve_prompt_family_support(question: str, family_state_path: Path) -> PromptFamilySupport:
    """Resolve the best stored prompt-family support for one prompt string."""

    sqlite_shortlist = _sqlite_family_index_shortlist(question, family_state_path)
    if sqlite_shortlist:
        hydrated_families = [
            _family_state_entry_to_payload(family_state_path, family) for family in sqlite_shortlist
        ]
        return _resolve_prompt_family_support_from_families(question, hydrated_families)
    index_payload = _load_champion_index(family_state_path)
    return resolve_prompt_family_support_from_payload(question, index_payload)


def _refresh_prompt_family_summary(family_payload: dict[str, Any], question: str) -> None:
    """Update one prompt-family summary so routing follows the current family father."""

    normalized_question = _routing_question(question=question)
    question_variants = family_payload.get("question_variants")
    if not isinstance(question_variants, list):
        question_variants = []
        family_payload["question_variants"] = question_variants
    merged_variants = _family_question_variants(
        {
            **family_payload,
            "question_variants": [*question_variants, normalized_question],
        }
    )
    family_payload["question_variants"] = merged_variants
    family_payload["question_variant_count"] = len(merged_variants)
    father_record, father_similarity_mean = _select_family_father_record(family_payload)
    if father_record is not None:
        family_payload["family_father_record"] = father_record
        father_question = _record_routing_question(father_record)
        family_payload["family_father_question"] = father_question or None
        family_payload["family_father_similarity_mean"] = father_similarity_mean
        family_payload["question"] = father_question
        family_payload["normalized_question"] = father_question.casefold()
        _refresh_family_profile_summary(family_payload)
        return
    family_payload["family_father_record"] = None
    family_payload["family_father_similarity_mean"] = None
    family_payload["family_father_question"] = normalized_question or None
    if normalized_question:
        family_payload["question"] = normalized_question
        family_payload["normalized_question"] = normalized_question.casefold()
    _refresh_family_profile_summary(family_payload)


def _find_or_create_prompt_family(
    family_by_id: dict[str, dict[str, Any]],
    family_order: list[str],
    *,
    question: str,
    candidate_record: Mapping[str, Any] | None = None,
    preferred_family_id: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Return the matching prompt family for one question, creating one when needed."""

    candidate_family = _singleton_prompt_family_payload(
        question=question,
        candidate_record=candidate_record,
    )
    best_family: dict[str, Any] | None = None
    best_similarity = 0.0
    for family_id in family_order:
        family_payload = family_by_id.get(family_id)
        if family_payload is None:
            continue
        similarity = _family_to_family_similarity(candidate_family, family_payload)
        if similarity > best_similarity:
            best_family = family_payload
            best_similarity = similarity
    if best_family is not None and best_similarity >= PROMPT_FAMILY_MATCH_THRESHOLD:
        _refresh_prompt_family_summary(best_family, question)
        return best_family, False

    prompt_family_id = str(preferred_family_id or _prompt_family_id(question)).strip()
    if not prompt_family_id:
        prompt_family_id = _prompt_family_id(question)
    if prompt_family_id in family_by_id:
        suffix = 2
        candidate_id = f"{prompt_family_id}-{suffix}"
        while candidate_id in family_by_id:
            suffix += 1
            candidate_id = f"{prompt_family_id}-{suffix}"
        prompt_family_id = candidate_id
    family_payload = _singleton_prompt_family_payload(
        question=question,
        candidate_record=candidate_record,
    )
    family_payload["prompt_family_id"] = prompt_family_id
    family_payload["family_records"] = []
    _refresh_prompt_family_summary(family_payload, question)
    family_by_id[prompt_family_id] = family_payload
    family_order.append(prompt_family_id)
    return family_payload, True


def _exact_snapshot_id(
    *,
    question: str,
    expected_answer: str,
    source_identity: str,
    trace_record_path: str,
    recorded_at: str,
    context_snapshot: Mapping[str, Any],
) -> str:
    """Return the immutable identity for one concrete imported trace snapshot."""

    identity_token = source_identity.strip() or trace_record_path.strip() or recorded_at.strip()
    stable_snapshot_hash = _stable_hash(
        question,
        expected_answer,
        identity_token,
        context_snapshot,
    )
    return f"ts-{stable_snapshot_hash}"


_REPLAYED_TRACE_RECORD_NAME_PATTERN = re.compile(
    r"^(?P<prefix>\d{8}T\d{6}Z)-(?P<rest>\d{8}T\d{6}Z-.*)$"
)


def _canonical_trace_record_path(path_text: object) -> str:
    """Return one stable trace-record path token across imported replays."""

    normalized_path = str(path_text or "").strip()
    if not normalized_path:
        return ""
    candidate = Path(normalized_path)
    file_name = candidate.name
    while True:
        match = _REPLAYED_TRACE_RECORD_NAME_PATTERN.match(file_name)
        if match is None:
            break
        file_name = match.group("rest")
    return str(candidate.with_name(file_name))


def _stable_trace_source_identity(
    payload: Mapping[str, Any],
    *,
    trace_record_path: str,
) -> str:
    """Return one stable source identity for deduping logical trace replays."""

    source_queue_item_path = str(payload.get("source_queue_item_path") or "").strip()
    if source_queue_item_path:
        canonical_queue_item_path = _canonical_trace_record_path(source_queue_item_path)
        return f"trace-file:{Path(canonical_queue_item_path).name}"
    provenance = payload.get("provenance")
    if isinstance(provenance, Mapping):
        provenance_queue_item_path = str(provenance.get("source_queue_item_path") or "").strip()
        if provenance_queue_item_path:
            canonical_queue_item_path = _canonical_trace_record_path(provenance_queue_item_path)
            return f"trace-file:{Path(canonical_queue_item_path).name}"
    source_trace_name = str(payload.get("source_trace_name") or "").strip()
    source_batch_name = str(payload.get("source_batch_name") or "").strip()
    if source_trace_name:
        if source_batch_name:
            return f"trace:{source_batch_name}:{source_trace_name}"
        return f"trace:{source_trace_name}"
    canonical_trace_path = _canonical_trace_record_path(trace_record_path)
    if canonical_trace_path:
        return f"trace-file:{Path(canonical_trace_path).name}"
    return ""


def _metric_ratio(hits: int, total: int) -> float:
    """Return one bounded `hits / total` score."""

    if total <= 0:
        return 0.0
    return round(max(0, min(hits, total)) / total, 6)


def _trace_hit_total_metric(
    trace_mapping: Mapping[str, Any],
    context_snapshot: Mapping[str, Any],
) -> tuple[int, int, float]:
    """Return the active trainer metric for one trace."""

    raw_hits = _coerce_int(trace_mapping.get("mediation_metric_hits"))
    raw_total = _coerce_int(trace_mapping.get("mediation_metric_total"))
    if raw_hits is None or raw_total is None:
        execution_status = str(context_snapshot.get("execution_status") or "").strip().lower()
        raw_hits = 1 if execution_status == "success" else 0
        raw_total = 1
    hits = max(0, raw_hits)
    total = max(0, raw_total)
    return hits, total, _metric_ratio(hits, total)


def _record_metric(record: Mapping[str, Any]) -> tuple[int, int, float]:
    """Return persisted `hits / total` metric fields from one record."""

    hits = max(0, _coerce_int(record.get("metric_hits")) or 0)
    total = max(0, _coerce_int(record.get("metric_total")) or 0)
    raw_ratio = record.get("metric_ratio")
    if isinstance(raw_ratio, int | float):
        ratio = round(float(raw_ratio), 6)
    else:
        ratio = _metric_ratio(hits, total)
    return hits, total, ratio


def _feedback_metric_payload(
    *,
    hits: int,
    total: int,
) -> dict[str, Any]:
    """Return one normalized family feedback-metric payload."""

    return {
        "metric_hits": max(0, hits),
        "metric_total": max(0, total),
        "hit_rate": _metric_ratio(max(0, hits), max(0, total)),
    }


def _aggregate_record_metric(records: Sequence[Mapping[str, Any]]) -> tuple[int, int]:
    """Return aggregated `hits / total` counts across one record sequence."""

    aggregate_hits = 0
    aggregate_total = 0
    for record in records:
        hits, total, _ = _record_metric(record)
        aggregate_hits += hits
        aggregate_total += total
    return aggregate_hits, aggregate_total


def _success_metric_payload(
    *,
    replay_hits: int,
    replay_total: int,
    feedback_hits: int,
    feedback_total: int,
) -> dict[str, Any] | None:
    """Return one posterior success-profile payload for one prompt family."""

    replay_hits = max(0, replay_hits)
    replay_total = max(0, replay_total)
    feedback_hits = max(0, feedback_hits)
    feedback_total = max(0, feedback_total)
    evidence_hits = replay_hits + feedback_hits
    evidence_total = replay_total + feedback_total
    if evidence_total <= 0:
        return None
    posterior_alpha = _SUCCESS_POSTERIOR_ALPHA_PRIOR + evidence_hits
    posterior_beta = _SUCCESS_POSTERIOR_BETA_PRIOR + max(0, evidence_total - evidence_hits)
    posterior_mass = posterior_alpha + posterior_beta
    posterior_mean = posterior_alpha / posterior_mass
    posterior_variance = (
        posterior_alpha * posterior_beta / ((posterior_mass**2) * (posterior_mass + 1.0))
    )
    posterior_stddev = math.sqrt(max(0.0, posterior_variance))
    lower_bound = max(0.0, posterior_mean - (_SUCCESS_LOWER_BOUND_Z * posterior_stddev))
    return {
        "evidence_hits": evidence_hits,
        "evidence_total": evidence_total,
        "replay_hits": replay_hits,
        "replay_total": replay_total,
        "feedback_hits": feedback_hits,
        "feedback_total": feedback_total,
        "posterior_alpha": round(posterior_alpha, 6),
        "posterior_beta": round(posterior_beta, 6),
        "posterior_mean": round(posterior_mean, 6),
        "lower_bound": round(lower_bound, 6),
        "uncertainty": round(posterior_stddev, 6),
    }


def _family_feedback_metric(family_payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the normalized aggregated feedback metric for one family."""

    raw_metric = family_payload.get("family_feedback_metric")
    if not isinstance(raw_metric, Mapping):
        return None
    hits = max(0, _coerce_int(raw_metric.get("metric_hits")) or 0)
    total = max(0, _coerce_int(raw_metric.get("metric_total")) or 0)
    return _feedback_metric_payload(hits=hits, total=total)


def _family_success_metric(family_payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the posterior success profile for one prompt family."""

    replay_hits, replay_total = _aggregate_record_metric(_family_replay_records(family_payload))
    feedback_metric = _family_feedback_metric(family_payload)
    feedback_hits = max(0, _coerce_int((feedback_metric or {}).get("metric_hits")) or 0)
    feedback_total = max(0, _coerce_int((feedback_metric or {}).get("metric_total")) or 0)
    raw_metric = family_payload.get("family_success_metric")
    if not isinstance(raw_metric, Mapping):
        return _success_metric_payload(
            replay_hits=replay_hits,
            replay_total=replay_total,
            feedback_hits=feedback_hits,
            feedback_total=feedback_total,
        )
    return _success_metric_payload(
        replay_hits=max(0, _coerce_int(raw_metric.get("replay_hits")) or replay_hits),
        replay_total=max(0, _coerce_int(raw_metric.get("replay_total")) or replay_total),
        feedback_hits=max(0, _coerce_int(raw_metric.get("feedback_hits")) or feedback_hits),
        feedback_total=max(0, _coerce_int(raw_metric.get("feedback_total")) or feedback_total),
    )


def _apply_family_feedback_trace(
    family_payload: dict[str, Any],
    record: Mapping[str, Any],
) -> None:
    """Update family-level runtime priors from one feedback-only trace."""

    normalized = _serialize_candidate_record(record)
    metric_hits, metric_total, _ = _record_metric(normalized)
    current_metric = _family_feedback_metric(family_payload)
    current_hits = _coerce_int((current_metric or {}).get("metric_hits")) or 0
    current_total = _coerce_int((current_metric or {}).get("metric_total")) or 0
    next_hits = metric_hits + current_hits
    next_total = metric_total + current_total
    family_payload["family_feedback_metric"] = _feedback_metric_payload(
        hits=next_hits,
        total=next_total,
    )
    family_payload["family_feedback_count"] = (
        max(0, int(family_payload.get("family_feedback_count") or 0)) + 1
    )
    runtime_artifact = family_payload.get("family_runtime_artifact")
    if not isinstance(runtime_artifact, dict):
        runtime_artifact = {}
        family_payload["family_runtime_artifact"] = runtime_artifact
    family_success_metric = _family_success_metric(family_payload)
    family_payload["family_success_metric"] = family_success_metric
    runtime_artifact["feedback_metric"] = family_payload["family_feedback_metric"]
    runtime_artifact["feedback_count"] = family_payload["family_feedback_count"]
    if family_success_metric is not None:
        runtime_artifact["predicted_hit_rate"] = family_success_metric["posterior_mean"]
        runtime_artifact["predicted_hit_rate_lower_bound"] = family_success_metric["lower_bound"]
        runtime_artifact["prediction_uncertainty"] = family_success_metric["uncertainty"]


def _extract_benchmark_context(
    payload: Mapping[str, Any],
) -> tuple[list[str], list[str]]:
    """Return compact benchmark context snippets plus their sources from one trace payload."""

    rows: list[Mapping[str, Any]] = []
    for field_name in ("retrieved_context", "context"):
        raw_rows = payload.get(field_name)
        if not isinstance(raw_rows, list):
            continue
        rows.extend(row for row in raw_rows if isinstance(row, Mapping))

    context_texts: list[str] = []
    context_sources: list[str] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        source = " ".join(str(row.get("source") or "").strip().split())
        text = _normalize_training_answer_whitespace(
            str(row.get("text") or row.get("preview") or "").strip()
        )
        if not source and not text:
            continue
        key = (source.casefold(), text.casefold())
        if key in seen:
            continue
        seen.add(key)
        context_texts.append(text)
        context_sources.append(source)
    return context_texts, context_sources


def _serialize_candidate_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON/YAML-safe trainer candidate record copy."""

    normalized = _normalize_materialized_candidate_record(record)
    for field_name in (
        "prompt_family_id",
        "context_group_id",
        "exact_snapshot_id",
        "quality_score",
        "metric_hits",
        "metric_total",
        "metric_ratio",
        "support_count",
    ):
        if field_name in record and record.get(field_name) not in (None, ""):
            normalized[field_name] = record.get(field_name)
    provenance = record.get("provenance")
    if isinstance(provenance, Mapping):
        merged_provenance = dict(provenance)
        existing_provenance = normalized.get("provenance")
        if isinstance(existing_provenance, Mapping):
            merged_provenance.update(existing_provenance)
        normalized["provenance"] = merged_provenance
    return normalized


def _fresh_champion_index() -> dict[str, Any]:
    """Return an empty champion-index payload."""

    return {
        "schema_version": TRAINER_FAMILY_STATE_SCHEMA_VERSION,
        "record_kind": TRAINER_CHAMPION_INDEX_KIND,
        "family_state_kind": TRAINER_FAMILY_STATE_KIND,
        "family_state_layout": "sqlite-index",
        "generated_at": datetime.now(UTC).isoformat(),
        "prompt_families": [],
    }


def _family_state_entry_to_payload(
    family_state_path: Path,
    family_entry: Mapping[str, Any],
) -> dict[str, Any]:
    """Hydrate one persisted thin-index family entry into its full family payload."""

    loaded_payload: dict[str, Any] | None = None
    resolved_family_path = _resolve_family_state_member_path(
        family_state_path,
        family_entry.get("family_path"),
    )
    if resolved_family_path is not None and resolved_family_path.is_file():
        candidate_payload = json.loads(resolved_family_path.read_text(encoding="utf-8"))
        if isinstance(candidate_payload, dict):
            loaded_payload = {str(key): value for key, value in candidate_payload.items()}
    if loaded_payload is None:
        loaded_payload = {str(key): value for key, value in family_entry.items()}
    for field_name in (
        "prompt_family_id",
        "family_path",
        "father_path",
        "family_needs_recompile",
        "question",
        "normalized_question",
        "question_variants",
        "question_variant_count",
        "family_prompt_profile_term_counts",
        "family_command_pattern_counts",
        "family_constraint_counts",
        "family_prompt_profile_term_stats",
        "family_command_pattern_term_stats",
        "family_constraint_term_stats",
        "family_prompt_profile_terms",
        "family_command_pattern_summary",
        "family_constraint_summary",
        "family_father_question",
        "family_father_similarity_mean",
        "family_father_record",
        "family_runtime_artifact",
        "family_runtime_score",
        "family_metric_1_mean",
        "family_runtime_record",
        "family_feedback_metric",
        "family_feedback_count",
        "family_success_metric",
    ):
        if field_name in family_entry and field_name not in loaded_payload:
            loaded_payload[field_name] = family_entry[field_name]
    return loaded_payload


def _strip_family_state_inline_payload(
    family_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Return one thin-index family entry without replay-set duplication."""

    replay_record_count = len(_family_replay_records(family_payload))
    context_groups_value = family_payload.get("context_groups")
    context_groups = context_groups_value if isinstance(context_groups_value, list) else []

    return {
        "prompt_family_id": str(family_payload.get("prompt_family_id") or "").strip(),
        "family_needs_recompile": bool(family_payload.get("family_needs_recompile")),
        "question": _normalize_question_text(family_payload.get("question")),
        "normalized_question": _normalize_question_text(family_payload.get("normalized_question")),
        "question_variant_count": len(_family_question_variants(family_payload)),
        "family_prompt_profile_term_stats": _term_stats_from_counts(
            _term_counts_from_stats(
                _term_stats_mapping(family_payload.get("family_prompt_profile_term_stats"))
            )
            or _term_count_mapping(
                _term_stats_mapping(family_payload.get("family_prompt_profile_term_counts"))
            )
        ),
        "family_command_pattern_term_stats": _term_stats_from_counts(
            _term_counts_from_stats(
                _term_stats_mapping(family_payload.get("family_command_pattern_term_stats"))
            )
            or _term_count_mapping(
                _term_stats_mapping(family_payload.get("family_command_pattern_counts"))
            )
        ),
        "family_constraint_term_stats": _term_stats_from_counts(
            _term_counts_from_stats(
                _term_stats_mapping(family_payload.get("family_constraint_term_stats"))
            )
            or _term_count_mapping(
                _term_stats_mapping(family_payload.get("family_constraint_counts"))
            )
        ),
        "family_prompt_profile_terms": _profile_terms(
            _stable_profile_terms_from_counts(
                _term_counts_from_stats(
                    _term_stats_mapping(family_payload.get("family_prompt_profile_term_stats"))
                )
                or _term_stats_mapping(family_payload.get("family_prompt_profile_term_counts")),
                limit=_FAMILY_PROMPT_PROFILE_LIMIT,
                min_count=_stable_profile_min_count(len(_family_replay_records(family_payload))),
            )
            or _string_list(family_payload.get("family_prompt_profile_terms")),
            limit=_FAMILY_PROMPT_PROFILE_LIMIT,
        ),
        "family_command_pattern_summary": _profile_terms(
            _stable_profile_terms_from_counts(
                _term_counts_from_stats(
                    _term_stats_mapping(family_payload.get("family_command_pattern_term_stats"))
                )
                or _term_stats_mapping(family_payload.get("family_command_pattern_counts")),
                limit=_FAMILY_COMMAND_PROFILE_LIMIT,
                min_count=_stable_profile_min_count(len(_family_replay_records(family_payload))),
            )
            or _string_list(family_payload.get("family_command_pattern_summary")),
            limit=_FAMILY_COMMAND_PROFILE_LIMIT,
        ),
        "family_constraint_summary": _constraint_terms(
            _stable_profile_terms_from_counts(
                _term_counts_from_stats(
                    _term_stats_mapping(family_payload.get("family_constraint_term_stats"))
                )
                or _term_stats_mapping(family_payload.get("family_constraint_counts")),
                limit=_FAMILY_CONSTRAINT_PROFILE_LIMIT,
                min_count=_stable_profile_min_count(len(_family_replay_records(family_payload))),
            )
            or _string_list(family_payload.get("family_constraint_summary")),
            limit=_FAMILY_CONSTRAINT_PROFILE_LIMIT,
        ),
        "family_father_question": _normalize_question_text(
            family_payload.get("family_father_question")
        )
        or None,
        "family_father_similarity_mean": family_payload.get("family_father_similarity_mean"),
        "family_runtime_score": family_payload.get("family_runtime_score"),
        "family_metric_1_mean": family_payload.get("family_metric_1_mean"),
        "family_feedback_metric": family_payload.get("family_feedback_metric"),
        "family_feedback_count": int(family_payload.get("family_feedback_count") or 0),
        "family_success_metric": family_payload.get("family_success_metric"),
        "family_record_count": replay_record_count,
        "context_group_count": len(context_groups),
    }


def _persist_local_family_state(
    family_state_path: Path,
    index_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist the local family cache plus a SQLite-backed family index."""

    resolved_family_state_path = family_state_path.resolve()
    family_state_dir = _family_state_dir(resolved_family_state_path)
    family_cache_dir = family_state_dir / DEFAULT_TRAINER_FAMILY_CACHE_DIR.name
    family_cache_dir.mkdir(parents=True, exist_ok=True)

    raw_families = index_payload.get("prompt_families")
    family_payloads = raw_families if isinstance(raw_families, list) else []
    active_family_dirs: set[Path] = set()
    thin_families: list[dict[str, Any]] = []

    for family_value in family_payloads:
        if not isinstance(family_value, Mapping):
            continue
        full_family_payload = {str(key): value for key, value in family_value.items()}
        prompt_family_id = str(full_family_payload.get("prompt_family_id") or "").strip()
        if not prompt_family_id:
            continue
        relative_family_dir = _family_cache_relative_dir(prompt_family_id)
        family_dir = family_state_dir / relative_family_dir
        active_family_dirs.add(family_dir)
        family_dir.mkdir(parents=True, exist_ok=True)

        # Preserve carried-forward replay records when an intermediate family payload was reduced
        # to a thin summary during compile/publish bookkeeping. Runtime and trainer contracts do
        # not treat an empty incoming replay set as an intentional family-history reset.
        existing_family_path = family_dir / "family.json"
        existing_replay_records = []
        existing_family_payload: dict[str, Any] | None = None
        if existing_family_path.is_file():
            try:
                loaded_existing = json.loads(existing_family_path.read_text(encoding="utf-8"))
            except Exception:
                loaded_existing = None
            if isinstance(loaded_existing, dict):
                existing_family_payload = {
                    str(key): value for key, value in loaded_existing.items()
                }
                existing_replay_records = _family_replay_records(existing_family_payload)
        if not _family_replay_records(full_family_payload) and existing_replay_records:
            full_family_payload["family_records"] = existing_replay_records
            for field_name in (
                "family_father_record",
                "family_runtime_record",
                "family_champion_record",
                "family_runtime_artifact",
            ):
                if (
                    field_name not in full_family_payload
                    and isinstance(existing_family_payload, dict)
                    and field_name in existing_family_payload
                ):
                    full_family_payload[field_name] = existing_family_payload[field_name]

        family_file_payload = {
            key: value
            for key, value in full_family_payload.items()
            if key not in {"family_path", "father_path", "record_paths", "family_record_count"}
        }
        family_file_payload["family_record_count"] = len(
            _family_replay_records(full_family_payload)
        )
        family_json_path = family_dir / "family.json"
        family_json_path.write_text(
            f"{json.dumps(family_file_payload, indent=2)}\n",
            encoding="utf-8",
        )

        father_path = family_dir / "father.json"
        father_record = _family_father_record(full_family_payload)
        if father_record is not None:
            father_path.write_text(
                f"{json.dumps(father_record, indent=2)}\n",
                encoding="utf-8",
            )
        elif father_path.exists():
            father_path.unlink()

        record_dir = family_dir / "records"
        record_dir.mkdir(parents=True, exist_ok=True)
        expected_record_paths: set[Path] = set()
        for record in _family_replay_records(full_family_payload):
            record_token = str(
                record.get("exact_snapshot_id") or _candidate_record_hash(record)
            ).strip()
            if not record_token:
                continue
            record_path = record_dir / f"{record_token}.json"
            expected_record_paths.add(record_path)
            record_path.write_text(
                f"{json.dumps(record, indent=2)}\n",
                encoding="utf-8",
            )
        for stale_record in record_dir.glob("*.json"):
            if stale_record not in expected_record_paths:
                stale_record.unlink()

        thin_entry = _strip_family_state_inline_payload(full_family_payload)
        thin_entry["family_path"] = str((relative_family_dir / "family.json").as_posix())
        if father_record is not None:
            thin_entry["father_path"] = str((relative_family_dir / "father.json").as_posix())
        thin_families.append(thin_entry)

    for stale_family_dir in family_cache_dir.iterdir():
        if stale_family_dir not in active_family_dirs:
            shutil.rmtree(stale_family_dir)

    thin_index = {
        "schema_version": index_payload.get("schema_version", TRAINER_FAMILY_STATE_SCHEMA_VERSION),
        "record_kind": index_payload.get("record_kind", TRAINER_CHAMPION_INDEX_KIND),
        "family_state_kind": index_payload.get("family_state_kind", TRAINER_FAMILY_STATE_KIND),
        "family_state_layout": "sqlite-index",
        "generated_at": index_payload.get("generated_at") or datetime.now(UTC).isoformat(),
        "prompt_families": thin_families,
    }
    resolved_family_state_path.parent.mkdir(parents=True, exist_ok=True)
    write_family_index_payload(resolved_family_state_path, thin_index)
    return thin_index


persist_local_family_state = _persist_local_family_state


def _load_champion_index(path: Path) -> dict[str, Any]:
    """Load a persisted champion index or return an empty one."""

    payload = load_family_index_payload(path)
    families = payload.get("prompt_families")
    if not isinstance(families, list):
        payload["prompt_families"] = []
        return payload
    hydrated_families: list[dict[str, Any]] = []
    for family in families:
        if not isinstance(family, Mapping):
            continue
        hydrated_families.append(_family_state_entry_to_payload(path, family))
    payload["prompt_families"] = hydrated_families
    for family in hydrated_families:
        family["family_needs_recompile"] = bool(family.get("family_needs_recompile"))
        family["family_feedback_count"] = max(0, int(family.get("family_feedback_count") or 0))
        feedback_metric = _family_feedback_metric(family)
        family["family_feedback_metric"] = feedback_metric
        family["family_success_metric"] = _family_success_metric(family)
        runtime_artifact = family.get("family_runtime_artifact")
        if isinstance(runtime_artifact, Mapping):
            runtime_artifact_payload = dict(runtime_artifact)
            if feedback_metric is not None:
                runtime_artifact_payload["feedback_metric"] = feedback_metric
                runtime_artifact_payload["feedback_count"] = family["family_feedback_count"]
            success_metric = family.get("family_success_metric")
            if isinstance(success_metric, Mapping):
                runtime_artifact_payload.setdefault(
                    "predicted_hit_rate",
                    success_metric.get("posterior_mean"),
                )
                runtime_artifact_payload.setdefault(
                    "predicted_hit_rate_lower_bound",
                    success_metric.get("lower_bound"),
                )
                runtime_artifact_payload.setdefault(
                    "prediction_uncertainty",
                    success_metric.get("uncertainty"),
                )
            family["family_runtime_artifact"] = runtime_artifact_payload
        stored_family_question = _normalize_question_text(family.get("question"))
        if stored_family_question:
            family["question"] = stored_family_question
            family["normalized_question"] = stored_family_question.casefold()
        for record_field in (
            "family_father_record",
            "family_runtime_record",
            "family_champion_record",
        ):
            candidate_record = family.get(record_field)
            if not isinstance(candidate_record, Mapping):
                continue
            normalized_record = _serialize_candidate_record(candidate_record)
            if not _trainer_candidate_record_is_supported(normalized_record):
                family[record_field] = None
                continue
            family[record_field] = normalized_record
        _refresh_prompt_family_summary(family, family.get("question") or "")
        normalized_family_records = _family_replay_records(family)
        if not normalized_family_records:
            normalized_family_records = _family_candidate_records(family)
        deduped_family_records: list[dict[str, Any]] = []
        deduped_record_index: dict[str, int] = {}
        for record in normalized_family_records:
            stable_key = _stable_family_replay_key(record)
            if not stable_key:
                deduped_family_records.append(record)
                continue
            existing_index = deduped_record_index.get(stable_key)
            if existing_index is None:
                deduped_record_index[stable_key] = len(deduped_family_records)
                deduped_family_records.append(record)
                continue
            merged_record = _merge_replayed_candidate_records(
                deduped_family_records[existing_index],
                record,
            )
            deduped_family_records[existing_index] = merged_record
        family["family_records"] = deduped_family_records
        family["family_record_count"] = len(deduped_family_records)
        family["context_groups"] = []
        _refresh_family_champion(family)
        runtime_record = _family_runtime_record(family)
        if runtime_record is not None:
            _refresh_prompt_family_summary(family, runtime_record.get("question") or "")
        elif stored_family_question:
            _refresh_prompt_family_summary(family, stored_family_question)
    return payload


def load_family_state_payload(path: Path) -> dict[str, Any]:
    """Load one persisted family-state file and hydrate its full family payloads."""

    return _load_champion_index(path)


def _seed_champion_index_from_existing_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a first family-state payload from legacy materialized candidate rows."""

    index_payload = _fresh_champion_index()
    family_by_id: dict[str, dict[str, Any]] = {}
    family_order: list[str] = []
    for record in records:
        question = _record_routing_question(record)
        if not question:
            continue
        preferred_family_id = str(record.get("prompt_family_id") or "").strip() or None
        family_payload, created_family = _find_or_create_prompt_family(
            family_by_id,
            family_order,
            question=question,
            candidate_record=record,
            preferred_family_id=preferred_family_id,
        )
        if created_family:
            family_payload["family_records"] = []
        _upsert_family_replay_record(family_payload, record)
        _refresh_family_champion(family_payload)
    index_payload["prompt_families"] = [family_by_id[family_id] for family_id in family_order]
    return index_payload


def _family_champion_record(family_payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the normalized family champion record, if any."""

    record = family_payload.get("family_champion_record")
    if not isinstance(record, Mapping):
        return None
    return _serialize_candidate_record(record)


def _family_replay_records(family_payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Return persisted replay-set records for one family in stable deduplicated order."""

    if not isinstance(family_payload, Mapping):
        return []
    raw_records = family_payload.get("family_records")
    if not isinstance(raw_records, list):
        return []
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in raw_records:
        if not isinstance(value, Mapping):
            continue
        normalized = _serialize_candidate_record(value)
        if not _trainer_candidate_record_is_supported(normalized):
            continue
        key = str(normalized.get("exact_snapshot_id") or _candidate_record_hash(normalized)).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        records.append(normalized)
    return records


def _family_runtime_record(family_payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return the current family runtime record, falling back to legacy champion state."""

    if not isinstance(family_payload, Mapping):
        return None
    record = family_payload.get("family_runtime_record")
    if isinstance(record, Mapping):
        return _serialize_candidate_record(record)
    return _family_champion_record(family_payload)


def _family_candidate_records(family_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return stable unique family-level trace records for father/runtime selection."""

    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _append_record(value: object) -> None:
        if not isinstance(value, Mapping):
            return
        normalized = _serialize_candidate_record(value)
        key = str(normalized.get("exact_snapshot_id") or _candidate_record_hash(normalized)).strip()
        if not key or key in seen:
            return
        seen.add(key)
        records.append(normalized)

    for record in _family_replay_records(family_payload):
        _append_record(record)
    if not records:
        groups = family_payload.get("context_groups")
        if isinstance(groups, list):
            for group in groups:
                if not isinstance(group, Mapping):
                    continue
                _append_record(group.get("champion_record"))
    _append_record(family_payload.get("family_runtime_record"))
    _append_record(family_payload.get("family_father_record"))
    return records


def _family_materialized_records(family_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return compile-facing answer variants aggregated from one family's replay traces."""

    replay_records = _family_replay_records(family_payload)
    if not replay_records:
        return _family_candidate_records(family_payload)
    materialized: list[dict[str, Any]] = []
    materialized_index: dict[tuple[str, str, tuple[str, ...], str], int] = {}
    for record in replay_records:
        record_key = _candidate_record_key(record)
        existing_index = materialized_index.get(record_key)
        if existing_index is None:
            materialized_index[record_key] = len(materialized)
            materialized.append(_serialize_candidate_record(record))
            continue
        materialized[existing_index] = _merge_equivalent_candidate_records(
            materialized[existing_index],
            record,
        )
    return materialized


def _record_metric_mean_score(record: Mapping[str, Any]) -> float:
    """Return the arithmetic mean of all known numeric trace metrics for one record."""

    metrics: list[float] = []
    _, _, metric_ratio = _record_metric(record)
    metrics.append(metric_ratio)
    for candidate in (
        record.get("prompt_family_similarity"),
        record.get("semantic_similarity"),
    ):
        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
            metrics.append(float(candidate))
    provenance = record.get("provenance")
    if isinstance(provenance, Mapping):
        for candidate in (
            provenance.get("prompt_family_similarity"),
            provenance.get("semantic_similarity"),
        ):
            if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                metrics.append(float(candidate))
    return round(sum(metrics) / len(metrics), 6) if metrics else 0.0


def _family_metric_1_mean(family_payload: Mapping[str, Any]) -> float | None:
    """Return the family mean hit-rate across all stored trace records."""

    candidate_records = _family_replay_records(family_payload)
    if not candidate_records:
        return None
    ratios = [_record_metric(record)[2] for record in candidate_records]
    if not ratios:
        return None
    return round(sum(ratios) / len(ratios), 6)


def _select_family_father_record(
    family_payload: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, float | None]:
    """Return the family record with the highest arithmetic mean across known metrics."""

    candidate_records = _family_candidate_records(family_payload)
    best_record: dict[str, Any] | None = None
    best_mean: float | None = None
    for record in candidate_records:
        question = _record_routing_question(record)
        if not question:
            continue
        mean_metric = _record_metric_mean_score(record)
        if best_mean is None or mean_metric > best_mean:
            best_record = record
            best_mean = mean_metric
    return best_record, best_mean


def _family_father_record(family_payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return the current routing father record for one family."""

    if not isinstance(family_payload, Mapping):
        return None
    record = family_payload.get("family_father_record")
    if isinstance(record, Mapping):
        return _serialize_candidate_record(record)
    father_record, _ = _select_family_father_record(family_payload)
    return father_record


def _record_acceptance_rank(record: Mapping[str, Any]) -> int:
    """Return an ordinal that prefers accepted traces over weaker statuses."""

    candidate_status = str(record.get("candidate_status") or "").strip().casefold()
    if candidate_status == "accepted":
        return 2
    if candidate_status == "candidate":
        return 1
    return 0


def _record_context_snapshot(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the best available persisted context snapshot for one record."""

    provenance = record.get("provenance")
    if isinstance(provenance, Mapping):
        context_snapshot = provenance.get("context_snapshot")
        if isinstance(context_snapshot, Mapping):
            return context_snapshot
    return {}


def _rebuild_family_context_groups(family_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return compatibility context-group summaries derived from stored family records."""

    candidate_records = _family_replay_records(family_payload)
    if not candidate_records:
        groups = family_payload.get("context_groups")
        if isinstance(groups, list):
            return [dict(group) for group in groups if isinstance(group, Mapping)]
        return []

    prompt_family_id = str(family_payload.get("prompt_family_id") or "").strip()
    context_group_id = f"cg-{_stable_hash(prompt_family_id or 'family')}"
    aggregate_sources: list[str] = []
    aggregate_fingerprints: list[str] = []
    retrieval_mode = ""
    mode = ""
    context_field = ""
    source_count = 0
    context_count = 0
    top_k: int | None = None
    trace_count = 0
    support_by_record_key: dict[str, int] = {}
    group_champion_record: dict[str, Any] | None = None
    group_champion_score = 0.0
    materialized_records = _family_materialized_records(family_payload)

    for record in candidate_records:
        trace_count += 1
        support_key = _candidate_record_hash(record)
        support_by_record_key[support_key] = max(
            support_by_record_key.get(support_key, 0),
            max(0, int(record.get("support_count") or 0)),
        )
        context_snapshot = _record_context_snapshot(record)
        aggregate_sources = _normalized_source_tokens(
            [
                *aggregate_sources,
                *(
                    str(source).strip()
                    for source in context_snapshot.get("sources", [])
                    if str(source).strip()
                ),
                *(
                    str(source).strip()
                    for source in record.get("benchmark_context_sources", [])
                    if str(source).strip()
                ),
            ]
        )
        aggregate_fingerprints = _normalized_source_tokens(
            [
                *aggregate_fingerprints,
                *(
                    str(token).strip()
                    for token in context_snapshot.get("evidence_fingerprints", [])
                    if str(token).strip()
                ),
            ]
        )
        if not retrieval_mode:
            retrieval_mode = str(context_snapshot.get("retrieval_mode") or "").strip()
        if not mode:
            mode = str(context_snapshot.get("mode") or "").strip()
        if not context_field:
            context_field = str(context_snapshot.get("context_field") or "").strip()
        source_count = max(
            source_count,
            int(context_snapshot.get("source_count") or 0),
            len(aggregate_sources),
        )
        context_count = max(
            context_count,
            int(context_snapshot.get("context_count") or 0),
            len(aggregate_fingerprints),
        )
        candidate_top_k = _coerce_int(context_snapshot.get("top_k"))
        if candidate_top_k is not None:
            top_k = max(top_k or candidate_top_k, candidate_top_k)

    for record in materialized_records:
        candidate_group_score = _record_metric_mean_score(record)
        if group_champion_record is None or (
            candidate_group_score,
            max(0, int(record.get("support_count") or 0)),
            _record_acceptance_rank(record),
            _candidate_recorded_at(record),
        ) > (
            group_champion_score,
            max(0, int(group_champion_record.get("support_count") or 0)),
            _record_acceptance_rank(group_champion_record),
            _candidate_recorded_at(group_champion_record),
        ):
            group_champion_record = _serialize_candidate_record(record)
            group_champion_score = candidate_group_score

    return [
        {
            "context_group_id": context_group_id,
            "sources": aggregate_sources,
            "evidence_fingerprints": aggregate_fingerprints,
            "evidence_count": len(aggregate_fingerprints),
            "retrieval_mode": retrieval_mode,
            "mode": mode,
            "context_field": context_field,
            "source_count": source_count,
            "context_count": context_count,
            "top_k": top_k,
            "trace_count": trace_count,
            "support_by_record_key": support_by_record_key,
            "champion_score": group_champion_score if group_champion_record is not None else None,
            "champion_record": group_champion_record,
        }
    ]


def _refresh_family_champion(family_payload: dict[str, Any]) -> tuple[bool, str | None, str | None]:
    """Refresh the family runtime/father records directly from stored trace records."""

    previous_record = _family_runtime_record(family_payload) or _family_champion_record(
        family_payload
    )
    previous_snapshot_id = (
        str(previous_record.get("exact_snapshot_id") or "").strip()
        if isinstance(previous_record, Mapping)
        else None
    ) or None
    candidate_records = _family_materialized_records(family_payload)
    if not candidate_records:
        family_payload["family_runtime_context_group_id"] = None
        family_payload["family_runtime_score"] = None
        family_payload["family_metric_1_mean"] = None
        family_payload["family_success_metric"] = _family_success_metric(family_payload)
        family_payload["family_runtime_record"] = None
        family_payload["family_champion_context_group_id"] = None
        family_payload["family_champion_score"] = None
        family_payload["family_champion_record"] = None
        family_payload["context_groups"] = _rebuild_family_context_groups(family_payload)
        _refresh_prompt_family_summary(family_payload, "")
        return False, previous_snapshot_id, None

    best_runtime_record = max(
        candidate_records,
        key=lambda record: (
            _record_metric(record)[2],
            max(0, int(record.get("support_count") or 0)),
            _record_acceptance_rank(record),
            _record_metric_mean_score(record),
            _candidate_recorded_at(record),
        ),
    )
    runtime_hits, runtime_total, runtime_ratio = _record_metric(best_runtime_record)
    context_groups = _rebuild_family_context_groups(family_payload)
    runtime_context_group_id = None
    if context_groups:
        runtime_context_group_id = (
            str(context_groups[0].get("context_group_id") or "").strip() or None
        )
    family_payload["family_runtime_context_group_id"] = None
    family_payload["family_runtime_score"] = runtime_ratio
    family_payload["family_metric_1_mean"] = _family_metric_1_mean(family_payload)
    family_payload["family_success_metric"] = _family_success_metric(family_payload)
    family_payload["family_runtime_record"] = _serialize_candidate_record(best_runtime_record)
    family_payload["family_runtime_context_group_id"] = runtime_context_group_id
    family_payload["family_champion_context_group_id"] = runtime_context_group_id
    family_payload["family_champion_score"] = runtime_ratio
    family_payload["family_champion_record"] = _serialize_candidate_record(best_runtime_record)
    family_payload["context_groups"] = context_groups
    family_payload["family_runtime_metric"] = {
        "metric_hits": runtime_hits,
        "metric_total": runtime_total,
        "hit_rate": runtime_ratio,
    }
    _refresh_prompt_family_summary(family_payload, best_runtime_record.get("question") or "")
    current_snapshot_id = str(best_runtime_record.get("exact_snapshot_id") or "").strip() or None
    changed = previous_snapshot_id != current_snapshot_id
    return changed, previous_snapshot_id, current_snapshot_id


def _materialize_family_champion_records(index_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the current compile-facing family champion records in stable order."""

    records: list[dict[str, Any]] = []
    families = index_payload.get("prompt_families")
    if not isinstance(families, list):
        return records
    for family in families:
        if not isinstance(family, Mapping):
            continue
        runtime_record = _family_runtime_record(family)
        if runtime_record is None:
            continue
        records.append(runtime_record)
    return records


def summarize_family_state(path: Path) -> dict[str, Any]:
    """Return one compact summary of the current family-state runtime set."""

    index_payload = _load_champion_index(path)
    prompt_family_ids: list[str] = []
    family_trace_record_paths: list[str] = []
    family_exact_snapshot_ids: list[str] = []
    family_record_hashes: list[str] = []
    dirty_family_ids: list[str] = []
    seen_family_ids: set[str] = set()
    seen_trace_paths: set[str] = set()
    seen_snapshot_ids: set[str] = set()
    seen_record_hashes: set[str] = set()
    seen_dirty_family_ids: set[str] = set()
    families = index_payload.get("prompt_families")
    family_records: list[dict[str, Any]] = []
    if isinstance(families, list):
        for family in families:
            if not isinstance(family, Mapping):
                continue
            prompt_family_id = str(family.get("prompt_family_id") or "").strip()
            if (
                bool(family.get("family_needs_recompile"))
                and prompt_family_id
                and prompt_family_id not in seen_dirty_family_ids
            ):
                seen_dirty_family_ids.add(prompt_family_id)
                dirty_family_ids.append(prompt_family_id)
            replay_records = _family_replay_records(family)
            if replay_records:
                family_records.extend(replay_records)
            else:
                runtime_record = _family_runtime_record(family)
                if runtime_record is not None:
                    family_records.append(runtime_record)
            if prompt_family_id and prompt_family_id not in seen_family_ids:
                seen_family_ids.add(prompt_family_id)
                prompt_family_ids.append(prompt_family_id)
    for record in family_records:
        prompt_family_id = str(record.get("prompt_family_id") or "").strip()
        if prompt_family_id and prompt_family_id not in seen_family_ids:
            seen_family_ids.add(prompt_family_id)
            prompt_family_ids.append(prompt_family_id)
        provenance = record.get("provenance")
        if isinstance(provenance, Mapping):
            trace_record_path = str(provenance.get("trace_record_path") or "").strip()
            if trace_record_path and trace_record_path not in seen_trace_paths:
                seen_trace_paths.add(trace_record_path)
                family_trace_record_paths.append(trace_record_path)
        snapshot_id = str(record.get("exact_snapshot_id") or "").strip()
        if snapshot_id and snapshot_id not in seen_snapshot_ids:
            seen_snapshot_ids.add(snapshot_id)
            family_exact_snapshot_ids.append(snapshot_id)
        record_hash = _candidate_record_hash(record)
        if record_hash not in seen_record_hashes:
            seen_record_hashes.add(record_hash)
            family_record_hashes.append(record_hash)
    return {
        "candidate_count": len(family_records),
        "family_candidate_count": len(family_records),
        "dirty_family_count": len(dirty_family_ids),
        "dirty_family_ids": dirty_family_ids,
        "prompt_family_ids": prompt_family_ids,
        "family_trace_record_paths": family_trace_record_paths,
        "family_exact_snapshot_ids": family_exact_snapshot_ids,
        "family_record_hashes": family_record_hashes,
    }


def summarize_champion_index(path: Path) -> dict[str, Any]:
    """Compatibility wrapper that returns the family-state summary."""

    summary = summarize_family_state(path)
    return {
        **summary,
        "champion_trace_record_paths": list(summary.get("family_trace_record_paths", [])),
        "champion_exact_snapshot_ids": list(summary.get("family_exact_snapshot_ids", [])),
        "champion_record_hashes": list(summary.get("family_record_hashes", [])),
    }


def _normalize_materialized_candidate_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one persisted trainer-candidate record for future trainer cycles."""

    tags = _dedupe_tags(record.get("tags", []))
    tag_set = {tag.casefold() for tag in tags}
    expected_sources = [
        str(source).strip() for source in record.get("expected_sources", []) if str(source).strip()
    ]
    if "trainer-candidate" in tag_set:
        # Imported worker traces are global candidates, not repo-local retrieval benchmarks.
        expected_sources = []

    normalized_answer, answer_metadata = _normalize_imported_training_answer(
        record.get("expected_answer"),
        None,
    )
    provenance = record.get("provenance")
    existing_answer_metadata: Mapping[str, Any] | None = None
    if isinstance(provenance, Mapping):
        candidate_metadata = provenance.get("answer_normalization")
        if isinstance(candidate_metadata, Mapping):
            existing_answer_metadata = candidate_metadata
    if (
        existing_answer_metadata is not None
        and str(record.get("expected_answer") or "").strip() == normalized_answer
    ):
        answer_metadata = dict(existing_answer_metadata)
    original_prompt = _normalize_question_text(record.get("original_prompt"))
    reformulated_prompt = _normalize_question_text(record.get("reformulated_prompt"))
    normalized: dict[str, Any] = {
        "question": _routing_question(
            question=record.get("question"),
            original_prompt=original_prompt,
            reformulated_prompt=reformulated_prompt,
        ),
        "expected_answer": normalized_answer,
        "tags": tags,
        "expected_sources": expected_sources,
        "benchmark_context": [
            str(text).strip() for text in record.get("benchmark_context", []) if str(text).strip()
        ],
        "benchmark_context_sources": [
            str(source).strip()
            for source in record.get("benchmark_context_sources", [])
            if str(source).strip()
        ],
        "command_trace": _ordered_unique_command_trace(record.get("command_trace", [])),
        "trainer_signal_kind": _normalize_trainer_signal_kind(record.get("trainer_signal_kind")),
    }
    if original_prompt:
        normalized["original_prompt"] = original_prompt
    if reformulated_prompt:
        normalized["reformulated_prompt"] = reformulated_prompt
    candidate_status = str(record.get("candidate_status") or "").strip()
    if candidate_status:
        normalized["candidate_status"] = candidate_status
    if isinstance(provenance, Mapping):
        normalized_provenance = dict(provenance)
        for field_name in ("question", "original_prompt", "reformulated_prompt"):
            if field_name in normalized_provenance:
                normalized_value = _normalize_question_text(normalized_provenance.get(field_name))
                if normalized_value:
                    normalized_provenance[field_name] = normalized_value
        if "command_trace" in normalized_provenance:
            normalized_provenance["command_trace"] = _ordered_unique_command_trace(
                normalized_provenance.get("command_trace", [])
            )
        normalized_provenance["answer_normalization"] = answer_metadata
        normalized["provenance"] = normalized_provenance
    for field_name in (
        "metric_hits",
        "metric_total",
        "metric_ratio",
        "quality_score",
        "support_count",
    ):
        if record.get(field_name) not in (None, ""):
            normalized[field_name] = record.get(field_name)
    return normalized


def _normalize_combined_training_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one base/candidate record for the generated trainer compile dataset."""

    normalized = _normalize_materialized_candidate_record(record)
    combined = {
        "question": str(
            normalized.get("question")
            or normalized.get("original_prompt")
            or normalized.get("reformulated_prompt")
            or ""
        ).strip(),
        "expected_answer": str(normalized.get("expected_answer") or "").strip(),
        "tags": _dedupe_tags(normalized.get("tags", [])),
        "expected_sources": [
            str(source).strip()
            for source in normalized.get("expected_sources", [])
            if str(source).strip()
        ],
        "benchmark_context": [
            str(text).strip()
            for text in normalized.get("benchmark_context", [])
            if str(text).strip()
        ],
        "benchmark_context_sources": [
            str(source).strip()
            for source in normalized.get("benchmark_context_sources", [])
            if str(source).strip()
        ],
        "command_trace": _ordered_unique_command_trace(normalized.get("command_trace", [])),
    }
    original_prompt = str(normalized.get("original_prompt") or "").strip()
    reformulated_prompt = str(normalized.get("reformulated_prompt") or "").strip()
    if original_prompt:
        combined["original_prompt"] = original_prompt
    if reformulated_prompt:
        combined["reformulated_prompt"] = reformulated_prompt
    return combined


def _candidate_materialization_signature(record: Mapping[str, Any] | None) -> str | None:
    """Return the compile-facing signature for one champion record."""

    if not isinstance(record, Mapping):
        return None
    normalized = _normalize_combined_training_record(record)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _ordered_unique_texts(values: Sequence[object]) -> list[str]:
    """Return stable ordered unique non-empty strings."""

    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized:
            continue
        folded = normalized.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        ordered.append(normalized)
    return ordered


def _ordered_unique_command_trace(values: object) -> list[dict[str, Any]]:
    """Return stable ordered unique command-trace steps."""

    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, Mapping):
            continue
        normalized = {str(key): item for key, item in value.items()}
        for field_name in ("text", "content", "question", "original_prompt", "reformulated_prompt"):
            field_value = normalized.get(field_name)
            if isinstance(field_value, str):
                cleaned = _normalize_question_text(field_value)
                normalized[field_name] = cleaned if cleaned else field_value.strip()
        token = json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        if token in seen:
            continue
        seen.add(token)
        ordered.append(normalized)
    return ordered


def _trainer_candidate_record_is_supported(record: Mapping[str, Any]) -> bool:
    """Return whether one materialized trainer-candidate row is eligible for champion review."""

    del record
    return True


def _candidate_benchmark_context_richness(record: Mapping[str, Any]) -> tuple[int, int, int, int]:
    """Return one lexicographic richness score for stored benchmark context."""

    benchmark_context = _ordered_unique_texts(record.get("benchmark_context", []))
    benchmark_context_sources = _ordered_unique_texts(record.get("benchmark_context_sources", []))
    return (
        len(benchmark_context),
        len(benchmark_context_sources),
        sum(len(text) for text in benchmark_context),
        sum(len(source) for source in benchmark_context_sources),
    )


def _candidate_recorded_at(record: Mapping[str, Any]) -> str:
    """Return the provenance recorded-at timestamp for one candidate record."""

    provenance = record.get("provenance")
    if not isinstance(provenance, Mapping):
        return ""
    return str(provenance.get("recorded_at") or "").strip()


def _merge_equivalent_candidate_records(
    current_record: Mapping[str, Any],
    candidate_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge two same-key candidate variants, preferring richer benchmark context."""

    current_serialized = _serialize_candidate_record(current_record)
    candidate_serialized = _serialize_candidate_record(candidate_record)
    current_richness = _candidate_benchmark_context_richness(current_serialized)
    candidate_richness = _candidate_benchmark_context_richness(candidate_serialized)
    prefer_candidate = candidate_richness > current_richness or (
        candidate_richness == current_richness
        and _candidate_recorded_at(candidate_serialized)
        > _candidate_recorded_at(current_serialized)
    )
    merged = dict(candidate_serialized if prefer_candidate else current_serialized)
    current_hits, current_total, _ = _record_metric(current_serialized)
    candidate_hits, candidate_total, _ = _record_metric(candidate_serialized)
    merged_hits = current_hits + candidate_hits
    merged_total = current_total + candidate_total
    merged["benchmark_context"] = _ordered_unique_texts(
        [
            *current_serialized.get("benchmark_context", []),
            *candidate_serialized.get("benchmark_context", []),
        ]
    )
    merged["benchmark_context_sources"] = _ordered_unique_texts(
        [
            *current_serialized.get("benchmark_context_sources", []),
            *candidate_serialized.get("benchmark_context_sources", []),
        ]
    )
    merged["command_trace"] = _ordered_unique_command_trace(
        [
            *current_serialized.get("command_trace", []),
            *candidate_serialized.get("command_trace", []),
        ]
    )
    merged["metric_hits"] = merged_hits
    merged["metric_total"] = merged_total
    merged["metric_ratio"] = _metric_ratio(merged_hits, merged_total)
    merged["quality_score"] = merged["metric_ratio"]
    merged["support_count"] = max(0, int(current_serialized.get("support_count") or 0)) + max(
        0,
        int(candidate_serialized.get("support_count") or 0),
    )
    merged["original_prompt"] = str(
        merged.get("original_prompt")
        or candidate_serialized.get("original_prompt")
        or current_serialized.get("original_prompt")
        or ""
    ).strip()
    merged["original_prompt"] = _normalize_question_text(merged["original_prompt"])
    merged["reformulated_prompt"] = str(
        merged.get("reformulated_prompt")
        or candidate_serialized.get("reformulated_prompt")
        or current_serialized.get("reformulated_prompt")
        or ""
    ).strip()
    merged["reformulated_prompt"] = _normalize_question_text(merged["reformulated_prompt"])
    provenance = merged.get("provenance")
    if isinstance(provenance, Mapping):
        merged_provenance = dict(provenance)
        merged_provenance["benchmark_context_count"] = len(merged["benchmark_context"])
        merged_provenance["metric_hits"] = merged_hits
        merged_provenance["metric_total"] = merged_total
        merged_provenance["metric_ratio"] = merged["metric_ratio"]
        merged["provenance"] = merged_provenance
    return merged


def _stable_family_replay_key(record: Mapping[str, Any]) -> str:
    """Return one stable dedupe key for logical family replay records."""

    provenance = record.get("provenance")
    if isinstance(provenance, Mapping):
        stable_source_identity = str(provenance.get("stable_source_identity") or "").strip()
        if stable_source_identity:
            return stable_source_identity
        source_queue_item_path = str(provenance.get("source_queue_item_path") or "").strip()
        if source_queue_item_path:
            canonical_queue_item_path = _canonical_trace_record_path(source_queue_item_path)
            return f"trace-file:{Path(canonical_queue_item_path).name}"
        trace_record_path = str(provenance.get("trace_record_path") or "").strip()
        canonical_trace_path = _canonical_trace_record_path(trace_record_path)
        if canonical_trace_path:
            return f"trace-file:{Path(canonical_trace_path).name}"
    exact_snapshot_id = str(record.get("exact_snapshot_id") or "").strip()
    if exact_snapshot_id:
        return exact_snapshot_id
    return str(_candidate_record_hash(record)).strip()


def _merge_replayed_candidate_records(
    current_record: Mapping[str, Any],
    candidate_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge two re-imported copies of the same logical trace without double-counting it."""

    current_serialized = _serialize_candidate_record(current_record)
    candidate_serialized = _serialize_candidate_record(candidate_record)
    current_richness = _candidate_benchmark_context_richness(current_serialized)
    candidate_richness = _candidate_benchmark_context_richness(candidate_serialized)
    prefer_candidate = candidate_richness > current_richness or (
        candidate_richness == current_richness
        and _candidate_recorded_at(candidate_serialized)
        > _candidate_recorded_at(current_serialized)
    )
    return dict(candidate_serialized if prefer_candidate else current_serialized)


def _training_candidate_from_trace_record(
    payload: Mapping[str, Any],
    *,
    include_statuses: set[str],
) -> tuple[dict[str, Any] | None, str | None]:
    """Build one training-candidate record from an imported trace record."""

    question = str(payload.get("question") or "").strip()
    expected_answer, answer_metadata = _normalize_imported_training_answer(
        payload.get("answer"),
        payload.get("response_text"),
    )
    trace = payload.get("trace")
    trace_mapping = trace if isinstance(trace, Mapping) else {}
    outcome = payload.get("outcome")
    outcome_mapping = outcome if isinstance(outcome, Mapping) else {}
    acceptance_status = str(outcome_mapping.get("acceptance_status") or "").strip().lower()

    if not question:
        return None, "missing-question"
    if not expected_answer:
        return None, "missing-answer"
    if include_statuses and acceptance_status and acceptance_status not in include_statuses:
        return None, "excluded-status"

    context_snapshot = _trace_context_snapshot(payload, trace_mapping, outcome_mapping)
    original_prompt = str(context_snapshot.get("original_prompt") or "").strip()
    reformulated_prompt = str(context_snapshot.get("reformulated_prompt") or "").strip()
    question = _routing_question(
        question=context_snapshot.get("question"),
        original_prompt=original_prompt,
        reformulated_prompt=reformulated_prompt,
    )
    command_trace = _ordered_unique_command_trace(context_snapshot.get("command_trace", []))
    if not question:
        return None, "missing-question"
    prompt_family_id = _prompt_family_id(question)
    benchmark_context, benchmark_context_sources = _extract_benchmark_context(payload)
    trace_record_path = str(payload.get("trace_record_path") or "")
    source_identity = _stable_trace_source_identity(
        payload,
        trace_record_path=trace_record_path,
    )
    exact_snapshot_id = _exact_snapshot_id(
        question=question,
        expected_answer=expected_answer,
        source_identity=source_identity,
        trace_record_path=trace_record_path,
        recorded_at=str(trace_mapping.get("recorded_at") or ""),
        context_snapshot=context_snapshot,
    )
    observed_sources = list(context_snapshot.get("sources", []))
    metric_hits, metric_total, metric_ratio = _trace_hit_total_metric(
        trace_mapping,
        context_snapshot,
    )
    trainer_signal_kind = _normalize_trainer_signal_kind(
        payload.get("trainer_signal_kind") or trace_mapping.get("trainer_signal_kind")
    )
    tags = _dedupe_tags(
        [
            "trainer-candidate",
            str(trace_mapping.get("mode") or ""),
            str(trace_mapping.get("retrieval_mode") or ""),
            acceptance_status,
            str(outcome_mapping.get("method") or ""),
            str(outcome_mapping.get("backend") or ""),
        ]
    )

    candidate_record = {
        "question": question,
        "original_prompt": original_prompt,
        "reformulated_prompt": reformulated_prompt or question,
        "expected_answer": expected_answer,
        "tags": tags,
        # Imported worker traces may originate from arbitrary repositories, so the global
        # trainer keeps their source paths in provenance instead of turning them into
        # repo-local retrieval benchmarks.
        "expected_sources": [],
        "benchmark_context": benchmark_context,
        "benchmark_context_sources": benchmark_context_sources,
        "command_trace": command_trace,
        "candidate_status": acceptance_status or None,
        "prompt_family_id": prompt_family_id,
        "exact_snapshot_id": exact_snapshot_id,
        "quality_score": metric_ratio,
        "metric_hits": metric_hits,
        "metric_total": metric_total,
        "metric_ratio": metric_ratio,
        "support_count": 1,
        "trainer_signal_kind": trainer_signal_kind,
        "provenance": {
            "trace_record_path": trace_record_path,
            "source_queue_item_path": str(payload.get("source_queue_item_path") or ""),
            "source_trace_name": str(payload.get("source_trace_name") or ""),
            "source_batch_name": str(payload.get("source_batch_name") or ""),
            "stable_source_identity": source_identity,
            "source_command": str(payload.get("source_command") or ""),
            "original_prompt": original_prompt,
            "reformulated_prompt": reformulated_prompt or question,
            "command_trace": command_trace,
            "observed_sources": observed_sources,
            "recorded_at": str(trace_mapping.get("recorded_at") or ""),
            "mode": str(trace_mapping.get("mode") or ""),
            "retrieval_mode": str(trace_mapping.get("retrieval_mode") or ""),
            "bundle_version": str(trace_mapping.get("bundle_version") or ""),
            "overlay_path": str(trace_mapping.get("overlay_path") or ""),
            "method": str(outcome_mapping.get("method") or ""),
            "backend": str(outcome_mapping.get("backend") or ""),
            "execution_status": str(outcome_mapping.get("execution_status") or ""),
            "acceptance_status": acceptance_status or None,
            "used_baseline_fallback": outcome_mapping.get("used_baseline_fallback"),
            "context_snapshot": context_snapshot,
            "benchmark_context_count": len(benchmark_context),
            "answer_normalization": answer_metadata,
            "metric_hits": metric_hits,
            "metric_total": metric_total,
            "metric_ratio": metric_ratio,
            "trainer_signal_kind": trainer_signal_kind,
        },
    }
    if not _trainer_candidate_record_is_supported(candidate_record):
        return None, "unsupported-benchmark-context"
    return candidate_record, None


def _upsert_family_replay_record(
    family_payload: dict[str, Any],
    record: Mapping[str, Any],
) -> None:
    """Persist or refresh one replay-set record inside one family payload."""

    normalized = _serialize_candidate_record(record)
    if not _trainer_candidate_record_is_supported(normalized):
        return
    raw_records = family_payload.get("family_records")
    if not isinstance(raw_records, list):
        raw_records = []
        family_payload["family_records"] = raw_records
    candidate_key = _stable_family_replay_key(normalized)
    if not candidate_key:
        raw_records.append(normalized)
        return
    for index, existing in enumerate(raw_records):
        if not isinstance(existing, Mapping):
            continue
        existing_normalized = _serialize_candidate_record(existing)
        existing_key = _stable_family_replay_key(existing_normalized)
        if existing_key != candidate_key:
            continue
        if (
            str(existing_normalized.get("exact_snapshot_id") or "").strip()
            == str(normalized.get("exact_snapshot_id") or "").strip()
        ):
            raw_records[index] = _merge_equivalent_candidate_records(
                existing_normalized,
                normalized,
            )
        else:
            raw_records[index] = _merge_replayed_candidate_records(
                existing_normalized,
                normalized,
            )
        return
    raw_records.append(normalized)


def materialize_training_candidates(
    root: Path,
    *,
    trace_paths: Sequence[Path | str] | None = None,
    output_path: Path,
    summary_path: Path,
    family_state_path: Path | None = DEFAULT_TRAINER_FAMILY_STATE_PATH,
    champion_index_path: Path | None = None,
    include_statuses: Sequence[str] = ("accepted", "candidate"),
    seed_existing_output: bool = True,
    upload_remote_state: bool = True,
) -> dict[str, Any]:
    """Materialize trainer-side DSPy training candidates from imported trace records."""

    resolved_root = root.resolve()
    resolved_output_path = output_path if output_path.is_absolute() else resolved_root / output_path
    resolved_summary_path = (
        summary_path if summary_path.is_absolute() else resolved_root / summary_path
    )
    effective_family_state_path = family_state_path or DEFAULT_TRAINER_FAMILY_STATE_PATH
    resolved_family_state_path = (
        effective_family_state_path
        if effective_family_state_path.is_absolute()
        else resolved_root / effective_family_state_path
    )
    existing_family_state_path = resolved_family_state_path
    resolved_champion_index_path = None
    if champion_index_path is not None:
        resolved_champion_index_path = (
            champion_index_path
            if champion_index_path.is_absolute()
            else resolved_root / champion_index_path
        )
    else:
        resolved_champion_index_path = (
            resolved_root / "artifacts" / "trainer" / "champion-index.json"
        )
    if (
        not resolved_family_state_path.is_file()
        and resolved_champion_index_path != resolved_family_state_path
        and resolved_champion_index_path.is_file()
    ):
        existing_family_state_path = resolved_champion_index_path
    candidate_paths: list[Path]
    if trace_paths is not None:
        candidate_paths = []
        for trace_path in trace_paths:
            path = Path(str(trace_path))
            candidate_paths.append(path if path.is_absolute() else resolved_root / path)
    else:
        candidate_paths = sorted(
            (resolved_root / "artifacts" / "traces" / "imported").glob("*.json")
        )

    normalized_statuses = {
        str(status).strip().lower() for status in include_statuses if str(status).strip()
    }
    loaded_records: list[dict[str, Any]] = []
    skipped_reasons: dict[str, int] = {}
    invalid_trace_paths: list[str] = []
    for candidate_path in candidate_paths:
        if not candidate_path.is_file():
            invalid_trace_paths.append(str(candidate_path))
            skipped_reasons["missing-trace-path"] = skipped_reasons.get("missing-trace-path", 0) + 1
            continue
        payload = load_json_object(candidate_path)
        candidate_record, skip_reason = _training_candidate_from_trace_record(
            payload,
            include_statuses=normalized_statuses,
        )
        if candidate_record is None:
            reason = skip_reason or "unknown"
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
            continue
        loaded_records.append(candidate_record)
    loaded_records.sort(
        key=lambda record: (
            _candidate_recorded_at(record),
            str(record.get("exact_snapshot_id") or ""),
            str(record.get("question") or ""),
        )
    )

    existing_records: list[dict[str, Any]] = []
    if seed_existing_output and resolved_output_path.is_file():
        existing_payload = yaml.safe_load(resolved_output_path.read_text(encoding="utf-8")) or []
        if isinstance(existing_payload, list):
            existing_records = [
                normalized
                for record in existing_payload
                if isinstance(record, Mapping)
                if _trainer_candidate_record_is_supported(
                    normalized := _normalize_materialized_candidate_record(record)
                )
            ]

    champion_index = _load_champion_index(existing_family_state_path)
    if not champion_index.get("prompt_families") and existing_records:
        champion_index = _seed_champion_index_from_existing_records(existing_records)
    families_payload = champion_index.get("prompt_families")
    if not isinstance(families_payload, list):
        families_payload = []
        champion_index["prompt_families"] = families_payload

    family_by_id: dict[str, dict[str, Any]] = {}
    family_order: list[str] = []
    seen_snapshot_ids: set[str] = set()
    for family_payload in families_payload:
        if not isinstance(family_payload, dict):
            continue
        family_id = str(family_payload.get("prompt_family_id") or "").strip()
        if not family_id:
            continue
        family_by_id[family_id] = family_payload
        family_order.append(family_id)
        for context_group in family_payload.get("context_groups", []):
            if not isinstance(context_group, Mapping):
                continue
            champion_record = context_group.get("champion_record")
            if isinstance(champion_record, Mapping):
                snapshot_id = str(champion_record.get("exact_snapshot_id") or "").strip()
                if snapshot_id:
                    seen_snapshot_ids.add(snapshot_id)
    preexisting_dirty_family_ids = {
        str(family_payload.get("prompt_family_id") or "").strip()
        for family_payload in family_by_id.values()
        if bool(family_payload.get("family_needs_recompile"))
    }

    duplicate_count = 0
    replaced_count = 0
    new_candidate_count = 0
    feedback_trace_count = 0
    new_context_group_count = 0
    new_prompt_family_count = 0
    families_with_new_candidates: set[str] = set()
    families_with_replacements: set[str] = set()
    families_with_feedback: set[str] = set()
    prompt_family_count_before = len(family_by_id)
    for record in loaded_records:
        prompt_family_id_hint = str(record.get("prompt_family_id") or "").strip()
        exact_snapshot_id = str(record.get("exact_snapshot_id") or "").strip()
        question = _normalize_question_text(record.get("question"))
        trainer_signal_kind = _normalize_trainer_signal_kind(record.get("trainer_signal_kind"))
        if not exact_snapshot_id or not question:
            continue
        if exact_snapshot_id in seen_snapshot_ids:
            duplicate_count += 1
            continue
        seen_snapshot_ids.add(exact_snapshot_id)

        family_payload, created_family = _find_or_create_prompt_family(
            family_by_id,
            family_order,
            question=question,
            candidate_record=record,
            preferred_family_id=prompt_family_id_hint or None,
        )
        if created_family:
            new_prompt_family_count += 1
        prompt_family_id = str(family_payload.get("prompt_family_id") or "").strip()
        if trainer_signal_kind == "feedback_trace":
            family_payload["family_needs_recompile"] = (
                bool(family_payload.get("family_needs_recompile")) and not created_family
            )
            serialized_record = _serialize_candidate_record(record)
            serialized_record["prompt_family_id"] = prompt_family_id
            serialized_record["trainer_signal_kind"] = "feedback_trace"
            _apply_family_feedback_trace(family_payload, serialized_record)
            families_with_feedback.add(prompt_family_id)
            feedback_trace_count += 1
            continue

        family_payload["family_needs_recompile"] = True

        previous_family_record = _family_champion_record(family_payload)
        previous_family_key = (
            _candidate_record_key(previous_family_record)
            if previous_family_record is not None
            else None
        )
        previous_family_signature = (
            _candidate_materialization_signature(previous_family_record)
            if previous_family_record is not None
            else None
        )

        serialized_record = _serialize_candidate_record(record)
        serialized_record["prompt_family_id"] = prompt_family_id
        _upsert_family_replay_record(family_payload, serialized_record)

        family_changed, _, _ = _refresh_family_champion(family_payload)
        current_family_record = _family_champion_record(family_payload)
        current_family_signature = (
            _candidate_materialization_signature(current_family_record)
            if current_family_record is not None
            else None
        )
        if previous_family_record is None and current_family_record is not None:
            families_with_new_candidates.add(prompt_family_id)
        elif (
            previous_family_signature is not None
            and current_family_signature is not None
            and previous_family_signature != current_family_signature
        ):
            families_with_new_candidates.add(prompt_family_id)
            families_with_replacements.add(prompt_family_id)
        elif family_changed and current_family_record is not None and previous_family_key is None:
            families_with_new_candidates.add(prompt_family_id)

    champion_index["generated_at"] = datetime.now(UTC).isoformat()
    champion_index["prompt_families"] = [family_by_id[family_id] for family_id in family_order]
    merged_records = _materialize_family_champion_records(champion_index)
    new_candidate_count = len(families_with_new_candidates)
    replaced_count = len(families_with_replacements)

    _persist_local_family_state(
        resolved_family_state_path,
        champion_index,
    )
    remote_family_state = (
        upload_remote_family_state(
            resolved_root,
            family_state_path=resolved_family_state_path,
        )
        if upload_remote_state and bool(loaded_records)
        else None
    )
    family_state_summary = summarize_family_state(resolved_family_state_path)
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_output_path.write_text(
        yaml.safe_dump(merged_records, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    summary: dict[str, Any] = {
        "candidate_count": len(merged_records),
        "family_candidate_count": int(family_state_summary.get("family_candidate_count") or 0),
        "dirty_family_count": int(family_state_summary.get("dirty_family_count") or 0),
        "dirty_family_ids": list(family_state_summary.get("dirty_family_ids", [])),
        "preexisting_dirty_family_count": len(preexisting_dirty_family_ids),
        "preexisting_dirty_family_ids": sorted(preexisting_dirty_family_ids),
        "new_candidate_count": new_candidate_count,
        "feedback_trace_count": feedback_trace_count,
        "input_trace_count": len(candidate_paths),
        "loaded_candidate_count": len(loaded_records),
        "duplicate_count": duplicate_count,
        "replaced_count": replaced_count,
        "families_with_feedback": sorted(families_with_feedback),
        "family_count": len(family_by_id),
        "prompt_family_count": len(family_by_id),
        "prompt_family_ids": list(family_state_summary.get("prompt_family_ids", [])),
        "family_trace_record_paths": list(
            family_state_summary.get("family_trace_record_paths", [])
        ),
        "family_exact_snapshot_ids": list(
            family_state_summary.get("family_exact_snapshot_ids", [])
        ),
        "family_record_hashes": list(family_state_summary.get("family_record_hashes", [])),
        "new_prompt_family_count": max(
            new_prompt_family_count,
            max(0, len(family_by_id) - prompt_family_count_before),
        ),
        "context_group_count": sum(
            1 for family_payload in family_by_id.values() if _family_replay_records(family_payload)
        ),
        "new_context_group_count": max(
            new_context_group_count,
            max(0, len(families_with_new_candidates)),
        ),
        "skipped_reasons": dict(sorted(skipped_reasons.items())),
        "include_statuses": sorted(normalized_statuses),
        "trace_paths": [
            str(path.relative_to(resolved_root))
            if path.is_relative_to(resolved_root)
            else str(path)
            for path in candidate_paths
        ],
        "invalid_trace_paths": invalid_trace_paths,
        "output_path": (
            str(resolved_output_path.relative_to(resolved_root))
            if resolved_output_path.is_relative_to(resolved_root)
            else str(resolved_output_path)
        ),
        "family_state_path": (
            str(resolved_family_state_path.relative_to(resolved_root))
            if resolved_family_state_path.is_relative_to(resolved_root)
            else str(resolved_family_state_path)
        ),
    }
    if remote_family_state is not None:
        summary["remote_family_state"] = remote_family_state
    resolved_summary_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_summary_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        **summary,
        "summary_path": (
            str(resolved_summary_path.relative_to(resolved_root))
            if resolved_summary_path.is_relative_to(resolved_root)
            else str(resolved_summary_path)
        ),
    }


def materialize_combined_training_examples(
    root: Path,
    *,
    base_training_path: Path,
    candidates_path: Path,
    output_path: Path,
    summary_path: Path,
) -> dict[str, Any]:
    """Merge the base training set with trainer-side candidate examples."""

    resolved_root = root.resolve()
    resolved_base_path = (
        base_training_path
        if base_training_path.is_absolute()
        else resolved_root / base_training_path
    )
    resolved_candidates_path = (
        candidates_path if candidates_path.is_absolute() else resolved_root / candidates_path
    )
    resolved_output_path = output_path if output_path.is_absolute() else resolved_root / output_path
    resolved_summary_path = (
        summary_path if summary_path.is_absolute() else resolved_root / summary_path
    )

    base_payload = yaml.safe_load(resolved_base_path.read_text(encoding="utf-8")) or []
    if not isinstance(base_payload, list):
        raise ValueError(f"Base training payload must be a YAML list: {resolved_base_path}")
    base_records = [record for record in base_payload if isinstance(record, Mapping)]

    candidate_records: list[Mapping[str, Any]] = []
    skipped_candidate_records = 0
    if resolved_candidates_path.is_file():
        candidate_payload = (
            yaml.safe_load(resolved_candidates_path.read_text(encoding="utf-8")) or []
        )
        if not isinstance(candidate_payload, list):
            raise ValueError(
                f"Trainer candidate payload must be a YAML list: {resolved_candidates_path}"
            )
        raw_candidate_records = [
            _normalize_materialized_candidate_record(record)
            for record in candidate_payload
            if isinstance(record, Mapping)
        ]
        candidate_records = [
            record
            for record in raw_candidate_records
            if _trainer_candidate_record_is_supported(record)
        ]
        skipped_candidate_records = len(raw_candidate_records) - len(candidate_records)

    merged_records_by_question: dict[str, dict[str, Any]] = {}
    merged_order: list[str] = []
    duplicate_base_count = 0
    for record in base_records:
        normalized = _normalize_combined_training_record(record)
        question_key = _candidate_question_key(normalized)
        if not question_key:
            merged_order.append(f"__blank-base-{len(merged_order)}")
            merged_records_by_question[merged_order[-1]] = normalized
            continue
        if question_key in merged_records_by_question:
            duplicate_base_count += 1
            continue
        merged_order.append(question_key)
        merged_records_by_question[question_key] = normalized

    new_candidate_count = 0
    duplicate_candidate_count = 0
    replaced_candidate_count = 0
    for record in candidate_records:
        normalized = _normalize_combined_training_record(record)
        question_key = _candidate_question_key(normalized)
        if not question_key:
            merged_order.append(f"__blank-candidate-{len(merged_order)}")
            merged_records_by_question[merged_order[-1]] = normalized
            new_candidate_count += 1
            continue
        existing_record = merged_records_by_question.get(question_key)
        if existing_record is None:
            merged_order.append(question_key)
            merged_records_by_question[question_key] = normalized
            new_candidate_count += 1
            continue
        if _candidate_record_key(existing_record) == _candidate_record_key(normalized):
            duplicate_candidate_count += 1
            continue
        merged_records_by_question[question_key] = normalized
        replaced_candidate_count += 1

    merged_records = [merged_records_by_question[key] for key in merged_order]

    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_output_path.write_text(
        yaml.safe_dump(merged_records, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    summary = {
        "base_example_count": len(base_records),
        "candidate_example_count": len(candidate_records),
        "skipped_unsupported_candidate_count": skipped_candidate_records,
        "combined_example_count": len(merged_records),
        "new_candidate_count": new_candidate_count,
        "duplicate_candidate_count": duplicate_candidate_count,
        "replaced_candidate_count": replaced_candidate_count,
        "duplicate_base_count": duplicate_base_count,
        "base_training_path": (
            str(resolved_base_path.relative_to(resolved_root))
            if resolved_base_path.is_relative_to(resolved_root)
            else str(resolved_base_path)
        ),
        "candidates_path": (
            str(resolved_candidates_path.relative_to(resolved_root))
            if resolved_candidates_path.is_relative_to(resolved_root)
            else str(resolved_candidates_path)
        ),
        "output_path": (
            str(resolved_output_path.relative_to(resolved_root))
            if resolved_output_path.is_relative_to(resolved_root)
            else str(resolved_output_path)
        ),
    }
    resolved_summary_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return {
        **summary,
        "summary_path": (
            str(resolved_summary_path.relative_to(resolved_root))
            if resolved_summary_path.is_relative_to(resolved_root)
            else str(resolved_summary_path)
        ),
    }
