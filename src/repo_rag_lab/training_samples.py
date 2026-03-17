"""Helpers for loading and summarizing starter DSPy training examples."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


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
