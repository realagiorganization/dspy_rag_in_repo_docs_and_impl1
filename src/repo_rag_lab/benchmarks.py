"""Retrieval benchmark helpers for notebook assertions and logging."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .corpus import RepoDocument, load_documents
from .retrieval import chunk_documents, retrieve
from .training_samples import TrainingExample

BENCHMARK_EXCLUDED_PARTS = {
    ".git",
    ".github",
    ".mypy_cache",
    ".pre-commit-cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "artifacts",
    "build",
    "data",
    "dist",
    "target",
    "tests",
}
BENCHMARK_EXCLUDED_PATH_SNIPPETS = (
    "REPO_COMPLETENESS_CHECKLIST.md",
    "README.DSPY.MD",
    "documentation/hushwheel-fixture-rag-guide.md",
    "samples/population/",
    "samples/logs/",
    "samples/training/",
)


@dataclass(frozen=True)
class RetrievalBenchmark:
    """A notebook-friendly retrieval assertion."""

    question: str
    expected_sources: tuple[str, ...]
    tags: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalBenchmarkResult:
    """The result of evaluating one retrieval benchmark."""

    question: str
    expected_sources: tuple[str, ...]
    retrieved_sources: tuple[str, ...]
    matched_sources: tuple[str, ...]
    tags: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """Return ``True`` when retrieval found at least one expected source."""

        return bool(self.matched_sources)


def build_retrieval_benchmarks(examples: list[TrainingExample]) -> list[RetrievalBenchmark]:
    """
    Build retrieval assertions from training examples that declare expected sources.

    >>> build_retrieval_benchmarks([
    ...     TrainingExample(
    ...         question='Q1',
    ...         expected_answer='A1',
    ...         tags=('repo',),
    ...         expected_sources=('README.md',),
    ...     ),
    ...     TrainingExample(question='Q2', expected_answer='A2', tags=('docs',)),
    ... ])[0].expected_sources
    ('README.md',)
    """

    return [
        RetrievalBenchmark(
            question=example.question,
            expected_sources=example.expected_sources,
            tags=example.tags,
        )
        for example in examples
        if example.expected_sources
    ]


def _select_benchmark_documents(root: Path) -> list[RepoDocument]:
    """Load a fairness-filtered benchmark corpus from repository documents."""

    documents: list[RepoDocument] = []
    for document in load_documents(root):
        relative_path = document.path.relative_to(root)
        if any(part in BENCHMARK_EXCLUDED_PARTS for part in relative_path.parts):
            continue
        path_text = str(relative_path)
        if any(snippet in path_text for snippet in BENCHMARK_EXCLUDED_PATH_SNIPPETS):
            continue
        documents.append(document)
    return documents


def _unique_in_order(items: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return tuple(ordered)


def evaluate_retrieval_benchmarks(
    root: Path, benchmarks: list[RetrievalBenchmark], top_k: int = 4
) -> list[RetrievalBenchmarkResult]:
    """Evaluate retrieval assertions against a fairness-filtered benchmark corpus."""

    chunks = chunk_documents(_select_benchmark_documents(root))
    results: list[RetrievalBenchmarkResult] = []
    for benchmark in benchmarks:
        retrieved = retrieve(benchmark.question, chunks, top_k=top_k)
        retrieved_sources = _unique_in_order(
            [str(chunk.source.relative_to(root)) for chunk in retrieved]
        )
        expected_source_set = set(benchmark.expected_sources)
        matched_sources = tuple(
            source for source in retrieved_sources if source in expected_source_set
        )
        results.append(
            RetrievalBenchmarkResult(
                question=benchmark.question,
                expected_sources=benchmark.expected_sources,
                retrieved_sources=retrieved_sources,
                matched_sources=matched_sources,
                tags=benchmark.tags,
            )
        )
    return results


def summarize_benchmark_results(results: list[RetrievalBenchmarkResult]) -> dict[str, Any]:
    """
    Summarize benchmark outcomes for notebook display and artifact logs.

    >>> summary = summarize_benchmark_results([
    ...     RetrievalBenchmarkResult(
    ...         question='Q',
    ...         expected_sources=('README.md',),
    ...         retrieved_sources=('README.md', 'utilities/README.md'),
    ...         matched_sources=('README.md',),
    ...         tags=('repo',),
    ...     )
    ... ])
    >>> summary['pass_count']
    1
    >>> summary['retrieved_source_hits']['README.md']
    1
    """

    retrieved_hits = Counter(
        source for result in results for source in result.retrieved_sources if source
    )
    matched_hits = Counter(
        source for result in results for source in result.matched_sources if source
    )
    return {
        "case_count": len(results),
        "pass_count": sum(1 for result in results if result.passed),
        "pass_rate": (sum(1 for result in results if result.passed) / len(results))
        if results
        else 0.0,
        "retrieved_source_hits": dict(sorted(retrieved_hits.items())),
        "matched_source_hits": dict(sorted(matched_hits.items())),
        "results": [
            {
                "question": result.question,
                "expected_sources": list(result.expected_sources),
                "retrieved_sources": list(result.retrieved_sources),
                "matched_sources": list(result.matched_sources),
                "passed": result.passed,
                "tags": list(result.tags),
            }
            for result in results
        ],
    }
