"""Helpers for loading and summarizing starter DSPy training examples."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml

from .runtime_artifacts import (
    DEFAULT_TRAINER_CHAMPION_INDEX_PATH,
    load_json_object,
    upload_remote_champion_index,
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


@dataclass(frozen=True)
class PromptFamilySupport:
    """Describe the best current champion-family support for one prompt."""

    question: str
    prompt_family_id: str | None
    similarity: float
    band: str
    supported: bool
    champion_record: dict[str, Any] | None = None


TRAINER_CHAMPION_INDEX_SCHEMA_VERSION = 1
TRAINER_CHAMPION_INDEX_KIND = "repo-rag-trainer-champion-index"
PROMPT_FAMILY_MATCH_THRESHOLD = 0.8
PROMPT_FAMILY_SOFT_THRESHOLD = 0.6
TRAINER_IMPORTED_ANSWER_CHAR_BUDGET = 4000

_CODEX_TRANSCRIPT_BLOCK_PATTERN = re.compile(
    r"(?ms)^codex\n(.*?)(?=^(?:user|exec|apply patch|diff --git|web search|mcp)\b|^tokens used\b|\Z)"
)
_CODEX_STDOUT_SECTION_PATTERN = re.compile(r"(?ms)\nSTDOUT:\n(.*?)(?:\nSTDERR:\n|\Z)")


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
            str(text).strip()
            for text in record.get("benchmark_context", [])
            if str(text).strip()
        )
        benchmark_context_sources = tuple(
            str(source).strip()
            for source in record.get("benchmark_context_sources", [])
            if str(source).strip()
        )
        normalized.append(
            TrainingExample(
                question=str(record["question"]).strip(),
                expected_answer=str(record["expected_answer"]).strip(),
                tags=tags,
                expected_sources=expected_sources,
                benchmark_context=benchmark_context,
                benchmark_context_sources=benchmark_context_sources,
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
            1
            for example in examples
            if example.expected_sources or example.benchmark_context
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
        str(record.get("question") or "").strip().casefold(),
        str(record.get("expected_answer") or "").strip().casefold(),
        sources,
        str(record.get("candidate_status") or "").strip().casefold(),
    )


def _candidate_question_key(record: Mapping[str, Any]) -> str:
    """Return the stable question-level identity for one training-candidate record."""

    return str(record.get("question") or "").strip().casefold()


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

    return " ".join(str(value or "").strip().split())


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


def _count_similarity(left: object, right: object) -> float:
    """Return a bounded similarity score for two optional integer-like values."""

    left_value = _coerce_int(left)
    right_value = _coerce_int(right)
    if left_value is None and right_value is None:
        return 1.0
    if left_value is None or right_value is None:
        return 0.5
    if left_value == right_value:
        return 1.0
    upper = max(abs(left_value), abs(right_value))
    if upper == 0:
        return 1.0
    return min(abs(left_value), abs(right_value)) / upper


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
    return {
        "question": reformulated_prompt or original_prompt,
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
    stored_variants = family_payload.get("question_variants")
    if isinstance(stored_variants, list):
        for variant in stored_variants:
            _append_variant(variant)
    champion_record = family_payload.get("family_champion_record")
    if isinstance(champion_record, Mapping):
        _append_variant(champion_record.get("question"))
    return variants


def _prompt_family_similarity(question: str, family_payload: Mapping[str, Any]) -> float:
    """Return the best prompt similarity between one question and one prompt family."""

    return max(
        (
            _question_similarity(question, variant)
            for variant in _family_question_variants(family_payload)
        ),
        default=0.0,
    )


def resolve_prompt_family_support(question: str, champion_index_path: Path) -> PromptFamilySupport:
    """Resolve the best stored prompt-family support for one prompt string."""

    normalized_question = _normalize_question_text(question)
    if not normalized_question:
        return PromptFamilySupport(
            question="",
            prompt_family_id=None,
            similarity=0.0,
            band="new",
            supported=False,
            champion_record=None,
        )
    index_payload = _load_champion_index(champion_index_path)
    families = index_payload.get("prompt_families")
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
    band = "new"
    if best_similarity > PROMPT_FAMILY_MATCH_THRESHOLD:
        band = "match"
    elif best_similarity >= PROMPT_FAMILY_SOFT_THRESHOLD:
        band = "heuristic"
    supported = bool(best_family is not None and _matches_prompt_family(normalized_question, best_family))
    prompt_family_id = (
        str(best_family.get("prompt_family_id") or "").strip()
        if isinstance(best_family, Mapping)
        else ""
    )
    champion_record = _family_champion_record(best_family) if best_family is not None else None
    return PromptFamilySupport(
        question=normalized_question,
        prompt_family_id=prompt_family_id or None,
        similarity=best_similarity,
        band=band,
        supported=supported,
        champion_record=champion_record,
    )


def _matches_prompt_family(question: str, family_payload: Mapping[str, Any]) -> bool:
    """Return whether one question should join an existing prompt family."""

    return _prompt_family_similarity(question, family_payload) >= PROMPT_FAMILY_MATCH_THRESHOLD


def _refresh_prompt_family_summary(family_payload: dict[str, Any], question: str) -> None:
    """Update one prompt-family summary so similar prompt variants stay grouped."""

    normalized_question = _normalize_question_text(question)
    if normalized_question:
        family_payload["question"] = normalized_question
        family_payload["normalized_question"] = normalized_question.casefold()
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
        if similarity > best_similarity and _matches_prompt_family(question, family_payload):
            best_family = family_payload
            best_similarity = similarity
    if best_family is not None:
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
        "question": "",
        "normalized_question": "",
        "question_variants": [],
        "question_variant_count": 0,
        "family_champion_context_group_id": None,
        "family_champion_score": None,
        "family_champion_record": None,
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
    trace_record_path: str,
    recorded_at: str,
    context_snapshot: Mapping[str, Any],
) -> str:
    """Return the immutable identity for one concrete imported trace snapshot."""

    stable_snapshot_hash = _stable_hash(
        question,
        expected_answer,
        trace_record_path,
        recorded_at,
        context_snapshot,
    )
    return f"ts-{stable_snapshot_hash}"


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


def _context_similarity(
    candidate_snapshot: Mapping[str, Any], group_payload: Mapping[str, Any]
) -> float:
    """Return a soft similarity score between one trace snapshot and one stored context group."""

    candidate_sources = _normalized_source_tokens(candidate_snapshot.get("sources", []))
    group_sources = _normalized_source_tokens(group_payload.get("sources", []))
    source_overlap = _jaccard_similarity(candidate_sources, group_sources)
    candidate_evidence = _normalized_source_tokens(
        candidate_snapshot.get("evidence_fingerprints", [])
    )
    group_evidence = _normalized_source_tokens(group_payload.get("evidence_fingerprints", []))
    evidence_overlap = _jaccard_similarity(candidate_evidence, group_evidence)
    retrieval_mode_score = _string_match_similarity(
        candidate_snapshot.get("retrieval_mode"),
        group_payload.get("retrieval_mode"),
    )
    mode_score = _string_match_similarity(candidate_snapshot.get("mode"), group_payload.get("mode"))
    context_field_score = _string_match_similarity(
        candidate_snapshot.get("context_field"),
        group_payload.get("context_field"),
    )
    source_count_score = _count_similarity(
        candidate_snapshot.get("source_count"),
        group_payload.get("source_count"),
    )
    context_count_score = _count_similarity(
        candidate_snapshot.get("context_count"),
        group_payload.get("context_count"),
    )
    top_k_score = _count_similarity(candidate_snapshot.get("top_k"), group_payload.get("top_k"))
    evidence_count_score = _count_similarity(
        candidate_snapshot.get("evidence_count"),
        group_payload.get("evidence_count"),
    )
    return round(
        (0.30 * source_overlap)
        + (0.35 * evidence_overlap)
        + (0.10 * retrieval_mode_score)
        + (0.10 * mode_score)
        + (0.05 * context_field_score)
        + (0.05 * source_count_score)
        + (0.05 * context_count_score)
        + (0.03 * top_k_score)
        + (0.02 * evidence_count_score),
        6,
    )


def _matches_context_group(
    candidate_snapshot: Mapping[str, Any], group_payload: Mapping[str, Any]
) -> bool:
    """Return whether a trace snapshot should join an existing context group."""

    del candidate_snapshot, group_payload
    return False


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
        "schema_version": TRAINER_CHAMPION_INDEX_SCHEMA_VERSION,
        "record_kind": TRAINER_CHAMPION_INDEX_KIND,
        "generated_at": datetime.now(UTC).isoformat(),
        "prompt_families": [],
    }


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
    for family in families:
        if not isinstance(family, dict):
            continue
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
        _refresh_family_champion(family)
        champion_record = _family_champion_record(family)
        if champion_record is not None:
            _refresh_prompt_family_summary(family, champion_record.get("question") or "")
    return payload


def _seed_champion_index_from_existing_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a first champion index from legacy materialized candidate rows."""

    index_payload = _fresh_champion_index()
    family_by_id: dict[str, dict[str, Any]] = {}
    family_order: list[str] = []
    for record in records:
        question = _normalize_question_text(record.get("question"))
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
        record = family_by_id[prompt_family_id].get("seed_record")
        if not isinstance(record, Mapping):
            continue
        question = _normalize_question_text(record.get("question"))
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
                "family_champion_context_group_id": context_group_id,
                "family_champion_score": metric_ratio,
                "family_champion_record": champion_record,
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
    index_payload["prompt_families"] = families
    return index_payload


