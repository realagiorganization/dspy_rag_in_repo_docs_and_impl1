"""Helpers for loading and summarizing starter DSPy training examples."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .runtime_artifacts import (
    DEFAULT_TRAINER_CHAMPION_INDEX_PATH,
    load_json_object,
)


@dataclass(frozen=True)
class TrainingExample:
    """A normalized repository question-answer example."""

    question: str
    expected_answer: str
    tags: tuple[str, ...]
    expected_sources: tuple[str, ...] = ()


TRAINER_CHAMPION_INDEX_SCHEMA_VERSION = 1
TRAINER_CHAMPION_INDEX_KIND = "repo-rag-trainer-champion-index"
CONTEXT_GROUP_MATCH_THRESHOLD = 0.8
CONTEXT_GROUP_SOFT_THRESHOLD = 0.6
CHAMPION_REPLACEMENT_DELTA = 0.05


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
        normalized.append(
            TrainingExample(
                question=str(record["question"]).strip(),
                expected_answer=str(record["expected_answer"]).strip(),
                tags=tags,
                expected_sources=expected_sources,
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
        "benchmark_count": sum(1 for example in examples if example.expected_sources),
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

    try:
        left_value = int(left) if left not in (None, "") else None
    except (TypeError, ValueError):
        left_value = None
    try:
        right_value = int(right) if right not in (None, "") else None
    except (TypeError, ValueError):
        right_value = None
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
    return {
        "question": _normalize_question_text(
            payload.get("question") or trace_mapping.get("question")
        ),
        "retrieval_mode": retrieval_mode,
        "mode": mode,
        "context_field": context_field,
        "sources": observed_sources,
        "evidence_fingerprints": evidence_fingerprints,
        "evidence_count": len(evidence_fingerprints),
        "source_count": source_count,
        "context_count": context_count,
        "top_k": top_k,
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


def _trace_quality_score(
    *,
    expected_answer: str,
    acceptance_status: str,
    execution_status: str,
    used_baseline_fallback: bool,
    source_count: int,
    top_k: int | None,
    program_loaded: bool,
) -> float:
    """Return a bounded trainer-side quality score for one trace snapshot."""

    acceptance_score = {
        "accepted": 1.0,
        "candidate": 0.7,
        "rejected": 0.0,
    }.get(acceptance_status, 0.4)
    execution_score = 1.0 if execution_status.casefold() == "success" else 0.0
    fallback_score = 0.0 if used_baseline_fallback else 1.0
    answer_length = len(expected_answer.strip())
    answer_quality = min(answer_length / 400.0, 1.0) if answer_length else 0.0
    effective_top_k = max(1, top_k or source_count or 1)
    retrieval_quality = min(max(source_count, 0) / effective_top_k, 1.0)
    program_score = 1.0 if program_loaded else 0.0
    score = (
        0.30 * acceptance_score
        + 0.25 * execution_score
        + 0.15 * fallback_score
        + 0.15 * retrieval_quality
        + 0.10 * answer_quality
        + 0.05 * program_score
    )
    return round(score, 6)


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

    similarity = _context_similarity(candidate_snapshot, group_payload)
    if similarity >= CONTEXT_GROUP_MATCH_THRESHOLD:
        return True
    if similarity < CONTEXT_GROUP_SOFT_THRESHOLD:
        return False
    source_overlap = _jaccard_similarity(
        _normalized_source_tokens(candidate_snapshot.get("sources", [])),
        _normalized_source_tokens(group_payload.get("sources", [])),
    )
    candidate_evidence = _normalized_source_tokens(
        candidate_snapshot.get("evidence_fingerprints", [])
    )
    group_evidence = _normalized_source_tokens(group_payload.get("evidence_fingerprints", []))
    if candidate_evidence and group_evidence:
        evidence_overlap = _jaccard_similarity(candidate_evidence, group_evidence)
        return source_overlap >= 0.5 and evidence_overlap >= 0.25
    return source_overlap >= 0.5


def _serialize_candidate_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON/YAML-safe trainer candidate record copy."""

    normalized = _normalize_materialized_candidate_record(record)
    for field_name in (
        "prompt_family_id",
        "context_group_id",
        "exact_snapshot_id",
        "quality_score",
        "support_count",
    ):
        if field_name in record and record.get(field_name) not in (None, ""):
            normalized[field_name] = record.get(field_name)
    provenance = record.get("provenance")
    if isinstance(provenance, Mapping):
        normalized["provenance"] = dict(provenance)
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


