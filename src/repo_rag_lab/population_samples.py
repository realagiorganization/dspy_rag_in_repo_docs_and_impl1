from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PopulationCandidate:
    """A candidate source to include in sample population experiments."""

    source: str
    rationale: str
    priority: int


def normalize_population_candidates(records: list[dict[str, Any]]) -> list[PopulationCandidate]:
    """
    Normalize raw candidate records.

    >>> candidates = normalize_population_candidates([
    ...     {"source": "README.md", "rationale": "Core overview", "priority": 1},
    ...     {
    ...         "source": "documentation/inspired",
    ...         "rationale": "Reference material",
    ...         "priority": "2",
    ...     },
    ... ])
    >>> candidates[0].source
    'README.md'
    >>> [candidate.priority for candidate in candidates]
    [1, 2]
    """

    items = [
        PopulationCandidate(
            source=str(record["source"]).strip(),
            rationale=str(record["rationale"]).strip(),
            priority=int(record["priority"]),
        )
        for record in records
    ]
    return sorted(items, key=lambda item: (item.priority, item.source))


def group_population_candidates(
    candidates: list[PopulationCandidate], batch_size: int = 2
) -> list[list[PopulationCandidate]]:
    """
    Group candidates for notebook review.

    >>> candidates = normalize_population_candidates([
    ...     {"source": "a", "rationale": "r1", "priority": 1},
    ...     {"source": "b", "rationale": "r2", "priority": 2},
    ...     {"source": "c", "rationale": "r3", "priority": 3},
    ... ])
    >>> [batch[0].source for batch in group_population_candidates(candidates, batch_size=2)]
    ['a', 'c']
    """

    return [
        candidates[index : index + batch_size] for index in range(0, len(candidates), batch_size)
    ]


def summarize_population_candidates(candidates: list[PopulationCandidate]) -> dict[str, Any]:
    """
    Summarize a candidate set for notebook output.

    >>> summary = summarize_population_candidates(normalize_population_candidates([
    ...     {"source": "README.md", "rationale": "overview", "priority": 1},
    ...     {
    ...         "source": "samples/training/repository_training_examples.yaml",
    ...         "rationale": "training set",
    ...         "priority": 2,
    ...     },
    ... ]))
    >>> summary["candidate_count"]
    2
    >>> summary["highest_priority_source"]
    'README.md'
    """

    return {
        "candidate_count": len(candidates),
        "highest_priority_source": candidates[0].source if candidates else "",
        "sources": [candidate.source for candidate in candidates],
    }


def load_population_candidates(path: Path) -> list[PopulationCandidate]:
    """Load and normalize a YAML population candidate list."""

    records = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return normalize_population_candidates(records)
