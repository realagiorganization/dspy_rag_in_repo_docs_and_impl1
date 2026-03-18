from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from repo_rag_lab.benchmarks import (
    RetrievalBenchmarkResult,
    assert_retrieval_quality_thresholds,
    build_retrieval_benchmarks,
    check_retrieval_quality_thresholds,
    evaluate_retrieval_benchmarks,
    evaluate_retrieval_quality_suite,
    is_benchmark_document_path,
    summarize_benchmark_results,
)
from repo_rag_lab.notebook_scaffolding import (
    build_agent_workflow_context,
    build_hushwheel_fixture_lab_context,
    build_population_lab_context,
    build_research_playbook_context,
    build_training_lab_context,
)
from repo_rag_lab.training_samples import load_training_examples

REPO_ROOT = Path(__file__).resolve().parents[1]
HUSHWHEEL_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "hushwheel_lexiconarium"


def _copy_scaffold_inputs(tmp_path: Path) -> Path:
    for relative_path in [
        Path("AGENTS.md"),
        Path("README.md"),
        Path("utilities/README.md"),
        Path("documentation/azure-deployment.md"),
        Path("documentation/package-api.md"),
        Path("documentation/mcp-discovery.md"),
        Path("documentation/inspired/dspy-rag-tutorial.md"),
        Path("documentation/inspired/implementing-rag-with-dspy-technical-guide.md"),
        Path("publication/README.md"),
        Path("samples/training/repository_training_examples.yaml"),
        Path("samples/population/repository_population_candidates.yaml"),
        Path("src/repo_rag_lab/mcp.py"),
        Path("src/repo_rag_lab/notebook_scaffolding.py"),
        Path("src/repo_rag_lab/utilities.py"),
    ]:
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative_path, destination)
    return tmp_path


def test_repository_benchmarks_pass_with_current_training_samples() -> None:
    examples = load_training_examples(
        REPO_ROOT / "samples" / "training" / "repository_training_examples.yaml"
    )
    benchmarks = build_retrieval_benchmarks(examples)
    results = evaluate_retrieval_benchmarks(REPO_ROOT, benchmarks)
    summary = summarize_benchmark_results(results)
    assert len(benchmarks) >= 8
    assert len(benchmarks) == len(examples)
    assert summary["case_count"] == len(examples)
    assert summary["pass_rate"] == 1.0
    assert set(summary["tag_summaries"]) == {tag for example in examples for tag in example.tags}


def test_summarize_benchmark_results_reports_quality_metrics() -> None:
    summary = summarize_benchmark_results(
        [
            RetrievalBenchmarkResult(
                question="Q1",
                expected_sources=("README.md", "utilities/README.md"),
                retrieved_sources=("AGENTS.md", "README.md", "utilities/README.md"),
                matched_sources=("README.md", "utilities/README.md"),
                tags=("repo",),
            ),
            RetrievalBenchmarkResult(
                question="Q2",
                expected_sources=("documentation/package-api.md",),
                retrieved_sources=("README.md",),
                matched_sources=(),
                tags=("docs",),
            ),
        ],
        top_k=3,
    )

    assert summary["top_k"] == 3
    assert summary["pass_count"] == 1
    assert summary["fully_covered_case_count"] == 1
    assert summary["fully_covered_rate"] == pytest.approx(0.5)
    assert summary["average_source_recall"] == pytest.approx(0.5)
    assert summary["average_source_precision"] == pytest.approx(1 / 3)
    assert summary["average_reciprocal_rank"] == pytest.approx(0.25)
    assert summary["missed_source_hits"]["documentation/package-api.md"] == 1
    assert summary["results"][0]["first_relevant_rank"] == 2
    assert summary["tag_summaries"]["repo"]["case_count"] == 1
    assert summary["tag_summaries"]["repo"]["pass_rate"] == pytest.approx(1.0)
    assert summary["tag_summaries"]["docs"]["case_count"] == 1
    assert summary["tag_summaries"]["docs"]["pass_rate"] == pytest.approx(0.0)