def _seed_champion_index_from_existing_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a first champion index from legacy materialized candidate rows."""

    index_payload = _fresh_champion_index()
    canonical_records: dict[str, Mapping[str, Any]] = {}
    family_order: list[str] = []
    for record in records:
        question = _normalize_question_text(record.get("question"))
        if not question:
            continue
        prompt_family_id = str(record.get("prompt_family_id") or _prompt_family_id(question))
        if prompt_family_id not in canonical_records:
            family_order.append(prompt_family_id)
        canonical_records[prompt_family_id] = record

    families: list[dict[str, Any]] = []
    for prompt_family_id in family_order:
        record = canonical_records[prompt_family_id]
        question = _normalize_question_text(record.get("question"))
        sources = _normalized_source_tokens(record.get("expected_sources", []))
        context_group_id = str(
            record.get("context_group_id")
            or f"cg-{_stable_hash(prompt_family_id, sources or ['legacy'])}"
        )
        quality_score = float(record.get("quality_score") or 0.5)
        support_count = int(record.get("support_count") or 1)
        champion_record = _serialize_candidate_record(
            {
                **dict(record),
                "prompt_family_id": prompt_family_id,
                "context_group_id": context_group_id,
                "quality_score": quality_score,
                "support_count": support_count,
            }
        )
        families.append(
            {
                "prompt_family_id": prompt_family_id,
                "question": question,
                "normalized_question": question.casefold(),
                "family_champion_context_group_id": context_group_id,
                "family_champion_score": quality_score,
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
                        "champion_score": quality_score,
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
        key=lambda group: (
            float(group.get("champion_score") or 0.0),
            _group_champion_support_count(group),
            str(group.get("context_group_id") or ""),
        ),
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
        incumbent_support = _group_champion_support_count(incumbent_group)
        incumbent_evidence_count = _group_champion_evidence_count(incumbent_group)
        selected_group = incumbent_group
        for challenger_group in ranked_groups:
            if challenger_group is incumbent_group:
                continue
            challenger_score = float(challenger_group.get("champion_score") or 0.0)
            challenger_support = _group_champion_support_count(challenger_group)
            challenger_evidence_count = _group_champion_evidence_count(challenger_group)

            should_switch = False
            if (
                challenger_score > incumbent_score + CHAMPION_REPLACEMENT_DELTA
                or (
                    abs(challenger_score - incumbent_score) <= CHAMPION_REPLACEMENT_DELTA
                    and challenger_support > incumbent_support
                )
                or (
                    abs(challenger_score - incumbent_score) <= CHAMPION_REPLACEMENT_DELTA
                    and challenger_support == incumbent_support
                    and challenger_evidence_count > incumbent_evidence_count
                )
            ):
                should_switch = True

            if should_switch:
                selected_group = challenger_group
                incumbent_score = challenger_score
                incumbent_support = challenger_support
                incumbent_evidence_count = challenger_evidence_count

    best_group = selected_group
    best_group_id = str(best_group.get("context_group_id") or "") or None
    best_record = _serialize_candidate_record(best_group.get("champion_record", {}))
    best_snapshot_id = str(best_record.get("exact_snapshot_id") or "") or None
    family_payload["family_champion_context_group_id"] = best_group_id
    family_payload["family_champion_score"] = float(best_group.get("champion_score") or 0.0)
    family_payload["family_champion_record"] = best_record
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


def _find_or_create_context_group(
    family_payload: dict[str, Any],
    *,
    context_snapshot: Mapping[str, Any],
    question: str,
    prompt_family_id: str,
    exact_snapshot_id: str,
) -> tuple[dict[str, Any], bool]:
    """Return the matching context group for a trace snapshot, creating one when needed."""

    groups = family_payload.setdefault("context_groups", [])
    if not isinstance(groups, list):
        groups = []
        family_payload["context_groups"] = groups
    for group in groups:
        if isinstance(group, dict) and _matches_context_group(context_snapshot, group):
            return group, False
    context_group_id = (
        f"cg-{_stable_hash(prompt_family_id, question, context_snapshot, exact_snapshot_id)}"
    )
    group_payload = {
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

    normalized: dict[str, Any] = {
        "question": str(record.get("question") or "").strip(),
        "expected_answer": str(record.get("expected_answer") or "").strip(),
        "tags": tags,
        "expected_sources": expected_sources,
    }
    candidate_status = str(record.get("candidate_status") or "").strip()
    if candidate_status:
        normalized["candidate_status"] = candidate_status
    provenance = record.get("provenance")
    if isinstance(provenance, Mapping):
        normalized["provenance"] = dict(provenance)
    return normalized


def _normalize_combined_training_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one base/candidate record for the generated trainer compile dataset."""

    normalized = _normalize_materialized_candidate_record(record)
    return {
        "question": str(normalized.get("question") or "").strip(),
        "expected_answer": str(normalized.get("expected_answer") or "").strip(),
        "tags": _dedupe_tags(normalized.get("tags", [])),
        "expected_sources": [
            str(source).strip()
            for source in normalized.get("expected_sources", [])
            if str(source).strip()
        ],
    }


