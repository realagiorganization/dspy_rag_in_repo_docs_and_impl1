"""High-level notebook scaffolds built from tested repository helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .azure import write_tuning_run_metadata
from .benchmarks import (
    build_retrieval_benchmarks,
    evaluate_retrieval_quality_suite,
)
from .corpus import load_documents
from .dspy_training import latest_dspy_artifact_metadata
from .mcp import discover_mcp_servers
from .notebook_support import configure_notebook_logger
from .population_samples import (
    extend_population_candidates,
    load_population_candidates,
    rerank_population_candidates,
    summarize_population_candidates,
    validate_population_candidates,
)
from .retrieval import chunk_documents
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
HUSHWHEEL_FIXTURE_ROOT = Path("tests/fixtures/hushwheel_lexiconarium")
HUSHWHEEL_TRAINING_SAMPLES_PATH = Path("samples/training/hushwheel_fixture_training_examples.yaml")
HUSHWHEEL_POPULATION_SAMPLES_PATH = Path(
    "samples/population/hushwheel_fixture_population_candidates.yaml"
)
HUSHWHEEL_HIGHLIGHT_QUESTIONS = (
    "What is the ember index?",
    "How does print_prefix_matches handle prefix search?",
)


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
    benchmark_suite: dict[str, Any] = evaluate_retrieval_quality_suite(root, benchmarks)
    benchmark_summary: dict[str, Any] = benchmark_suite["default_summary"]
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
        "benchmark_top_k_summaries": benchmark_suite["top_k_summaries"],
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
    benchmark_suite: dict[str, Any] = evaluate_retrieval_quality_suite(
        root,
        build_retrieval_benchmarks(examples),
    )
    benchmark_summary: dict[str, Any] = benchmark_suite["default_summary"]
    tuning_metadata_path = write_tuning_run_metadata(
        root=root,
        run_name="dspy-training-lab",
        training_data_path=training_path,
        benchmark_summary=benchmark_summary,
        deployment_name="repo-rag-ft",
    )
    compiled_program_metadata_path = latest_dspy_artifact_metadata(root)
    compiled_program_summary: dict[str, Any] | None = None
    compiled_program_path: str | None = None
    if compiled_program_metadata_path is not None:
        compiled_metadata = json.loads(compiled_program_metadata_path.read_text(encoding="utf-8"))
        compiled_program_summary = compiled_metadata.get("compiled_program_summary")
        program_path_value = compiled_metadata.get("program_path")
        if isinstance(program_path_value, str):
            compiled_program_path = program_path_value

    payload = {
        "training_path": str(TRAINING_SAMPLES_PATH),
        "training_summary": training_summary,
        "validation_issues": validation_issues,
        "benchmark_summary": benchmark_summary,
        "benchmark_top_k_summaries": benchmark_suite["top_k_summaries"],
        "tuning_metadata_path": str(tuning_metadata_path.relative_to(root)),
        "compiled_program_metadata_path": (
            str(compiled_program_metadata_path.relative_to(root))
            if compiled_program_metadata_path is not None
            else None
        ),
        "compiled_program_path": compiled_program_path,
        "compiled_program_summary": compiled_program_summary,
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
    benchmark_suite: dict[str, Any] = evaluate_retrieval_quality_suite(
        root,
        build_retrieval_benchmarks(examples),
    )
    benchmark_summary: dict[str, Any] = benchmark_suite["default_summary"]
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
        "benchmark_top_k_summaries": benchmark_suite["top_k_summaries"],
        "reranked_sources": [candidate.source for candidate in reranked_candidates],
    }
    LOGGER.info(
        "Built population lab context with %s extended candidates.",
        extended_summary["candidate_count"],
    )
    return payload


def build_hushwheel_fixture_lab_context(root: Path) -> dict[str, Any]:
    """Build notebook-safe context for the hushwheel retrieval fixture."""

    fixture_root = root / HUSHWHEEL_FIXTURE_ROOT
    training_path = root / HUSHWHEEL_TRAINING_SAMPLES_PATH
    population_path = root / HUSHWHEEL_POPULATION_SAMPLES_PATH
    manifest: dict[str, Any] = json.loads(
        (fixture_root / "fixture-manifest.json").read_text(encoding="utf-8")
    )
    examples = load_training_examples(training_path)
    candidates = load_population_candidates(population_path)
    benchmark_suite: dict[str, Any] = evaluate_retrieval_quality_suite(
        fixture_root,
        build_retrieval_benchmarks(examples),
    )
    benchmark_summary: dict[str, Any] = benchmark_suite["default_summary"]
    training_summary: dict[str, Any] = summarize_training_examples(examples)
    population_summary: dict[str, Any] = summarize_population_candidates(candidates)
    reranked_candidates = rerank_population_candidates(
        candidates,
        {
            source: int(hit_count)
            for source, hit_count in benchmark_summary["retrieved_source_hits"].items()
        },
    )
    documents = load_documents(fixture_root)
    chunks = chunk_documents(documents)
    corpus_summary: dict[str, Any] = {
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "largest_source": max(documents, key=lambda document: len(document.text)).path.name,
    }
    highlight_runs = []
    for question in HUSHWHEEL_HIGHLIGHT_QUESTIONS:
        answer = ask_repository(question, fixture_root)
        highlight_runs.append(
            {
                "question": question,
                "answer": answer.answer,
                "context_sources": [
                    str(chunk.source.relative_to(fixture_root)) for chunk in answer.context
                ],
            }
        )

    payload = {
        "root": str(root),
        "fixture_root": str(HUSHWHEEL_FIXTURE_ROOT),
        "training_path": str(HUSHWHEEL_TRAINING_SAMPLES_PATH),
        "population_path": str(HUSHWHEEL_POPULATION_SAMPLES_PATH),
        "fixture_manifest": manifest,
        "corpus_summary": corpus_summary,
        "training_summary": training_summary,
        "population_summary": population_summary,
        "training_validation_issues": validate_training_examples(examples, root=fixture_root),
        "population_validation_issues": validate_population_candidates(
            candidates, root=fixture_root
        ),
        "benchmark_summary": benchmark_summary,
        "benchmark_top_k_summaries": benchmark_suite["top_k_summaries"],
        "reranked_sources": [candidate.source for candidate in reranked_candidates],
        "highlight_runs": highlight_runs,
    }
    LOGGER.info(
        "Built hushwheel fixture context for %s examples across %s documents.",
        training_summary["example_count"],
        corpus_summary["document_count"],
    )
    return payload