def test_evaluate_retrieval_quality_suite_reports_top_k_summaries() -> None:
    examples = load_training_examples(
        REPO_ROOT / "samples" / "training" / "repository_training_examples.yaml"
    )
    benchmarks = build_retrieval_benchmarks(examples)
    suite = evaluate_retrieval_quality_suite(REPO_ROOT, benchmarks, top_k=4, top_k_values=(1, 4))

    assert suite["case_count"] == len(benchmarks)
    assert suite["default_top_k"] == 4
    assert suite["top_k_values"] == [1, 4]
    assert suite["default_summary"]["top_k"] == 4
    assert suite["default_summary"]["tag_summaries"]
    assert [summary["top_k"] for summary in suite["top_k_summaries"]] == [1, 4]


def test_retrieval_quality_threshold_helpers_report_regressions() -> None:
    summary = {
        "pass_rate": 0.75,
        "average_source_recall": 0.5,
    }

    failures = check_retrieval_quality_thresholds(
        summary,
        minimum_pass_rate=1.0,
        minimum_source_recall=0.75,
    )

    assert "Benchmark pass rate 0.75 is below required threshold 1.00." in failures
    assert "Benchmark average source recall 0.50 is below required threshold 0.75." in failures

    with pytest.raises(AssertionError, match=r"Benchmark pass rate 0\.75"):
        assert_retrieval_quality_thresholds(
            summary,
            minimum_pass_rate=1.0,
            minimum_source_recall=0.75,
        )


def test_is_benchmark_document_path_excludes_operational_repo_surfaces() -> None:
    assert is_benchmark_document_path(Path("README.md")) is True
    assert is_benchmark_document_path(Path("publication/README.md")) is True
    assert is_benchmark_document_path(Path("README.AGENTS.md")) is False
    assert is_benchmark_document_path(Path("FILES.md")) is False
    assert is_benchmark_document_path(Path("env.md")) is False
    assert is_benchmark_document_path(Path("TODO.MD")) is False
    assert is_benchmark_document_path(Path("todo-backlog.yaml")) is False
    assert is_benchmark_document_path(Path("AGENTS.md.d/FILES.md")) is False
    assert (
        is_benchmark_document_path(Path(".codex/skills/post-push-gh-run-logging/SKILL.md")) is False
    )
    assert (
        is_benchmark_document_path(Path("docs/audit/2026-03-18-retest-with-env-refresh.md"))
        is False
    )
    assert (
        is_benchmark_document_path(
            Path("publication/exploratorium_translation/generated/exploratorium-manifest.json")
        )
        is False
    )
    assert is_benchmark_document_path(Path("samples/logs/20260318T010254Z-gh-runs.md")) is False
    assert (
        is_benchmark_document_path(Path("samples/training/repository_training_examples.yaml"))
        is False
    )
    assert (
        is_benchmark_document_path(Path("samples/population/repository_population_candidates.yaml"))
        is False
    )
    assert is_benchmark_document_path(Path("artifacts/notebook_logs/run.json")) is False
    assert is_benchmark_document_path(Path("tests/test_utilities.py")) is False
    assert is_benchmark_document_path(Path("README.DSPY.MD")) is False


def test_build_training_lab_context_writes_metadata_and_reports_clean_validation(
    tmp_path: Path,
) -> None:
    root = _copy_scaffold_inputs(tmp_path)
    examples = load_training_examples(
        root / "samples" / "training" / "repository_training_examples.yaml"
    )
    payload = build_training_lab_context(root)
    assert payload["training_summary"]["example_count"] == len(examples)
    assert payload["validation_issues"] == []
    assert (
        payload["benchmark_summary"]["case_count"] == payload["training_summary"]["example_count"]
    )
    assert payload["benchmark_summary"]["pass_rate"] == 1.0
    assert payload["benchmark_summary"]["tag_summaries"]
    assert len(payload["benchmark_top_k_summaries"]) >= 1
    assert (root / payload["tuning_metadata_path"]).exists()
    assert payload["compiled_program_metadata_path"] is None
    assert payload["compiled_program_path"] is None


