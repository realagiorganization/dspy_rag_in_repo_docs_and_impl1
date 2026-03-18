"""Retrieval benchmark helpers for notebook assertions and logging."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .corpus import RepoDocument, load_documents
from .retrieval import chunk_documents, retrieve
from .training_samples import TrainingExample

BENCHMARK_EXCLUDED_PARTS = {
    ".codex",
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
BENCHMARK_EXCLUDED_PATHS = {
    Path("README.DSPY.MD"),
    Path("REPO_COMPLETENESS_CHECKLIST.md"),
    Path("documentation/hushwheel-fixture-rag-guide.md"),
}
BENCHMARK_EXCLUDED_PATH_PREFIXES = (
    Path("docs/audit"),
    Path("samples/logs"),
    Path("samples/population"),
    Path("samples/training"),
)
DEFAULT_RETRIEVAL_EVAL_TOP_K = 4
DEFAULT_RETRIEVAL_EVAL_TOP_K_SWEEP = (1, 2, 4, 8)


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

    @property
    def missed_sources(self) -> tuple[str, ...]:
        """Return expected sources that were not retrieved."""

        matched_source_set = set(self.matched_sources)
        return tuple(source for source in self.expected_sources if source not in matched_source_set)

    @property
    def first_relevant_rank(self) -> int | None:
        """Return the 1-based rank of the first retrieved expected source, if any."""

        matched_source_set = set(self.matched_sources)
        for index, source in enumerate(self.retrieved_sources, start=1):
            if source in matched_source_set:
                return index
        return None

    @property
    def reciprocal_rank(self) -> float:
        """Return reciprocal rank for the first relevant retrieved source."""

        first_rank = self.first_relevant_rank
        if first_rank is None:
            return 0.0
        return 1.0 / first_rank

    @property
    def source_recall(self) -> float:
        """Return source recall across the expected source set."""

        if not self.expected_sources:
            return 0.0
        return len(self.matched_sources) / len(self.expected_sources)

    @property
    def source_precision(self) -> float:
        """Return source precision across retrieved sources."""

        if not self.retrieved_sources:
            return 0.0
        return len(self.matched_sources) / len(self.retrieved_sources)

    @property
    def fully_covered(self) -> bool:
        """Return ``True`` when retrieval found every expected source."""

        return bool(self.expected_sources) and len(self.matched_sources) == len(
            self.expected_sources
        )


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


def is_benchmark_document_path(relative_path: Path) -> bool:
    """
    Return ``True`` when a repository-relative path belongs in the benchmark corpus.

    >>> is_benchmark_document_path(Path("README.md"))
    True
    >>> is_benchmark_document_path(Path("docs/audit/2026-03-18-retest-with-env-refresh.md"))
    False
    >>> is_benchmark_document_path(Path("samples/logs/20260318T010254Z-gh-runs.md"))
    False
    """

    if any(part in BENCHMARK_EXCLUDED_PARTS for part in relative_path.parts):
        return False
    if relative_path in BENCHMARK_EXCLUDED_PATHS:
        return False
    path_text = relative_path.as_posix()
    for prefix in BENCHMARK_EXCLUDED_PATH_PREFIXES:
        prefix_text = prefix.as_posix()
        if path_text == prefix_text or path_text.startswith(f"{prefix_text}/"):
            return False
    return True


def _select_benchmark_documents(root: Path) -> list[RepoDocument]:
    """Load a fairness-filtered benchmark corpus from repository documents."""

    documents: list[RepoDocument] = []
    for document in load_documents(root):
        relative_path = document.path.relative_to(root)
        if not is_benchmark_document_path(relative_path):
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


def normalize_retrieval_top_k_values(
    top_k_values: Sequence[int] | None = None,
    *,
    default_top_k: int = DEFAULT_RETRIEVAL_EVAL_TOP_K,
) -> tuple[int, ...]:
    """Normalize the retrieval evaluation top-k sweep into positive, unique values."""

    candidates = [*(top_k_values or DEFAULT_RETRIEVAL_EVAL_TOP_K_SWEEP), default_top_k]
    normalized: list[int] = []
    seen: set[int] = set()
    for candidate in sorted(candidates):
        if candidate <= 0:
            raise ValueError(f"Retrieval evaluation top-k values must be positive: {candidate}")
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return tuple(normalized)


def _coerce_summary_metric(summary: Mapping[str, object], metric_name: str) -> float:
    """Coerce a numeric retrieval-summary metric to ``float``."""

    if metric_name not in summary:
        raise AssertionError(f"Benchmark summary is missing required metric `{metric_name}`.")
    value = summary[metric_name]
    if not isinstance(value, (int, float, str)):
        raise AssertionError(f"Benchmark summary metric `{metric_name}` must be numeric.")
    return float(value)


def check_retrieval_quality_thresholds(
    summary: Mapping[str, object],
    *,
    minimum_pass_rate: float | None = None,
    minimum_source_recall: float | None = None,
) -> list[str]:
    """Return threshold failures for a retrieval-quality summary."""

    failures: list[str] = []
    for metric_name, label, threshold in (
        ("pass_rate", "pass rate", minimum_pass_rate),
        ("average_source_recall", "average source recall", minimum_source_recall),
    ):
        if threshold is None:
            continue
        metric_value = _coerce_summary_metric(summary, metric_name)
        if metric_value < threshold:
            failures.append(
                f"Benchmark {label} {metric_value:.2f} is below required threshold {threshold:.2f}."
            )
    return failures


def assert_retrieval_quality_thresholds(
    summary: Mapping[str, object],
    *,
    minimum_pass_rate: float | None = None,
    minimum_source_recall: float | None = None,
) -> None:
    """Raise ``AssertionError`` when retrieval-quality thresholds regress."""

    failures = check_retrieval_quality_thresholds(
        summary,
        minimum_pass_rate=minimum_pass_rate,
        minimum_source_recall=minimum_source_recall,
    )
    if failures:
        raise AssertionError(" ".join(failures))


def _build_retrieval_benchmark_result(
    benchmark: RetrievalBenchmark,
    *,
    retrieved_sources: tuple[str, ...],
) -> RetrievalBenchmarkResult:
    expected_source_set = set(benchmark.expected_sources)
    matched_sources = tuple(source for source in retrieved_sources if source in expected_source_set)
    return RetrievalBenchmarkResult(
        question=benchmark.question,
        expected_sources=benchmark.expected_sources,
        retrieved_sources=retrieved_sources,
        matched_sources=matched_sources,
        tags=benchmark.tags,
    )


def _summarize_benchmark_metrics(results: list[RetrievalBenchmarkResult]) -> dict[str, Any]:
    """Compute aggregate benchmark metrics without embedding per-case detail."""

    case_count = len(results)
    pass_count = sum(1 for result in results if result.passed)
    fully_covered_case_count = sum(1 for result in results if result.fully_covered)
    retrieved_hits = Counter(
        source for result in results for source in result.retrieved_sources if source
    )
    matched_hits = Counter(
        source for result in results for source in result.matched_sources if source
    )
    missed_hits = Counter(
        source for result in results for source in result.missed_sources if source
    )
    return {
        "case_count": case_count,
        "pass_count": pass_count,
        "pass_rate": (pass_count / case_count) if case_count else 0.0,
        "fully_covered_case_count": fully_covered_case_count,
        "fully_covered_rate": (fully_covered_case_count / case_count) if case_count else 0.0,
        "average_source_recall": (
            sum(result.source_recall for result in results) / case_count if case_count else 0.0
        ),
        "average_source_precision": (
            sum(result.source_precision for result in results) / case_count if case_count else 0.0
        ),
        "average_reciprocal_rank": (
            sum(result.reciprocal_rank for result in results) / case_count if case_count else 0.0
        ),
        "retrieved_source_hits": dict(sorted(retrieved_hits.items())),
        "matched_source_hits": dict(sorted(matched_hits.items())),
        "missed_source_hits": dict(sorted(missed_hits.items())),
    }


def _summarize_benchmark_tags(results: list[RetrievalBenchmarkResult]) -> dict[str, dict[str, Any]]:
    """Group benchmark metrics by tag for narrower retrieval-quality analysis."""

    results_by_tag: dict[str, list[RetrievalBenchmarkResult]] = {}
    for result in results:
        for tag in result.tags:
            results_by_tag.setdefault(tag, []).append(result)
    return {
        tag: _summarize_benchmark_metrics(tag_results)
        for tag, tag_results in sorted(results_by_tag.items())
    }


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
        results.append(
            _build_retrieval_benchmark_result(benchmark, retrieved_sources=retrieved_sources)
        )
    return results


def evaluate_retrieval_quality_suite(
    root: Path,
    benchmarks: list[RetrievalBenchmark],
    *,
    top_k: int = DEFAULT_RETRIEVAL_EVAL_TOP_K,
    top_k_values: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Evaluate retrieval quality across the default top-k and a small top-k sweep."""

    normalized_top_k_values = normalize_retrieval_top_k_values(top_k_values, default_top_k=top_k)
    chunks = chunk_documents(_select_benchmark_documents(root))
    max_top_k = max(normalized_top_k_values, default=top_k)
    results_by_top_k: dict[int, list[RetrievalBenchmarkResult]] = {
        value: [] for value in normalized_top_k_values
    }

    for benchmark in benchmarks:
        retrieved = retrieve(benchmark.question, chunks, top_k=max_top_k)
        retrieved_sources = _unique_in_order(
            [str(chunk.source.relative_to(root)) for chunk in retrieved]
        )
        for sweep_top_k in normalized_top_k_values:
            results_by_top_k[sweep_top_k].append(
                _build_retrieval_benchmark_result(
                    benchmark,
                    retrieved_sources=retrieved_sources[:sweep_top_k],
                )
            )

    top_k_summaries = [
        summarize_benchmark_results(results_by_top_k[sweep_top_k], top_k=sweep_top_k)
        for sweep_top_k in normalized_top_k_values
    ]
    default_summary = next(summary for summary in top_k_summaries if summary.get("top_k") == top_k)
    best_summary = max(
        top_k_summaries,
        key=lambda summary: (
            float(summary["pass_rate"]),
            float(summary["average_reciprocal_rank"]),
            float(summary["average_source_recall"]),
            -int(summary["top_k"]),
        ),
    )
    return {
        "case_count": len(benchmarks),
        "default_top_k": top_k,
        "top_k_values": list(normalized_top_k_values),
        "default_summary": default_summary,
        "top_k_summaries": top_k_summaries,
        "best_pass_rate_top_k": best_summary["top_k"],
        "best_pass_rate": best_summary["pass_rate"],
    }


def summarize_benchmark_results(
    results: list[RetrievalBenchmarkResult],
    *,
    top_k: int | None = None,
) -> dict[str, Any]:
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

    summary = {
        **_summarize_benchmark_metrics(results),
        "tag_summaries": _summarize_benchmark_tags(results),
        "results": [
            {
                "question": result.question,
                "expected_sources": list(result.expected_sources),
                "retrieved_sources": list(result.retrieved_sources),
                "matched_sources": list(result.matched_sources),
                "missed_sources": list(result.missed_sources),
                "passed": result.passed,
                "fully_covered": result.fully_covered,
                "first_relevant_rank": result.first_relevant_rank,
                "reciprocal_rank": result.reciprocal_rank,
                "source_recall": result.source_recall,
                "source_precision": result.source_precision,
                "tags": list(result.tags),
            }
            for result in results
        ],
    }
    if top_k is not None:
        summary["top_k"] = top_k
    return summary
