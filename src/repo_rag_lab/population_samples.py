"""Helpers for reviewing and batching starter corpus-population inputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PopulationCandidate:
    """A prioritized repository source for corpus-population planning."""

    source: str
    rationale: str
    priority: int


def normalize_population_candidates(records: list[dict[str, Any]]) -> list[PopulationCandidate]:
    """
    Normalize raw YAML records into sorted population candidates.

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
    Group candidates into notebook-friendly review batches.

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
    Summarize the current population candidate set for notebook display.

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


def validate_population_candidates(
    candidates: list[PopulationCandidate], root: Path | None = None
) -> list[str]:
    """
    Validate starter corpus candidates before notebook assertions run.

    >>> issues = validate_population_candidates([
    ...     PopulationCandidate(source="README.md", rationale="overview", priority=1)
    ... ])
    >>> issues
    []
    """

    issues: list[str] = []
    seen_sources: set[str] = set()
    for index, candidate in enumerate(candidates, start=1):
        if not candidate.source:
            issues.append(f"Candidate {index} is missing a source.")
        if not candidate.rationale:
            issues.append(f"Candidate {index} is missing a rationale.")
        if candidate.priority < 1:
            issues.append(f"Candidate {index} priority must be positive.")
        if candidate.source in seen_sources:
            issues.append(f"Candidate {index} duplicates source {candidate.source}.")
        seen_sources.add(candidate.source)
        if root is None or not candidate.source:
            continue
        if Path(candidate.source).is_absolute():
            issues.append(f"Candidate {index} source must be relative: {candidate.source}")
            continue
        if not (root / candidate.source).exists():
            issues.append(f"Candidate {index} source does not exist: {candidate.source}")
    return issues


def discover_submodule_documentation(root: Path) -> list[PopulationCandidate]:
    """Discover README or docs files under configured git submodules when present."""

    gitmodules_path = root / ".gitmodules"
    if not gitmodules_path.exists():
        return []

    submodule_paths: list[Path] = []
    for line in gitmodules_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("path ="):
            continue
        _, _, relative_path = stripped.partition("=")
        submodule_paths.append(root / relative_path.strip())

    candidates: list[PopulationCandidate] = []
    for submodule_path in submodule_paths:
        for pattern in ("README.md", "docs/*.md", "docs/**/*.md"):
            for path in sorted(submodule_path.glob(pattern)):
                if not path.is_file():
                    continue
                candidates.append(
                    PopulationCandidate(
                        source=str(path.relative_to(root)),
                        rationale="Submodule documentation discovered for follow-up corpus work.",
                        priority=999,
                    )
                )
    return candidates


def extend_population_candidates(
    root: Path, candidates: list[PopulationCandidate]
) -> list[PopulationCandidate]:
    """
    Extend the starter candidate list with docs needed by the scaffolded notebooks.

    >>> root = Path('/tmp/example')
    >>> extras = extend_population_candidates(root, [
    ...     PopulationCandidate(source='README.md', rationale='overview', priority=1)
    ... ])
    >>> extras[0].source
    'README.md'
    """

    next_priority = max((candidate.priority for candidate in candidates), default=0) + 1
    additions = [
        PopulationCandidate(
            source="documentation/package-api.md",
            rationale="Package API notes support notebook validation and utility questions.",
            priority=next_priority,
        ),
        PopulationCandidate(
            source="documentation/mcp-discovery.md",
            rationale="MCP discovery notes ground follow-up notebook corpus work.",
            priority=next_priority + 1,
        ),
    ]
    additions.extend(discover_submodule_documentation(root))

    by_source: dict[str, PopulationCandidate] = {
        candidate.source: candidate for candidate in candidates
    }
    current_priority = next_priority + len(additions)
    for addition in additions:
        if addition.source in by_source:
            continue
        if not (root / addition.source).exists():
            continue
        by_source[addition.source] = PopulationCandidate(
            source=addition.source,
            rationale=addition.rationale,
            priority=current_priority,
        )
        current_priority += 1
    return sorted(by_source.values(), key=lambda item: (item.priority, item.source))


def rerank_population_candidates(
    candidates: list[PopulationCandidate], source_hits: dict[str, int]
) -> list[PopulationCandidate]:
    """
    Re-rank candidates using empirical retrieval hits while preserving stable ties.

    >>> items = rerank_population_candidates([
    ...     PopulationCandidate(source='README.md', rationale='overview', priority=2),
    ...     PopulationCandidate(source='utilities/README.md', rationale='utilities', priority=1),
    ... ], {'README.md': 3})
    >>> [item.source for item in items]
    ['README.md', 'utilities/README.md']
    """

    ranked = sorted(
        candidates,
        key=lambda item: (-source_hits.get(item.source, 0), item.priority, item.source),
    )
    return [
        PopulationCandidate(
            source=item.source,
            rationale=item.rationale,
            priority=index,
        )
        for index, item in enumerate(ranked, start=1)
    ]


def load_population_candidates(path: Path) -> list[PopulationCandidate]:
    """Load a YAML population candidate file and normalize its records."""

    records = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return normalize_population_candidates(records)