def test_build_training_lab_context_uses_paths_relative_to_selected_root(
    tmp_path: Path,
) -> None:
    root = _copy_scaffold_inputs(tmp_path / "tests" / "fixture_repo")
    payload = build_training_lab_context(root)

    assert payload["validation_issues"] == []
    assert payload["benchmark_summary"]["pass_rate"] == 1.0
    assert payload["benchmark_summary"]["tag_summaries"]
    assert payload["benchmark_top_k_summaries"][-1]["top_k"] >= 4


def test_build_population_lab_context_extends_and_reranks_candidates(tmp_path: Path) -> None:
    root = _copy_scaffold_inputs(tmp_path)
    payload = build_population_lab_context(root)
    assert (
        payload["extended_summary"]["candidate_count"] > payload["base_summary"]["candidate_count"]
    )
    assert payload["validation_issues"] == []
    assert payload["benchmark_summary"]["tag_summaries"]
    assert len(payload["benchmark_top_k_summaries"]) >= 1
    assert "documentation/package-api.md" in payload["reranked_sources"]


def test_build_agent_workflow_context_reports_validation_and_benchmarks() -> None:
    payload = build_agent_workflow_context(REPO_ROOT)
    assert payload["training_validation_issues"] == []
    assert payload["population_validation_issues"] == []
    assert payload["benchmark_summary"]["pass_rate"] == 1.0
    assert payload["benchmark_summary"]["tag_summaries"]
    assert len(payload["benchmark_top_k_summaries"]) >= 1


def test_build_research_playbook_context_reports_smoke_and_baseline_details() -> None:
    payload = build_research_playbook_context(REPO_ROOT)
    assert "ask" in payload["utility_summary"]
    assert payload["baseline_question"] == "What does this repository research?"
    assert "Question:" in payload["baseline_answer"]
    assert "Answer:" in payload["baseline_answer"]
    assert "Evidence:" in payload["baseline_answer"]
    assert payload["smoke_test"]["answer_contains_repository"] is True
    assert payload["smoke_test"]["mcp_candidate_count"] == len(payload["mcp_candidates"])


def test_hushwheel_fixture_benchmarks_pass_with_nested_fixture_root() -> None:
    examples = load_training_examples(
        REPO_ROOT / "samples" / "training" / "hushwheel_fixture_training_examples.yaml"
    )
    summary = summarize_benchmark_results(
        evaluate_retrieval_benchmarks(HUSHWHEEL_FIXTURE_ROOT, build_retrieval_benchmarks(examples))
    )
    assert summary["case_count"] == len(examples)
    assert summary["pass_rate"] == 1.0
    assert summary["retrieved_source_hits"]["src/hushwheel.c"] >= 1


def test_build_hushwheel_fixture_lab_context_reports_fixture_scale_and_answers() -> None:
    payload = build_hushwheel_fixture_lab_context(REPO_ROOT)

    assert payload["fixture_manifest"]["entry_count"] == 4108
    assert payload["corpus_summary"]["document_count"] >= 19
    assert payload["corpus_summary"]["chunk_count"] >= 1500
    assert payload["training_summary"]["example_count"] == 6
    assert payload["population_summary"]["candidate_count"] == 7
    assert payload["training_validation_issues"] == []
    assert payload["population_validation_issues"] == []
    assert payload["benchmark_summary"]["pass_rate"] == 1.0
    assert len(payload["benchmark_top_k_summaries"]) >= 1
    assert payload["reranked_sources"][0] == "README.md"
    assert len(payload["highlight_runs"]) == 2
    assert any("src/hushwheel.c" in run["context_sources"] for run in payload["highlight_runs"])
