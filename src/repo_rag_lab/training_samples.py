"""Helpers for loading and summarizing starter DSPy training examples."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, cast

import yaml

from .runtime_artifacts import (
    DEFAULT_TRAINER_FAMILY_CACHE_DIR,
    DEFAULT_TRAINER_FAMILY_STATE_PATH,
    load_json_object,
    upload_remote_family_state,
)


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
TRAINER_CHAMPION_INDEX_KIND = "repo-rag-trainer-champion-index"
TRAINER_FAMILY_STATE_SCHEMA_VERSION = TRAINER_CHAMPION_INDEX_SCHEMA_VERSION
TRAINER_FAMILY_STATE_KIND = "repo-rag-trainer-family-state"
PROMPT_FAMILY_MATCH_THRESHOLD = 0.8
TRAINER_IMPORTED_ANSWER_CHAR_BUDGET = 4000

_CODEX_TRANSCRIPT_BLOCK_PATTERN = re.compile(
    r"(?ms)^codex\n(.*?)(?=^(?:user|exec|apply patch|diff --git|web search|mcp)\b|"
    r"^tokens used\b|\Z)"
)
_CODEX_STDOUT_SECTION_PATTERN = re.compile(r"(?ms)\nSTDOUT:\n(.*?)(?:\nSTDERR:\n|\Z)")
_FORWARDED_DISCORD_TAIL_PATTERN = re.compile(r"(?is)\s*\[forwarded\]\s*@.*$")
_FAMILY_CACHE_TOKEN_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


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
        part
        for part in _FAMILY_CACHE_TOKEN_PATTERN.split(str(value or "").strip())
        if part
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

    normalized_question = _normalize_question_text(question).casefold()
    if not normalized_question:
        return []
    return [token for token in re.findall(r"[a-z0-9]+", normalized_question) if token]


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


def _prompt_family_similarity(question: str, family_payload: Mapping[str, Any]) -> float:
    """Return the prompt similarity between one question and the family father."""

    family_father_question = _routing_question(
        question=family_payload.get("family_father_question")
        or family_payload.get("question")
        or family_payload.get("normalized_question"),
        original_prompt=(
            _family_father_record(family_payload) or {}
        ).get("original_prompt"),
        reformulated_prompt=(
            _family_father_record(family_payload) or {}
        ).get("reformulated_prompt"),
    )
    if not family_father_question:
        return 0.0
    return _question_similarity(question, family_father_question)


def resolve_prompt_family_support_from_payload(
    question: str,
    payload: Mapping[str, Any],
) -> PromptFamilySupport:
    """Resolve the best stored prompt-family support from one in-memory family payload."""

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
    families = payload.get("prompt_families")
    best_family: Mapping[str, Any] | None = None
    best_similarity = 0.0
    if isinstance(families, list):
        for family in families:
            if not isinstance(family, Mapping):
                continue
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


def resolve_prompt_family_support(question: str, family_state_path: Path) -> PromptFamilySupport:
    """Resolve the best stored prompt-family support for one prompt string."""

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
        return
    family_payload["family_father_record"] = None
    family_payload["family_father_similarity_mean"] = None
    family_payload["family_father_question"] = normalized_question or None
    if normalized_question:
        family_payload["question"] = normalized_question
        family_payload["normalized_question"] = normalized_question.casefold()


def _find_or_create_prompt_family(
    family_by_id: dict[str, dict[str, Any]],
    family_order: list[str],
    *,
    question: str,
    preferred_family_id: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Return the matching prompt family for one question, creating one when needed."""

    best_family: dict[str, Any] | None = None
    best_similarity = 0.0
    for family_id in family_order:
        family_payload = family_by_id.get(family_id)
        if family_payload is None:
            continue
        similarity = _prompt_family_similarity(question, family_payload)
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
    family_payload = {
        "prompt_family_id": prompt_family_id,
        "family_needs_recompile": True,
        "question": "",
        "normalized_question": "",
        "question_variants": [],
        "question_variant_count": 0,
        "family_father_question": None,
        "family_father_similarity_mean": None,
        "family_father_record": None,
        "family_runtime_artifact": None,
        "family_runtime_context_group_id": None,
        "family_runtime_score": None,
        "family_runtime_record": None,
        "family_champion_context_group_id": None,
        "family_champion_score": None,
        "family_champion_record": None,
        "family_records": [],
        "context_groups": [],
    }
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
        return f"trace-file:{Path(source_queue_item_path).name}"
    provenance = payload.get("provenance")
    if isinstance(provenance, Mapping):
        provenance_queue_item_path = str(provenance.get("source_queue_item_path") or "").strip()
        if provenance_queue_item_path:
            return f"trace-file:{Path(provenance_queue_item_path).name}"
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
        "family_state_layout": "thin-index",
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
        "family_needs_recompile",
        "question",
        "normalized_question",
        "question_variants",
        "question_variant_count",
        "family_father_question",
        "family_father_similarity_mean",
        "family_father_record",
        "family_runtime_artifact",
        "family_runtime_context_group_id",
        "family_runtime_score",
        "family_runtime_record",
        "family_champion_context_group_id",
        "family_champion_score",
        "family_champion_record",
    ):
        if field_name in family_entry and field_name not in loaded_payload:
            loaded_payload[field_name] = family_entry[field_name]
    return loaded_payload