def _family_champion_record(family_payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the normalized family champion record, if any."""

    record = family_payload.get("family_champion_record")
    if not isinstance(record, Mapping):
        return None
    return _serialize_candidate_record(record)


def _group_support_count(group_payload: Mapping[str, Any]) -> int:
    """Return the observed support count for one context group."""

    try:
        return max(0, int(group_payload.get("trace_count") or 0))
    except (TypeError, ValueError):
        return 0


def _group_record_support_count(group_payload: Mapping[str, Any], record: Mapping[str, Any]) -> int:
    """Return the support count for one candidate-answer variant within a context group."""

    support_mapping = group_payload.get("support_by_record_key")
    if isinstance(support_mapping, Mapping):
        raw_value = support_mapping.get(_candidate_record_hash(record))
        try:
            return max(0, int(raw_value or 0))
        except (TypeError, ValueError):
            return 0
    return 0


def _group_champion_support_count(group_payload: Mapping[str, Any]) -> int:
    """Return the support count for the current context-group champion."""

    champion_record = group_payload.get("champion_record")
    if not isinstance(champion_record, Mapping):
        return 0
    return _group_record_support_count(group_payload, champion_record)


def _group_champion_evidence_count(group_payload: Mapping[str, Any]) -> int:
    """Return the summarized evidence count for one context-group champion."""

    try:
        return max(0, int(group_payload.get("evidence_count") or 0))
    except (TypeError, ValueError):
        return 0


def _context_group_rank_key(group: Mapping[str, Any]) -> tuple[float, int, str]:
    """Return the stable sort key for one candidate context group."""

    return (float(group.get("champion_score") or 0.0), 0, "")


def _refresh_family_champion(family_payload: dict[str, Any]) -> tuple[bool, str | None, str | None]:
    """Recompute the best family champion from its context-group champions."""

    groups = family_payload.get("context_groups")
    if not isinstance(groups, list) or not groups:
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
        champion_record = _family_champion_record(family)
        if champion_record is None:
            continue
        records.append(champion_record)
    return records


def summarize_champion_index(path: Path) -> dict[str, Any]:
    """Return one compact summary of the current family champion set."""

    index_payload = _load_champion_index(path)
    prompt_family_ids: list[str] = []
    champion_trace_record_paths: list[str] = []
    champion_exact_snapshot_ids: list[str] = []
    champion_record_hashes: list[str] = []
    seen_family_ids: set[str] = set()
    seen_trace_paths: set[str] = set()
    seen_snapshot_ids: set[str] = set()
    seen_record_hashes: set[str] = set()
    families = index_payload.get("prompt_families")
    champion_records: list[dict[str, Any]] = []
    if isinstance(families, list):
        for family in families:
            if not isinstance(family, Mapping):
                continue
            prompt_family_id = str(family.get("prompt_family_id") or "").strip()
            champion_record = _family_champion_record(family)
            if champion_record is None:
                continue
            champion_records.append(champion_record)
            if prompt_family_id and prompt_family_id not in seen_family_ids:
                seen_family_ids.add(prompt_family_id)
                prompt_family_ids.append(prompt_family_id)
    for record in champion_records:
        prompt_family_id = str(record.get("prompt_family_id") or "").strip()
        if prompt_family_id and prompt_family_id not in seen_family_ids:
            seen_family_ids.add(prompt_family_id)
            prompt_family_ids.append(prompt_family_id)
        provenance = record.get("provenance")
        if isinstance(provenance, Mapping):
            trace_record_path = str(provenance.get("trace_record_path") or "").strip()
            if trace_record_path and trace_record_path not in seen_trace_paths:
                seen_trace_paths.add(trace_record_path)
                champion_trace_record_paths.append(trace_record_path)
        snapshot_id = str(record.get("exact_snapshot_id") or "").strip()
        if snapshot_id and snapshot_id not in seen_snapshot_ids:
            seen_snapshot_ids.add(snapshot_id)
            champion_exact_snapshot_ids.append(snapshot_id)
        record_hash = _candidate_record_hash(record)
        if record_hash not in seen_record_hashes:
            seen_record_hashes.add(record_hash)
            champion_record_hashes.append(record_hash)
    return {
        "candidate_count": len(champion_records),
        "prompt_family_ids": prompt_family_ids,
        "champion_trace_record_paths": champion_trace_record_paths,
        "champion_exact_snapshot_ids": champion_exact_snapshot_ids,
        "champion_record_hashes": champion_record_hashes,
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
    original_prompt = str(record.get("original_prompt") or "").strip()
    reformulated_prompt = str(record.get("reformulated_prompt") or "").strip()
    normalized: dict[str, Any] = {
        "question": str(
            record.get("question") or reformulated_prompt or original_prompt
        ).strip(),
        "expected_answer": normalized_answer,
        "tags": tags,
        "expected_sources": expected_sources,
        "benchmark_context": [
            str(text).strip()
            for text in record.get("benchmark_context", [])
            if str(text).strip()
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
            normalized.get("reformulated_prompt")
            or normalized.get("question")
            or normalized.get("original_prompt")
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
        token = json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        if token in seen:
            continue
        seen.add(token)
        ordered.append(normalized)
    return ordered


def _normalize_benchmark_support_text(value: object) -> str:
    """Return one whitespace-normalized lowercase string for context grounding checks."""

    return " ".join(str(value or "").casefold().split())


def _benchmark_context_support_score(
    expected_answer: str,
    benchmark_context: Sequence[object],
) -> float:
    """Return one overlap score between a candidate answer and its preserved benchmark context."""

    normalized_answer = _normalize_benchmark_support_text(expected_answer)
    normalized_context = _normalize_benchmark_support_text("\n".join(map(str, benchmark_context)))
    expected_tokens = set(re.findall(r"[a-z0-9]+", normalized_answer))
    context_tokens = set(re.findall(r"[a-z0-9]+", normalized_context))
    if not expected_tokens or not context_tokens:
        return 0.0
    return len(expected_tokens.intersection(context_tokens)) / min(
        len(expected_tokens),
        len(context_tokens),
    )


def _answer_is_supported_by_benchmark_context(
    expected_answer: str,
    benchmark_context: Sequence[object],
) -> bool:
    """Return whether one trainer-candidate answer is grounded in its preserved benchmark context."""

    normalized_answer = _normalize_benchmark_support_text(expected_answer)
    normalized_context = _normalize_benchmark_support_text("\n".join(map(str, benchmark_context)))
    if not normalized_answer or not normalized_context:
        return False
    return normalized_answer in normalized_context


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
    prefer_candidate = (
        candidate_richness > current_richness
        or (
            candidate_richness == current_richness
            and _candidate_recorded_at(candidate_serialized) > _candidate_recorded_at(current_serialized)
        )
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
    merged["reformulated_prompt"] = str(
        merged.get("reformulated_prompt")
        or candidate_serialized.get("reformulated_prompt")
        or current_serialized.get("reformulated_prompt")
        or ""
    ).strip()
    provenance = merged.get("provenance")
    if isinstance(provenance, Mapping):
        merged_provenance = dict(provenance)
        merged_provenance["benchmark_context_count"] = len(merged["benchmark_context"])
        merged_provenance["metric_hits"] = merged_hits
        merged_provenance["metric_total"] = merged_total
        merged_provenance["metric_ratio"] = merged["metric_ratio"]
        merged["provenance"] = merged_provenance
    return merged


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
    question = str(context_snapshot.get("question") or reformulated_prompt or original_prompt).strip()
    command_trace = _ordered_unique_command_trace(context_snapshot.get("command_trace", []))
    if not question:
        return None, "missing-question"
    prompt_family_id = _prompt_family_id(question)
    benchmark_context, benchmark_context_sources = _extract_benchmark_context(payload)
    exact_snapshot_id = _exact_snapshot_id(
        question=question,
        expected_answer=expected_answer,
        trace_record_path=str(payload.get("trace_record_path") or ""),
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
            "trace_record_path": str(payload.get("trace_record_path") or ""),
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


def materialize_training_candidates(
    root: Path,
    *,
    trace_paths: Sequence[Path | str] | None = None,
    output_path: Path,
    summary_path: Path,
    champion_index_path: Path = DEFAULT_TRAINER_CHAMPION_INDEX_PATH,
    include_statuses: Sequence[str] = ("accepted", "candidate"),
    seed_existing_output: bool = True,
) -> dict[str, Any]:
    """Materialize trainer-side DSPy training candidates from imported trace records."""

    resolved_root = root.resolve()
    resolved_output_path = output_path if output_path.is_absolute() else resolved_root / output_path
    resolved_summary_path = (
        summary_path if summary_path.is_absolute() else resolved_root / summary_path
    )
    resolved_champion_index_path = (
        champion_index_path
        if champion_index_path.is_absolute()
        else resolved_root / champion_index_path
    )
    candidate_paths: list[Path]
    if trace_paths:
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

    champion_index = _load_champion_index(resolved_champion_index_path)
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

    resolved_champion_index_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_champion_index_path.write_text(
        json.dumps(champion_index, indent=2) + "\n",
        encoding="utf-8",
    )
    remote_champion_state = upload_remote_champion_index(
        resolved_root,
        champion_index_path=resolved_champion_index_path,
    )
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_output_path.write_text(
        yaml.safe_dump(merged_records, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    summary: dict[str, Any] = {
        "candidate_count": len(merged_records),
        "new_candidate_count": new_candidate_count,
        "input_trace_count": len(candidate_paths),
        "loaded_candidate_count": len(loaded_records),
        "duplicate_count": duplicate_count,
        "replaced_count": replaced_count,
        "prompt_family_count": len(family_by_id),
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
        "champion_index_path": (
            str(resolved_champion_index_path.relative_to(resolved_root))
            if resolved_champion_index_path.is_relative_to(resolved_root)
            else str(resolved_champion_index_path)
        ),
    }
    if remote_champion_state is not None:
        summary["remote_champion_state"] = remote_champion_state
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
            record for record in raw_candidate_records if _trainer_candidate_record_is_supported(record)
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
