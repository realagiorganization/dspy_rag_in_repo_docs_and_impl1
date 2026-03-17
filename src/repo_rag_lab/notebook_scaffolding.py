"""High-level notebook scaffolds built from tested repository helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .azure import write_tuning_run_metadata
from .benchmarks import (
    build_retrieval_benchmarks,
    evaluate_retrieval_benchmarks,
    summarize_benchmark_results,
)
from .mcp import discover_mcp_servers
from .notebook_support import configure_notebook_logger
from .population_samples import (
    extend_population_candidates,
    load_population_candidates,
    rerank_population_candidates,
    summarize_population_candidates,
    validate_population_candidates,
)
from .training_samples import (
    load_training_examples,
    summarize_training_examples,
    validate_training_examples,
)
from .utilities import run_smoke_test, utility_summary
from .workflow import ask_repository

LOGGER = configure_notebook_logger("repo_rag_lab.notebook_scaffolding")
TRAINING_SAMPLES_PATH = Path("samples/training/repository_training_examples.yaml")
POPULATION_SAMPLES_PATH = Path("samples/population/repository_population_candidates.yaml")


def build_research_playbook_context(root: Path) -> dict[str, Any]:
    """Build the baseline research notebook context with smoke-test assertions."""

    baseline_question = "What does this repository research?"
    baseline_answer = ask_repository(baseline_question, root=root).answer
    mcp_candidates = discover_mcp_servers(root)
    smoke_test_summary: dict[str, Any] = json.loads(run_smoke_test(root))
    payload = {
        "root": str(root),
        "utility_summary": utility_summary(root),
        "mcp_candidates": [candidate.path for candidate in mcp_candidates],
        "baseline_question": baseline_question,
        "baseline_answer": baseline_answer,
        "smoke_test": smoke_test_summary,
    }
    LOGGER.info(
        "Built research playbook context with %s MCP candidates and smoke test manifest %s.",
        len(mcp_candidates),
        smoke_test_summary["manifest_path"],
    )
    return payload


def build_agent_workflow_context(root: Path) -> dict[str, Any]:
    """Build notebook-safe workflow context with validation and assertion data."""

    training_path = root / TRAINING_SAMPLES_PATH
    population_path = root / POPULATION_SAMPLES_PATH
    examples = load_training_examples(training_path)
    benchmarks = build_retrieval_benchmarks(examples)
    benchmark_summary: dict[str, Any] = summarize_benchmark_results(
        evaluate_retrieval_benchmarks(root, benchmarks)
    )
    candidates = extend_population_candidates(root, load_population_candidates(population_path))
    mcp_candidates = discover_mcp_servers(root)
    payload = {
        "root": str(root),
        "training_path": str(TRAINING_SAMPLES_PATH),
        "population_path": str(POPULATION_SAMPLES_PATH),
        "mcp_candidate_count": len(mcp_candidates),
        "mcp_candidates": [candidate.path for candidate in mcp_candidates],
        "training_validation_issues": validate_training_examples(examples, root=root),
        "population_validation_issues": validate_population_candidates(candidates, root=root),
        "benchmark_summary": benchmark_summary,
    }
    LOGGER.info(
        "Built agent workflow context with %s benchmarks and %s MCP candidates.",
        benchmark_summary["case_count"],
        payload["mcp_candidate_count"],
    )
    return payload


def build_training_lab_context(root: Path) -> dict[str, Any]:
    """Build training-lab scaffold data, benchmark assertions, and deployment metadata."""

    training_path = root / TRAINING_SAMPLES_PATH
    examples = load_training_examples(training_path)
    validation_issues = validate_training_examples(examples, root=root)
    training_summary: dict[str, Any] = summarize_training_examples(examples)
    benchmark_summary: dict[str, Any] = summarize_benchmark_results(
        evaluate_retrieval_benchmarks(root, build_retrieval_benchmarks(examples))
    )
    tuning_metadata_path = write_tuning_run_metadata(
        root=root,
        run_name="dspy-training-lab",
        training_data_path=training_path,
        benchmark_summary=benchmark_summary,
        deployment_name="repo-rag-ft",
    )
    payload = {
        "training_path": str(TRAINING_SAMPLES_PATH),
        "training_summary": training_summary,
        "validation_issues": validation_issues,
        "benchmark_summary": benchmark_summary,
        "tuning_metadata_path": str(tuning_metadata_path.relative_to(root)),
    }
    LOGGER.info(
        "Built training lab context for %s examples with %s validation issues.",
        training_summary["example_count"],
        len(validation_issues),
    )
    return payload


def build_population_lab_context(root: Path) -> dict[str, Any]:
    """Build corpus-population scaffold data with validation and empirical re-ranking."""

    population_path = root / POPULATION_SAMPLES_PATH
    training_path = root / TRAINING_SAMPLES_PATH
    base_candidates = load_population_candidates(population_path)
    extended_candidates = extend_population_candidates(root, base_candidates)
    examples = load_training_examples(training_path)
    benchmark_summary: dict[str, Any] = summarize_benchmark_results(
        evaluate_retrieval_benchmarks(root, build_retrieval_benchmarks(examples))
    )
    base_summary: dict[str, Any] = summarize_population_candidates(base_candidates)
    extended_summary: dict[str, Any] = summarize_population_candidates(extended_candidates)
    reranked_candidates = rerank_population_candidates(
        extended_candidates,
        {
            source: int(hit_count)
            for source, hit_count in benchmark_summary["retrieved_source_hits"].items()
        },
    )
    payload = {
        "population_path": str(POPULATION_SAMPLES_PATH),
        "base_summary": base_summary,
        "extended_summary": extended_summary,
        "validation_issues": validate_population_candidates(extended_candidates, root=root),
        "benchmark_summary": benchmark_summary,
        "reranked_sources": [candidate.source for candidate in reranked_candidates],
    }
    LOGGER.info(
        "Built population lab context with %s extended candidates.",
        extended_summary["candidate_count"],
    )
    return payload