def _strip_family_state_inline_payload(
    family_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Return one thin-index family entry without replay-set duplication."""

    return {
        "prompt_family_id": str(family_payload.get("prompt_family_id") or "").strip(),
        "family_needs_recompile": bool(family_payload.get("family_needs_recompile")),
        "question": _normalize_question_text(family_payload.get("question")),
        "normalized_question": _normalize_question_text(
            family_payload.get("normalized_question")
        ),
        "question_variants": _family_question_variants(family_payload),
        "question_variant_count": int(family_payload.get("question_variant_count") or 0),
        "family_father_question": _normalize_question_text(
            family_payload.get("family_father_question")
        )
        or None,
        "family_father_similarity_mean": family_payload.get("family_father_similarity_mean"),
        "family_runtime_context_group_id": family_payload.get("family_runtime_context_group_id"),
        "family_runtime_score": family_payload.get("family_runtime_score"),
        "family_runtime_artifact": family_payload.get("family_runtime_artifact"),
        "family_champion_context_group_id": family_payload.get("family_champion_context_group_id"),
        "family_champion_score": family_payload.get("family_champion_score"),
        "family_record_count": len(_family_replay_records(family_payload)),
        "context_group_count": len(
            family_payload.get("context_groups")
            if isinstance(family_payload.get("context_groups"), list)
            else []
        ),
    }


def _persist_local_family_state(
    family_state_path: Path,
    index_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist the local family cache plus a thin family-state index."""

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

        family_file_payload = {
            key: value
            for key, value in full_family_payload.items()
            if key not in {"family_path", "father_path", "record_paths", "family_record_count"}
        }
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
        "family_state_layout": "thin-index",
        "generated_at": index_payload.get("generated_at") or datetime.now(UTC).isoformat(),
        "prompt_families": thin_families,
    }
    resolved_family_state_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_family_state_path.write_text(
        f"{json.dumps(thin_index, indent=2)}\n",
        encoding="utf-8",
    )
    return thin_index


def _load_champion_index(path: Path) -> dict[str, Any]:
    """Load a persisted champion index or return an empty one."""

    if not path.is_file():
        return _fresh_champion_index()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return _fresh_champion_index()
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
        if not isinstance(family, dict):
            continue
        family["family_needs_recompile"] = bool(family.get("family_needs_recompile"))
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
        context_groups = family.get("context_groups")
        if not isinstance(context_groups, list):
            continue
        normalized_groups: list[dict[str, Any]] = []
        for group in context_groups:
            if not isinstance(group, dict):
                continue
            champion_record = group.get("champion_record")
            if not isinstance(champion_record, Mapping):
                continue
            support_mapping = group.get("support_by_record_key")
            old_hash = _candidate_record_hash(champion_record)
            normalized_record = _serialize_candidate_record(champion_record)
            if not _trainer_candidate_record_is_supported(normalized_record):
                continue
            new_hash = _candidate_record_hash(normalized_record)
            if isinstance(support_mapping, dict):
                carried_support = int(support_mapping.get(old_hash) or 0)
                if old_hash != new_hash:
                    support_mapping.pop(old_hash, None)
                    if carried_support:
                        support_mapping[new_hash] = max(
                            int(support_mapping.get(new_hash) or 0),
                            carried_support,
                        )
            group["champion_record"] = normalized_record
            normalized_groups.append(group)
        family["context_groups"] = normalized_groups
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
        _refresh_family_champion(family)
        champion_record = _family_champion_record(family)
        if champion_record is not None:
            _refresh_prompt_family_summary(family, champion_record.get("question") or "")
        elif stored_family_question:
            _refresh_prompt_family_summary(family, stored_family_question)
    return payload


