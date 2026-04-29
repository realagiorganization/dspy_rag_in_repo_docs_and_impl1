"""Helpers for loading and summarizing starter DSPy training examples."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .runtime_artifacts import load_json_object


@dataclass(frozen=True)
class TrainingExample:
    """A normalized repository question-answer example."""

    question: str
    expected_answer: str
    tags: tuple[str, ...]
    expected_sources: tuple[str, ...] = ()


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

    expected_sources = [
        str(source).strip() for source in payload.get("sources", []) if str(source).strip()
    ]
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
            "expected_sources": expected_sources,
            "candidate_status": acceptance_status or None,
            "provenance": {
                "trace_record_path": str(payload.get("trace_record_path") or ""),
                "source_command": str(payload.get("source_command") or ""),
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
    include_statuses: Sequence[str] = ("accepted", "candidate"),
) -> dict[str, Any]:
    """Materialize trainer-side DSPy training candidates from imported trace records."""

    resolved_root = root.resolve()
    resolved_output_path = output_path if output_path.is_absolute() else resolved_root / output_path
    resolved_summary_path = (
        summary_path if summary_path.is_absolute() else resolved_root / summary_path
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

    existing_records = []
    if resolved_output_path.is_file():
        existing_payload = yaml.safe_load(resolved_output_path.read_text(encoding="utf-8")) or []
        if isinstance(existing_payload, list):
            existing_records = [
                record for record in existing_payload if isinstance(record, Mapping)
            ]

    existing_keys = {_candidate_record_key(record) for record in existing_records}
    new_records: list[dict[str, Any]] = []
    duplicate_count = 0
    for record in loaded_records:
        key = _candidate_record_key(record)
        if key in existing_keys:
            duplicate_count += 1
            continue
        existing_keys.add(key)
        new_records.append(record)

    merged_records = [dict(record) for record in existing_records] + new_records
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_output_path.write_text(
        yaml.safe_dump(merged_records, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    summary: dict[str, Any] = {
        "candidate_count": len(merged_records),
        "new_candidate_count": len(new_records),
        "input_trace_count": len(candidate_paths),
        "loaded_candidate_count": len(loaded_records),
        "duplicate_count": duplicate_count,
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

    merged_records: list[dict[str, Any]] = []
    merged_keys: set[tuple[str, str, tuple[str, ...], str]] = set()
    for record in base_records:
        normalized = {
            "question": str(record.get("question") or "").strip(),
            "expected_answer": str(record.get("expected_answer") or "").strip(),
            "tags": _dedupe_tags(record.get("tags", [])),
            "expected_sources": [
                str(source).strip()
                for source in record.get("expected_sources", [])
                if str(source).strip()
            ],
        }
        key = _candidate_record_key(normalized)
        if key in merged_keys:
            continue
        merged_keys.add(key)
        merged_records.append(normalized)

    new_candidate_count = 0
    duplicate_candidate_count = 0
    for record in candidate_records:
        normalized = {
            "question": str(record.get("question") or "").strip(),
            "expected_answer": str(record.get("expected_answer") or "").strip(),
            "tags": _dedupe_tags(record.get("tags", [])),
            "expected_sources": [
                str(source).strip()
                for source in record.get("expected_sources", [])
                if str(source).strip()
            ],
        }
        key = _candidate_record_key(normalized)
        if key in merged_keys:
            duplicate_candidate_count += 1
            continue
        merged_keys.add(key)
        merged_records.append(normalized)
        new_candidate_count += 1

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