def _training_candidate_from_trace_record(
    payload: Mapping[str, Any],
    *,
    include_statuses: set[str],
) -> tuple[dict[str, Any] | None, str | None]:
    """Build one training-candidate record from an imported trace record."""

    question = str(payload.get("question") or "").strip()
    expected_answer = str(payload.get("answer") or payload.get("response_text") or "").strip()
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
    question = str(context_snapshot.get("question") or "").strip()
    if not question:
        return None, "missing-question"
    prompt_family_id = _prompt_family_id(question)
    exact_snapshot_id = _exact_snapshot_id(
        question=question,
        expected_answer=expected_answer,
        trace_record_path=str(payload.get("trace_record_path") or ""),
        recorded_at=str(trace_mapping.get("recorded_at") or ""),
        context_snapshot=context_snapshot,
    )
    observed_sources = list(context_snapshot.get("sources", []))
    quality_score = _trace_quality_score(
        expected_answer=expected_answer,
        acceptance_status=acceptance_status,
        execution_status=str(outcome_mapping.get("execution_status") or ""),
        used_baseline_fallback=bool(outcome_mapping.get("used_baseline_fallback")),
        source_count=int(context_snapshot.get("source_count") or 0),
        top_k=(
            int(context_snapshot.get("top_k"))
            if isinstance(context_snapshot.get("top_k"), int)
            else None
        ),
        program_loaded=bool(context_snapshot.get("program_loaded")),
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

    return (
        {
            "question": question,
            "expected_answer": expected_answer,
            "tags": tags,
            # Imported worker traces may originate from arbitrary repositories, so the global
            # trainer keeps their source paths in provenance instead of turning them into
            # repo-local retrieval benchmarks.
            "expected_sources": [],
            "candidate_status": acceptance_status or None,
            "prompt_family_id": prompt_family_id,
            "exact_snapshot_id": exact_snapshot_id,
            "quality_score": quality_score,
            "support_count": 1,
            "provenance": {
                "trace_record_path": str(payload.get("trace_record_path") or ""),
                "source_command": str(payload.get("source_command") or ""),
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
            },
        },
        None,
    )


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

    existing_records: list[dict[str, Any]] = []
    if seed_existing_output and resolved_output_path.is_file():
        existing_payload = yaml.safe_load(resolved_output_path.read_text(encoding="utf-8")) or []
        if isinstance(existing_payload, list):
            existing_records = [
                _normalize_materialized_candidate_record(record)
                for record in existing_payload
                if isinstance(record, Mapping)
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
    prompt_family_count_before = len(family_by_id)
    for record in loaded_records:
        prompt_family_id = str(record.get("prompt_family_id") or "").strip()
        exact_snapshot_id = str(record.get("exact_snapshot_id") or "").strip()
        question = _normalize_question_text(record.get("question"))
        provenance = record.get("provenance")
        context_snapshot = {}
        if isinstance(provenance, Mapping):
            candidate_snapshot = provenance.get("context_snapshot")
            if isinstance(candidate_snapshot, Mapping):
                context_snapshot = dict(candidate_snapshot)
        if not prompt_family_id or not exact_snapshot_id or not question or not context_snapshot:
            continue
        if exact_snapshot_id in seen_snapshot_ids:
            duplicate_count += 1
            continue
        seen_snapshot_ids.add(exact_snapshot_id)

        family_payload = family_by_id.get(prompt_family_id)
        if family_payload is None:
            family_payload = {
                "prompt_family_id": prompt_family_id,
                "question": question,
                "normalized_question": question.casefold(),
                "family_champion_context_group_id": None,
                "family_champion_score": None,
                "family_champion_record": None,
                "context_groups": [],
            }
            family_by_id[prompt_family_id] = family_payload
            family_order.append(prompt_family_id)

        previous_family_record = _family_champion_record(family_payload)
        previous_family_key = (
            _candidate_record_key(previous_family_record)
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
        candidate_score = float(record.get("quality_score") or 0.0)
        serialized_record = _serialize_candidate_record(record)
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
        current_group_support = (
            _group_record_support_count(context_group, current_group_record)
            if isinstance(current_group_record, Mapping)
            else 0
        )
        replace_group_champion = False
        if not isinstance(current_group_record, Mapping):
            replace_group_champion = True
        elif _candidate_record_key(current_group_record) == _candidate_record_key(
            serialized_record
        ):
            current_group_record = dict(current_group_record)
            current_group_record["support_count"] = candidate_support
            context_group["champion_record"] = current_group_record
            context_group["champion_score"] = max(
                current_group_score,
                candidate_score,
            )
        elif candidate_score > current_group_score + CHAMPION_REPLACEMENT_DELTA or (
            abs(candidate_score - current_group_score) <= CHAMPION_REPLACEMENT_DELTA
            and candidate_support > current_group_support
        ):
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
        current_family_key = (
            _candidate_record_key(current_family_record)
            if current_family_record is not None
            else None
        )
        if previous_family_record is None and current_family_record is not None:
            new_candidate_count += 1
        elif (
            previous_family_key is not None
            and current_family_key is not None
            and previous_family_key != current_family_key
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
        "new_prompt_family_count": max(0, len(family_by_id) - prompt_family_count_before),
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
    if resolved_candidates_path.is_file():
        candidate_payload = (
            yaml.safe_load(resolved_candidates_path.read_text(encoding="utf-8")) or []
        )
        if not isinstance(candidate_payload, list):
            raise ValueError(
                f"Trainer candidate payload must be a YAML list: {resolved_candidates_path}"
            )
        candidate_records = [record for record in candidate_payload if isinstance(record, Mapping)]

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