def load_family_state_payload(path: Path) -> dict[str, Any]:
    """Load one persisted family-state file and hydrate its full family payloads."""

    return _load_champion_index(path)


def _seed_champion_index_from_existing_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a first champion index from legacy materialized candidate rows."""

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
            preferred_family_id=preferred_family_id,
        )
        if created_family:
            family_payload["seed_record"] = record
            continue
        family_payload["seed_record"] = record

    families: list[dict[str, Any]] = []
    for prompt_family_id in family_order:
        record_value = family_by_id[prompt_family_id].get("seed_record")
        if not isinstance(record_value, Mapping):
            continue
        record = cast(Mapping[str, Any], record_value)
        question = _record_routing_question(record)
        sources = _normalized_source_tokens(record.get("expected_sources", []))
        context_group_id = str(
            record.get("context_group_id")
            or f"cg-{_stable_hash(prompt_family_id, sources or ['legacy'])}"
        )
        _, _, metric_ratio = _record_metric(record)
        support_count = int(record.get("support_count") or 1)
        champion_record = _serialize_candidate_record(
            {
                **dict(record),
                "prompt_family_id": prompt_family_id,
                "context_group_id": context_group_id,
                "quality_score": metric_ratio,
                "support_count": support_count,
            }
        )
        families.append(
            {
                "prompt_family_id": prompt_family_id,
                "question": question,
                "normalized_question": question.casefold(),
                "question_variants": _family_question_variants(family_by_id[prompt_family_id]),
                "question_variant_count": len(
                    _family_question_variants(family_by_id[prompt_family_id])
                ),
                "family_needs_recompile": True,
                "family_father_question": None,
                "family_father_similarity_mean": None,
                "family_father_record": None,
                "family_runtime_artifact": None,
                "family_runtime_context_group_id": context_group_id,
                "family_runtime_score": metric_ratio,
                "family_runtime_record": champion_record,
                "family_champion_context_group_id": context_group_id,
                "family_champion_score": metric_ratio,
                "family_champion_record": champion_record,
                "family_records": [champion_record],
                "context_groups": [
                    {
                        "context_group_id": context_group_id,
                        "sources": sources,
                        "evidence_fingerprints": [],
                        "evidence_count": 0,
                        "retrieval_mode": "",
                        "mode": "",
                        "context_field": "",
                        "source_count": len(sources),
                        "context_count": 0,
                        "top_k": None,
                        "trace_count": support_count,
                        "support_by_record_key": {
                            _candidate_record_hash(champion_record): support_count
                        },
                        "champion_score": metric_ratio,
                        "champion_record": champion_record,
                    }
                ],
            }
        )
        _refresh_family_champion(families[-1])
    index_payload["prompt_families"] = families
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
    """Return stable unique family-level candidate records for father selection."""

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
    groups = family_payload.get("context_groups")
    if isinstance(groups, list):
        for group in groups:
            if not isinstance(group, Mapping):
                continue
            _append_record(group.get("champion_record"))
    _append_record(family_payload.get("family_runtime_record"))
    _append_record(family_payload.get("family_champion_record"))
    _append_record(family_payload.get("family_father_record"))
    return records


def _select_family_father_record(
    family_payload: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, float | None]:
    """Return the family record whose question is most central to the family."""

    candidate_records = _family_candidate_records(family_payload)
    best_record: dict[str, Any] | None = None
    best_mean: float | None = None
    for record in candidate_records:
        question = _record_routing_question(record)
        if not question:
            continue
        similarities = [
            _question_similarity(question, _record_routing_question(other))
            for other in candidate_records
            if _record_routing_question(other)
        ]
        if not similarities:
            continue
        mean_similarity = round(sum(similarities) / len(similarities), 6)
        if best_mean is None or mean_similarity > best_mean:
            best_record = record
            best_mean = mean_similarity
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


def _group_support_count(group_payload: Mapping[str, Any]) -> int:
    """Return the observed support count for one context group."""

    try:
        return max(0, int(group_payload.get("trace_count") or 0))
    except (TypeError, ValueError):
        return 0


def _context_group_rank_key(group: Mapping[str, Any]) -> tuple[float, int, str]:
    """Return the stable sort key for one candidate context group."""

    return (float(group.get("champion_score") or 0.0), 0, "")


def _refresh_family_champion(family_payload: dict[str, Any]) -> tuple[bool, str | None, str | None]:
    """Recompute the best family champion from its context-group champions."""

    groups = family_payload.get("context_groups")
    if not isinstance(groups, list) or not groups:
        fallback_record = _family_runtime_record(family_payload) or _family_champion_record(
            family_payload
        )
        if fallback_record is not None:
            family_payload["family_runtime_record"] = fallback_record
            family_payload["family_runtime_score"] = float(
                fallback_record.get("metric_ratio")
                or fallback_record.get("quality_score")
                or family_payload.get("family_runtime_score")
                or family_payload.get("family_champion_score")
                or 0.0
            )
            family_payload["family_champion_record"] = fallback_record
            family_payload["family_champion_score"] = float(
                family_payload.get("family_runtime_score") or 0.0
            )
            _refresh_prompt_family_summary(family_payload, fallback_record.get("question") or "")
            return False, None, None
        family_payload["family_runtime_context_group_id"] = None
        family_payload["family_runtime_score"] = None
        family_payload["family_runtime_record"] = None
        family_payload["family_champion_context_group_id"] = None
        family_payload["family_champion_score"] = None
        family_payload["family_champion_record"] = None
        return False, None, None

    ranked_groups = sorted(
        (
            group
            for group in groups
            if isinstance(group, Mapping) and isinstance(group.get("champion_record"), Mapping)
        ),
        key=_context_group_rank_key,
        reverse=True,
    )
    if not ranked_groups:
        fallback_record = _family_runtime_record(family_payload) or _family_champion_record(
            family_payload
        )
        if fallback_record is not None:
            family_payload["family_runtime_record"] = fallback_record
            family_payload["family_runtime_score"] = float(
                fallback_record.get("metric_ratio")
                or fallback_record.get("quality_score")
                or family_payload.get("family_runtime_score")
                or family_payload.get("family_champion_score")
                or 0.0
            )
            family_payload["family_champion_record"] = fallback_record
            family_payload["family_champion_score"] = float(
                family_payload.get("family_runtime_score") or 0.0
            )
            _refresh_prompt_family_summary(family_payload, fallback_record.get("question") or "")
            return False, None, None
        family_payload["family_runtime_context_group_id"] = None
        family_payload["family_runtime_score"] = None
        family_payload["family_runtime_record"] = None
        family_payload["family_champion_context_group_id"] = None
        family_payload["family_champion_score"] = None
        family_payload["family_champion_record"] = None
        return False, None, None

    previous_group_id = str(family_payload.get("family_champion_context_group_id") or "") or None
    previous_snapshot_id = None
    previous_record = family_payload.get("family_champion_record")
    if isinstance(previous_record, Mapping):
        previous_snapshot_id = str(previous_record.get("exact_snapshot_id") or "") or None

    incumbent_group: Mapping[str, Any] | None = None
    if previous_group_id is not None:
        for group in ranked_groups:
            if str(group.get("context_group_id") or "") == previous_group_id:
                incumbent_group = group
                break

    selected_group = ranked_groups[0]
    if incumbent_group is not None:
        incumbent_score = float(incumbent_group.get("champion_score") or 0.0)
        selected_group = incumbent_group
        for challenger_group in ranked_groups:
            if challenger_group is incumbent_group:
                continue
            challenger_score = float(challenger_group.get("champion_score") or 0.0)
            if challenger_score > incumbent_score:
                selected_group = challenger_group
                incumbent_score = challenger_score

    best_group = selected_group
    best_group_id = str(best_group.get("context_group_id") or "") or None
    best_record = _serialize_candidate_record(best_group.get("champion_record", {}))
    best_snapshot_id = str(best_record.get("exact_snapshot_id") or "") or None
    family_payload["family_runtime_context_group_id"] = best_group_id
    family_payload["family_runtime_score"] = float(best_group.get("champion_score") or 0.0)
    family_payload["family_runtime_record"] = best_record
    family_payload["family_champion_context_group_id"] = best_group_id
    family_payload["family_champion_score"] = float(best_group.get("champion_score") or 0.0)
    family_payload["family_champion_record"] = best_record
    _refresh_prompt_family_summary(family_payload, best_record.get("question") or "")
    changed = previous_group_id != best_group_id or previous_snapshot_id != best_snapshot_id
    return changed, previous_group_id, best_group_id


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


def _find_or_create_context_group(
    family_payload: dict[str, Any],
    *,
    context_snapshot: Mapping[str, Any],
    question: str,
    prompt_family_id: str,
    exact_snapshot_id: str,
) -> tuple[dict[str, Any], bool]:
    """Return one storage group for the family, creating it when needed."""

    groups = family_payload.setdefault("context_groups", [])
    if not isinstance(groups, list):
        groups = []
        family_payload["context_groups"] = groups
    for group in groups:
        if isinstance(group, dict):
            return group, False
    context_group_id = f"cg-{_stable_hash(prompt_family_id)}"
    group_payload: dict[str, Any] = {
        "context_group_id": context_group_id,
        "sources": list(context_snapshot.get("sources", [])),
        "evidence_fingerprints": list(context_snapshot.get("evidence_fingerprints", [])),
        "evidence_count": int(context_snapshot.get("evidence_count") or 0),
        "retrieval_mode": str(context_snapshot.get("retrieval_mode") or ""),
        "mode": str(context_snapshot.get("mode") or ""),
        "context_field": str(context_snapshot.get("context_field") or ""),
        "source_count": int(context_snapshot.get("source_count") or 0),
        "context_count": int(context_snapshot.get("context_count") or 0),
        "top_k": context_snapshot.get("top_k"),
        "trace_count": 0,
        "support_by_record_key": {},
        "champion_score": None,
        "champion_record": None,
    }
    groups.append(group_payload)
    return group_payload, True


def _refresh_context_group_summary(
    group_payload: dict[str, Any],
    context_snapshot: Mapping[str, Any],
    *,
    align_strings: bool = False,
) -> None:
    """Update one context-group summary so gradual retrieval drift stays grouped."""

    group_payload["sources"] = _normalized_source_tokens(
        [
            *(_normalized_source_tokens(group_payload.get("sources", []))),
            *(_normalized_source_tokens(context_snapshot.get("sources", []))),
        ]
    )
    group_payload["evidence_fingerprints"] = _normalized_source_tokens(
        [
            *(_normalized_source_tokens(group_payload.get("evidence_fingerprints", []))),
            *(_normalized_source_tokens(context_snapshot.get("evidence_fingerprints", []))),
        ]
    )
    group_payload["evidence_count"] = max(
        int(group_payload.get("evidence_count") or 0),
        int(context_snapshot.get("evidence_count") or 0),
        len(group_payload.get("evidence_fingerprints", [])),
    )
    for field_name in ("retrieval_mode", "mode", "context_field"):
        candidate_value = str(context_snapshot.get(field_name) or "").strip()
        current_value = str(group_payload.get(field_name) or "").strip()
        if align_strings or not current_value:
            group_payload[field_name] = candidate_value
    group_payload["source_count"] = max(
        int(group_payload.get("source_count") or 0),
        int(context_snapshot.get("source_count") or 0),
        len(group_payload.get("sources", [])),
    )
    group_payload["context_count"] = max(
        int(group_payload.get("context_count") or 0),
        int(context_snapshot.get("context_count") or 0),
    )
    current_top_k = group_payload.get("top_k")
    candidate_top_k = context_snapshot.get("top_k")
    try:
        current_top_k_value = int(current_top_k) if current_top_k is not None else None
    except (TypeError, ValueError):
        current_top_k_value = None
    try:
        candidate_top_k_value = int(candidate_top_k) if candidate_top_k is not None else None
    except (TypeError, ValueError):
        candidate_top_k_value = None
    if align_strings or current_top_k_value is None:
        group_payload["top_k"] = candidate_top_k_value
    elif candidate_top_k_value is not None:
        group_payload["top_k"] = max(current_top_k_value, candidate_top_k_value)


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
            return f"trace-file:{Path(source_queue_item_path).name}"
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
        if str(existing_normalized.get("exact_snapshot_id") or "").strip() == str(
            normalized.get("exact_snapshot_id") or ""
        ).strip():
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
    new_context_group_count = 0
    new_prompt_family_count = 0
    prompt_family_count_before = len(family_by_id)
    for record in loaded_records:
        prompt_family_id_hint = str(record.get("prompt_family_id") or "").strip()
        exact_snapshot_id = str(record.get("exact_snapshot_id") or "").strip()
        question = _normalize_question_text(record.get("question"))
        provenance = record.get("provenance")
        context_snapshot = {}
        if isinstance(provenance, Mapping):
            candidate_snapshot = provenance.get("context_snapshot")
            if isinstance(candidate_snapshot, Mapping):
                context_snapshot = dict(candidate_snapshot)
        if not exact_snapshot_id or not question or not context_snapshot:
            continue
        if exact_snapshot_id in seen_snapshot_ids:
            duplicate_count += 1
            continue
        seen_snapshot_ids.add(exact_snapshot_id)

        family_payload, created_family = _find_or_create_prompt_family(
            family_by_id,
            family_order,
            question=question,
            preferred_family_id=prompt_family_id_hint or None,
        )
        if created_family:
            new_prompt_family_count += 1
        prompt_family_id = str(family_payload.get("prompt_family_id") or "").strip()
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

        context_group, created_group = _find_or_create_context_group(
            family_payload,
            context_snapshot=context_snapshot,
            question=question,
            prompt_family_id=prompt_family_id,
            exact_snapshot_id=exact_snapshot_id,
        )
        if created_group:
            new_context_group_count += 1
        _refresh_context_group_summary(context_group, context_snapshot)
        context_group["trace_count"] = _group_support_count(context_group) + 1
        _, _, candidate_score = _record_metric(record)
        serialized_record = _serialize_candidate_record(record)
        serialized_record["prompt_family_id"] = prompt_family_id
        serialized_record["context_group_id"] = context_group["context_group_id"]
        support_mapping = context_group.get("support_by_record_key")
        if not isinstance(support_mapping, dict):
            support_mapping = {}
            context_group["support_by_record_key"] = support_mapping
        record_hash = _candidate_record_hash(serialized_record)
        candidate_support = int(support_mapping.get(record_hash) or 0) + 1
        support_mapping[record_hash] = candidate_support
        serialized_record["support_count"] = candidate_support
        _upsert_family_replay_record(family_payload, serialized_record)

        current_group_record = context_group.get("champion_record")
        current_group_score = float(context_group.get("champion_score") or 0.0)
        replace_group_champion = False
        if not isinstance(current_group_record, Mapping):
            replace_group_champion = True
        elif _candidate_record_key(current_group_record) == _candidate_record_key(
            serialized_record
        ):
            merged_group_record = _merge_equivalent_candidate_records(
                current_group_record,
                serialized_record,
            )
            merged_group_record["support_count"] = candidate_support
            context_group["champion_record"] = merged_group_record
            context_group["champion_score"] = max(
                current_group_score,
                candidate_score,
            )
        elif candidate_score > current_group_score:
            replace_group_champion = True
        if replace_group_champion:
            context_group["champion_record"] = serialized_record
            context_group["champion_score"] = candidate_score
            _refresh_context_group_summary(
                context_group,
                context_snapshot,
                align_strings=True,
            )

        family_changed, _, _ = _refresh_family_champion(family_payload)
        current_family_record = _family_champion_record(family_payload)
        current_family_signature = (
            _candidate_materialization_signature(current_family_record)
            if current_family_record is not None
            else None
        )
        if previous_family_record is None and current_family_record is not None:
            new_candidate_count += 1
        elif (
            previous_family_signature is not None
            and current_family_signature is not None
            and previous_family_signature != current_family_signature
        ):
            new_candidate_count += 1
            replaced_count += 1
        elif family_changed and current_family_record is not None and previous_family_key is None:
            new_candidate_count += 1

    champion_index["generated_at"] = datetime.now(UTC).isoformat()
    champion_index["prompt_families"] = [family_by_id[family_id] for family_id in family_order]
    merged_records = _materialize_family_champion_records(champion_index)

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
        "input_trace_count": len(candidate_paths),
        "loaded_candidate_count": len(loaded_records),
        "duplicate_count": duplicate_count,
        "replaced_count": replaced_count,
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
            len(family_payload.get("context_groups", []))
            for family_payload in family_by_id.values()
            if isinstance(family_payload.get("context_groups"), list)
        ),
        "new_context_group_count": new_context_group_count,
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
